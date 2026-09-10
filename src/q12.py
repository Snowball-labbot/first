"""Causal forecasts, MILP day-ahead dispatch and independent physical audits.

Run from the repository: python -m src.q12 --data-root <C题 directory> --stage full
All power observations are interpreted as interval means at right-end labels.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
import numpy as np
import pandas as pd
import scipy
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix


@dataclass(frozen=True)
class Battery:
    minimum: float = 1200.0
    maximum: float = 10800.0
    initial: float = 6000.0
    max_power: float = 5000.0
    eta_c: float = 0.9
    eta_d: float = 0.9
    dt: float = 1 / 6

    @property
    def limit(self):
        return self.max_power * self.dt


B = Battery()
N = 144
TOL = 1e-5


def dump_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def interval_label(i):
    def clock(m):
        return f"{m // 60:02d}:{m % 60:02d}"
    return f"{clock(i * 10)}-{clock((i + 1) * 10)}"


def time_minutes(value):
    if hasattr(value, "hour"):
        return value.hour*60 + value.minute
    text = str(value).strip()
    next_day = "+1" in text
    hour, minute, *_ = text.replace("+1", "").split(":")
    return int(hour)*60 + int(minute) + 1440*int(next_day)


def read_inputs(root):
    root = Path(root)
    day = pd.read_excel(root / "附件/附件1.xlsx", sheet_name=0, header=0)
    load = pd.read_excel(root / "附件/附件2.xlsx", sheet_name="小区负载", header=0)
    pv = pd.read_excel(root / "附件/附件2.xlsx", sheet_name="光伏发电实际功率", header=0)
    dates = pd.to_datetime(load.iloc[:, 0])
    if day.shape != (144, 4) or load.shape != (365, 145) or pv.shape != (365, 145):
        raise ValueError("Unexpected input dimensions")
    if not dates.equals(pd.to_datetime(pv.iloc[:, 0])):
        raise ValueError("Load/PV dates differ")
    if list(dates) != list(pd.date_range("2025-01-01", "2025-12-31")):
        raise ValueError("Dates must cover the complete ordered year")
    expected_minutes = list(range(10,1441,10))
    if any([time_minutes(v) for v in labels] != expected_minutes
           for labels in (load.columns[1:], pv.columns[1:], day.iloc[:,0])):
        raise ValueError("Input time labels do not match")
    data = {
        "dates": pd.DatetimeIndex(dates), "price": day.iloc[:, 1].to_numpy(float),
        "q1_load": day.iloc[:, 2].to_numpy(float) * B.dt,
        "q1_pv": day.iloc[:, 3].to_numpy(float) * B.dt,
        "load": load.iloc[:, 1:].to_numpy(float) * B.dt,
        "pv": pv.iloc[:, 1:].to_numpy(float) * B.dt,
    }
    audit = {"shapes": {"attachment1": list(day.shape), "load": list(load.shape), "pv": list(pv.shape)},
             "date_start": str(dates.iloc[0].date()), "date_end": str(dates.iloc[-1].date()),
             "duplicates": int(dates.duplicated().sum()), "input_files": [], "variables": {}}
    for key in ["price", "q1_load", "q1_pv", "load", "pv"]:
        a = data[key]
        if not np.isfinite(a).all() or (a < 0).any():
            raise ValueError(f"Nonfinite or negative data in {key}; investigate, do not silently impute")
        audit["variables"][key] = {"count": int(a.size), "missing": 0, "min": float(a.min()),
                                    "max": float(a.max()), "zero_count": int((a == 0).sum())}
    if (data["price"] <= 0).any():
        raise ValueError("This implementation assumes strictly positive fixed prices")
    for relative in ["C题.pdf", "附件/附件1.xlsx", "附件/附件2.xlsx"]:
        raw = (root / relative).read_bytes()
        audit["input_files"].append({"path": relative, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    audit["data_treatment"] = "No missing/negative values found; no observations deleted or imputed. Unusual peaks retained."
    return data, audit


def optimize_day(load, pv, price, initial, terminal=6000.0, battery=B, integer=True):
    """Nominal minimum-cost schedule, g/c/d/w/S/z in kWh; terminal is a lower bound.

    For Q1 initial=terminal and terminal_equal=True is obtained by the explicit
    upper bound below when requested by a (value, 'equal') tuple.
    """
    n = len(price)
    eq_terminal = isinstance(terminal, tuple)
    target = terminal[0] if eq_terminal else terminal
    size = 6 * n + 1
    gi, ci, di, wi, si, zi = 0, n, 2*n, 3*n, 4*n, 5*n+1
    objective = np.zeros(size)
    objective[:n] = price
    lb, ub = np.zeros(size), np.full(size, np.inf)
    ub[ci:wi] = battery.limit
    lb[si:zi], ub[si:zi] = battery.minimum, battery.maximum
    lb[si] = ub[si] = initial
    lb[si+n] = target
    if eq_terminal:
        ub[si+n] = target
    ub[zi:] = 1
    integrality = np.zeros(size)
    integrality[zi:] = int(integer)
    a = lil_matrix((4*n, size))
    lower, upper = np.zeros(4*n), np.zeros(4*n)
    for t in range(n):
        a[t, gi+t], a[t, ci+t], a[t, di+t], a[t, wi+t] = 1, -1, 1, -1
        lower[t] = upper[t] = load[t] - pv[t]
        a[n+t, si+t+1], a[n+t, si+t] = 1, -1
        a[n+t, ci+t], a[n+t, di+t] = -battery.eta_c, 1 / battery.eta_d
        a[2*n+t, ci+t], a[2*n+t, zi+t] = 1, -battery.limit
        lower[2*n+t], upper[2*n+t] = -np.inf, 0
        a[3*n+t, di+t], a[3*n+t, zi+t] = 1, battery.limit
        lower[3*n+t], upper[3*n+t] = -np.inf, battery.limit
    start = time.perf_counter()
    result = milp(objective, integrality=integrality, bounds=Bounds(lb, ub),
                  constraints=LinearConstraint(a.tocsc(), lower, upper),
                  options={"time_limit": 30.0, "mip_rel_gap": 1e-7})
    elapsed = time.perf_counter() - start
    if not result.success or result.x is None:
        raise RuntimeError(f"MILP failed: status={result.status}, {result.message}")
    x = result.x
    sol = {"plan_kwh": x[:n], "charge_kwh": x[ci:di], "discharge_kwh": x[di:wi],
           "spill_kwh": x[wi:si], "soc_start_kwh": x[si:si+n], "soc_end_kwh": x[si+1:zi],
           "emergency_kwh": np.zeros(n), "load_kwh": np.asarray(load), "pv_kwh": np.asarray(pv)}
    frame = pd.DataFrame(sol)
    frame["price"] = price
    meta = {"status": int(result.status), "cost": float(np.dot(price, x[:n])),
            "seconds": elapsed, "mip_gap": float(getattr(result, "mip_gap", 0) or 0),
            "dual_bound": float(getattr(result, "mip_dual_bound", result.fun) or result.fun)}
    if integer:
        audit_trace(frame, battery=battery, initial=initial)
    return frame, meta


def execute_day(plan, load, pv, initial, price, battery=B):
    """Causal real-time balancing; does not read future observations.

    Assumes instantaneous regulation within a ten-minute constant-power interval.
    Surplus charges first; deficit exhausts feasible discharge before emergency.
    """
    s = float(initial)
    records = []
    for t, (g, l, v) in enumerate(zip(plan, load, pv)):
        surplus = float(g + v - l)
        c = min(max(surplus, 0), battery.limit, max(0, (battery.maximum-s)/battery.eta_c))
        d = min(max(-surplus, 0), battery.limit, max(0, (s-battery.minimum)*battery.eta_d))
        e = max(0, -surplus-d)
        w = max(0, surplus-c)
        end = s + battery.eta_c*c - d/battery.eta_d
        records.append((g, l, v, c, d, e, w, s, end, price[t]))
        s = end
    frame = pd.DataFrame(records, columns=["plan_kwh", "load_kwh", "pv_kwh", "charge_kwh", "discharge_kwh",
                                          "emergency_kwh", "spill_kwh", "soc_start_kwh", "soc_end_kwh", "price"], dtype=float)
    audit_trace(frame, battery=battery, initial=initial)
    return frame


def audit_trace(frame, battery=B, initial=None):
    """Independent vectorized equations, also applicable to saved full-year traces."""
    f = frame
    balance = f.plan_kwh + f.pv_kwh + f.discharge_kwh + f.emergency_kwh - f.load_kwh - f.charge_kwh - f.spill_kwh
    evolution = f.soc_end_kwh - f.soc_start_kwh - battery.eta_c*f.charge_kwh + f.discharge_kwh/battery.eta_d
    continuity = f.soc_start_kwh.to_numpy()[1:] - f.soc_end_kwh.to_numpy()[:-1]
    metrics = {"max_balance_residual_kwh": float(np.max(np.abs(balance))),
               "max_soc_residual_kwh": float(np.max(np.abs(evolution))),
               "max_soc_discontinuity_kwh": float(np.max(np.abs(continuity))) if len(f)>1 else 0,
               "simultaneous_intervals": int(((f.charge_kwh > TOL) & (f.discharge_kwh > TOL)).sum()),
               "min_soc_kwh": float(min(f.soc_start_kwh.min(), f.soc_end_kwh.min())),
               "max_soc_kwh": float(max(f.soc_start_kwh.max(), f.soc_end_kwh.max()))}
    checks = [np.isfinite(f.select_dtypes(include="number").to_numpy()).all(),
              (f[["plan_kwh", "charge_kwh", "discharge_kwh", "emergency_kwh", "spill_kwh"]].to_numpy() >= -TOL).all(),
              metrics["max_balance_residual_kwh"] < TOL, metrics["max_soc_residual_kwh"] < TOL,
              metrics["max_soc_discontinuity_kwh"] < TOL, metrics["simultaneous_intervals"] == 0,
              metrics["min_soc_kwh"] >= battery.minimum-TOL, metrics["max_soc_kwh"] <= battery.maximum+TOL,
              f.charge_kwh.max() <= battery.limit+TOL, f.discharge_kwh.max() <= battery.limit+TOL]
    if initial is not None:
        checks.append(abs(f.soc_start_kwh.iloc[0]-initial) < TOL)
    if not all(checks):
        raise AssertionError(f"Physical audit failed: {metrics}")
    return {**metrics, "pass": True}


def features(history, day, dates):
    """Features for all 144 targets on a day, using completed days only."""
    if day < 7:
        raise ValueError("Seven completed days required")
    past = history[day-7:day]
    h = (np.arange(N)+0.5)/N
    dow = dates[day].dayofweek
    cols = [past[-1], past[-2], past[0], past[-3:].mean(0), past.mean(0), past.std(0),
            np.full(N, past[-1].mean()), np.full(N, past[-3:].mean())]
    for k in (1, 2, 3):
        cols.extend([np.sin(2*np.pi*k*h), np.cos(2*np.pi*k*h)])
    cols.extend([np.full(N, float(dow == k)) for k in range(7)])
    return np.column_stack(cols)


def ridge_fit(x, y, alpha):
    """Centered ridge via linear solve; intercept unpenalized, no sklearn required."""
    mean, scale = x.mean(0), x.std(0)
    scale[scale < 1e-10] = 1
    z = (x-mean)/scale
    intercept = float(y.mean())
    coef = np.linalg.solve(z.T@z + alpha*np.eye(z.shape[1]), z.T@(y-intercept))
    return mean, scale, coef, intercept


def forecasts(data, method, alphas=(10.0, 10.0), stop=365):
    pred, fit_dates = {}, []
    for k, alpha in zip(("load", "pv"), alphas):
        values = data[k]
        out = np.zeros((stop, N))
        model, fitted_on = None, -1
        all_x = {d: features(values, d, data["dates"]) for d in range(7, stop)}
        for d in range(stop):
            if d == 0:
                out[d] = data[f"q1_{k}"]
            elif d < 7:
                out[d] = values[max(0,d-3):d].mean(0)
            elif method == "seasonal" or d < 14:
                out[d] = 0.5*values[d-1] + 0.5*values[d-7]
            else:
                if model is None or d-fitted_on >= 7:
                    training_days = range(max(7,d-60), d)
                    x = np.concatenate([all_x[j] for j in training_days])
                    y = values[max(7,d-60):d].ravel()
                    model = ridge_fit(x, y, alpha)
                    fitted_on = d
                    fit_dates.append({"variable": k, "decision_date": str(data["dates"][d].date()),
                                      "fit_until": str(data["dates"][d-1].date()), "alpha": alpha,
                                      "training_rows": len(y)})
                mean, scale, coef, intercept = model
                out[d] = ((all_x[d]-mean)/scale)@coef+intercept
            out[d] = np.maximum(out[d], 0)
            if k == "pv" and d:
                out[d, values[max(0,d-7):d].max(0) == 0] = 0
        pred[k] = out
    return pred, fit_dates


def reserve(data, forecast, day, quantile):
    if quantile == 0 or day < 7:
        return np.zeros(N)
    start = max(1, day-28)
    errors = (data["load"][start:day]-data["pv"][start:day]
              -forecast["load"][start:day]+forecast["pv"][start:day])
    # Pool +/- three slots; no wrap at the day boundary, no future residuals.
    return np.array([max(0.0, float(np.quantile(errors[:,max(0,t-3):min(N,t+4)], quantile))) for t in range(N)])


def summarize_day(f, date, name, seconds, gap=0.0):
    normal = float(np.dot(f.plan_kwh, f.price))
    emergency = float(5*np.dot(f.emergency_kwh, f.price))
    return {"date": str(date.date()), "strategy": name, "normal_cost_yuan": normal,
            "emergency_cost_yuan": emergency, "total_cost_yuan": normal+emergency,
            "plan_kwh": float(f.plan_kwh.sum()), "emergency_kwh": float(f.emergency_kwh.sum()),
            "emergency_intervals": int((f.emergency_kwh>TOL).sum()), "spill_kwh": float(f.spill_kwh.sum()),
            "charge_kwh": float(f.charge_kwh.sum()), "discharge_kwh": float(f.discharge_kwh.sum()),
            "soc_start_kwh": float(f.soc_start_kwh.iloc[0]), "soc_end_kwh": float(f.soc_end_kwh.iloc[-1]),
            "solve_seconds": seconds, "mip_gap": gap}


def backtest(data, forecast, start, stop, initial, quantile, name, retain=True):
    s, daily, frames = initial, [], []
    for d in range(start,stop):
        buffer = reserve(data, forecast, d, quantile)
        nominal, meta = optimize_day(forecast["load"][d]+buffer, forecast["pv"][d], data["price"], s)
        f = execute_day(nominal.plan_kwh.to_numpy(), data["load"][d], data["pv"][d], s, data["price"])
        daily.append(summarize_day(f, data["dates"][d], name, meta["seconds"], meta["mip_gap"]))
        if retain:
            f.insert(0,"interval_start", pd.date_range(data["dates"][d],periods=N,freq="10min"))
            f.insert(1,"date", str(data["dates"][d].date()))
            f.insert(2,"slot", np.arange(N))
            f["forecast_load_kwh"], f["forecast_pv_kwh"], f["reserve_kwh"] = forecast["load"][d], forecast["pv"][d], buffer
            frames.append(f)
        s = float(f.soc_end_kwh.iloc[-1])
        if retain and (d == start or data["dates"][d].day == 1):
            print(f"{name}: {data['dates'][d].date()}, cumulative cost={sum(x['total_cost_yuan'] for x in daily):.2f}", flush=True)
    combined = pd.concat(frames,ignore_index=True) if frames else None
    if combined is not None:
        audit_trace(combined, initial=initial)
    return pd.DataFrame(daily), combined, s


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("artifacts/q12"))
    parser.add_argument("--stage", choices=["q1","smoke","full"],default="full")
    args = parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    start = time.perf_counter()
    data, input_audit = read_inputs(args.data_root)
    dump_json(args.out/"input_audit.json", input_audit)
    q1, q1_meta = optimize_day(data["q1_load"], data["q1_pv"], data["price"], B.initial, (B.initial,"equal"))
    lp, lp_meta = optimize_day(data["q1_load"], data["q1_pv"], data["price"], B.initial, (B.initial,"equal"), integer=False)
    q1.insert(0,"slot",np.arange(N));q1.insert(1,"interval",[interval_label(i) for i in range(N)])
    q1.to_csv(args.out/"q1_intervals.csv",index=False)
    no_storage_cost = float(np.dot(np.maximum(data["q1_load"]-data["q1_pv"],0),data["price"]))
    q1_meta.update({"no_storage_cost":no_storage_cost,"saving_percent":100*(no_storage_cost-q1_meta["cost"])/no_storage_cost,
                    "lp_cost_lower_bound":lp_meta["cost"], "lp_gap_yuan": q1_meta["cost"]-lp_meta["cost"],
                    "audit":audit_trace(q1,initial=B.initial), "plan_kwh":float(q1.plan_kwh.sum())})
    dump_json(args.out/"q1_summary.json",q1_meta)
    print("Q1",json.dumps(q1_meta,ensure_ascii=False),flush=True)
    if args.stage == "q1":
        return
    seasonal, _ = forecasts(data,"seasonal")
    tuning = []
    for alpha in (1.0,10.0,100.0):
        pred, _ = forecasts(data,"ridge",(alpha,alpha),stop=31)
        row = {"alpha":alpha}
        for key in ("load","pv"):
            row[key+"_mae_kw"] = float(np.abs(pred[key][21:31]-data[key][21:31]).mean()/B.dt)
        tuning.append(row)
    alpha_load = min(tuning,key=lambda r:r["load_mae_kw"])["alpha"]
    alpha_pv = min(tuning,key=lambda r:r["pv_mae_kw"])["alpha"]
    ridge, fit_log = forecasts(data,"ridge",(alpha_load,alpha_pv))
    dump_json(args.out/"forecast_fit_log.json",fit_log)
    pd.DataFrame(tuning).to_csv(args.out/"ridge_validation.csv",index=False)
    _, _, validation_soc = backtest(data,seasonal,0,21,B.initial,0,"warmup",retain=False)
    warmup, _, evaluation_soc = backtest(data,seasonal,21,31,validation_soc,0,"warmup",retain=False)
    warmup.to_csv(args.out/"warmup_last10days.csv",index=False)
    validation = []
    for method, pred in (("seasonal",seasonal),("ridge",ridge)):
        for q in (0.0,0.7,0.8,0.9):
            daily, _, _ = backtest(data,pred,21,31,validation_soc,q,method,retain=False)
            validation.append({"forecast":method,"quantile":q,"cost_yuan":float(daily.total_cost_yuan.sum()),
                               "emergency_cost_yuan":float(daily.emergency_cost_yuan.sum()),
                               "end_soc_kwh":float(daily.soc_end_kwh.iloc[-1])})
    selected = min(validation,key=lambda r:r["cost_yuan"])
    pd.DataFrame(validation).to_csv(args.out/"policy_validation.csv",index=False)
    stop = 38 if args.stage == "smoke" else 365
    strategies = [("seasonal_q0","seasonal",0.0),("ridge_q0","ridge",0.0)]
    for method in ("seasonal","ridge"):
        best = min((v for v in validation if v["forecast"]==method),key=lambda r:r["cost_yuan"])
        if best["quantile"]:
            strategies.append((f"{method}_q{best['quantile']:g}",method,best["quantile"]))
    selected_name = f"{selected['forecast']}_q{selected['quantile']:g}"
    all_daily, metrics = [], []
    for name, method, q in strategies:
        pred = {"seasonal":seasonal,"ridge":ridge}[method]
        daily, trace, _ = backtest(data,pred,31,stop,evaluation_soc,q,name)
        all_daily.append(daily)
        trace.to_csv(args.out/f"{name}_intervals.csv.gz",index=False,float_format="%.17g")
        audit = audit_trace(trace,initial=evaluation_soc)
        row = {"strategy":name,"forecast":method,"quantile":q,"selected_on_january":name==selected_name,
               "days":len(daily),"total_cost_yuan":float(daily.total_cost_yuan.sum()),
               "normal_cost_yuan":float(daily.normal_cost_yuan.sum()), "emergency_cost_yuan":float(daily.emergency_cost_yuan.sum()),
               "emergency_kwh":float(daily.emergency_kwh.sum()),"emergency_intervals":int(daily.emergency_intervals.sum()),
               "plan_kwh":float(daily.plan_kwh.sum()),"spill_kwh":float(daily.spill_kwh.sum()),
               "solve_seconds":float(daily.solve_seconds.sum()), "initial_soc_kwh":evaluation_soc,
               "final_soc_kwh":float(daily.soc_end_kwh.iloc[-1]),"audit":audit}
        for key in ("load","pv"):
            error = (pred[key][31:stop]-data[key][31:stop])/B.dt
            row[key+"_mae_kw"],row[key+"_rmse_kw"] = float(np.abs(error).mean()),float(np.sqrt(np.mean(error**2)))
        metrics.append(row)
    daily = pd.concat(all_daily,ignore_index=True)
    daily.to_csv(args.out/"q2_daily_metrics.csv",index=False)
    dump_json(args.out/"q2_summary.json",{"selection":selected,"selected_strategy":selected_name,"strategies":metrics})
    command = f'python -m src.q12 --data-root "{args.data_root}" --out "{args.out}" --stage {args.stage}'
    manifest = {"stage":args.stage,"battery":asdict(B),"time_interpretation":"interval mean power, right-end labels",
                "alpha_load":alpha_load,"alpha_pv":alpha_pv,"validation_start":"2025-01-22","validation_end":"2025-01-31",
                "evaluation_start":"2025-02-01","evaluation_end":str(data["dates"][stop-1].date()),
                "validation_initial_soc":validation_soc,"evaluation_initial_soc":evaluation_soc,
                "terminal_nominal_soc_minimum":6000,"refit_period_days":7,"training_window_days":60,
                "residual_window_days":28,"pool_halfwidth_slots":3,"seed":2026,"deterministic":True,
                "selected_strategy":selected_name,"command":command,"total_seconds":time.perf_counter()-start,
                "python":platform.python_version(),"numpy":np.__version__,"scipy":scipy.__version__,"pandas":pd.__version__,
                "platform":platform.platform(),"git_head_before_run":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
                "source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"input_files":input_audit["input_files"]}
    dump_json(args.out/"run_manifest.json",manifest)
    print("COMPLETE",json.dumps({"selected":selected_name,"seconds":manifest["total_seconds"],"days":stop-31}),flush=True)


if __name__ == "__main__":
    main()
