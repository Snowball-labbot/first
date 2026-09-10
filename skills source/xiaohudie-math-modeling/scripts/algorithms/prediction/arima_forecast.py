# -*- coding: utf-8 -*-
"""ARIMA 时序预测 —— 平稳或可差分平稳的单变量时序（样本 50+）。

防错：
  - 差分阶数 d 由 ADF 单位根检验确定；p、q 由 ACF/PACF 或 AIC/BIC 定；
  - 训练/验证必须按时间顺序划分，禁止随机打乱；
  - ARIMA 不直接处理多变量（多变量用 VAR/回归簇），季节性用 SARIMA。

依赖：statsmodels（未安装时给出提示）。
运行自测：python arima_forecast.py
"""
import warnings


def adf_test(series):
    """ADF 单位根检验，返回 (p值, 是否平稳@5%)。"""
    from statsmodels.tsa.stattools import adfuller
    stat, p, *_ = adfuller(series, autolag="AIC")
    return p, p < 0.05


def choose_d(series, max_d=2):
    """迭代差分直到平稳，返回 (d, 差分后序列)。"""
    s = list(map(float, series))
    for d in range(max_d + 1):
        _, stationary = adf_test(s)
        if stationary:
            return d, s
        s = [s[i + 1] - s[i] for i in range(len(s) - 1)]
    return max_d, s


def arima_forecast(train, steps=5, order=None):
    """ARIMA 建模预测。order=None 时先用 ADF 定差分阶数 d，
    再在网格 (p,q)∈{0..2}² 内按 AIC 择优（拟合始终在原始序列上，由模型内部差分）。

    train: 训练时序（按时间顺序！）；steps: 预测步数。
    返回 dict：order, 预测值, 95% 置信区间, AIC。
    """
    import numpy as np
    import itertools
    from statsmodels.tsa.arima.model import ARIMA

    train = np.asarray(train, dtype=float)
    if order is None:
        d, _ = choose_d(train)
        best, best_order = None, (1, d, 1)
        for p, q in itertools.product(range(3), repeat=2):
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    res = ARIMA(train, order=(p, d, q)).fit()
                if best is None or res.aic < best.aic:
                    best, best_order = res, (p, d, q)
            except Exception:
                continue
        if best is None:
            raise RuntimeError("ARIMA 网格搜索全部失败，考虑换指数平滑/灰色预测")
        res, order = best, best_order
    else:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = ARIMA(train, order=order).fit()

    fc = res.get_forecast(steps=steps)
    return {"order": order, "pred": fc.predicted_mean,
            "ci95": fc.conf_int(alpha=0.05), "aic": res.aic}


if __name__ == "__main__":
    import numpy as np
    rng = np.random.default_rng(7)
    # 构造带趋势+周期的序列（80 期），最后 5 期留作验证
    t = np.arange(85)
    y = 50 + 0.8 * t + 10 * np.sin(2 * np.pi * t / 12) + rng.normal(0, 2, 85)
    train, true = y[:-5], y[-5:]

    r = arima_forecast(train, steps=5)
    pred = np.asarray(r["pred"])
    mape = np.mean(np.abs((true - pred) / true)) * 100
    print(f"选定 ARIMA{r['order']}  AIC = {r['aic']:.1f}")
    print(f"验证集预测 = {np.round(pred, 2)}")
    print(f"真实值     = {np.round(true, 2)}")
    print(f"验证 MAPE = {mape:.2f}%")
    lo, hi = np.asarray(r["ci95"])[:, 0], np.asarray(r["ci95"])[:, 1]
    cover = np.mean((true >= lo) & (true <= hi))
    print(f"95% 置信区间覆盖率 = {cover:.0%}")
    assert mape < 8.0, "带趋势周期序列 ARIMA 验证 MAPE 应较小"
    print("arima_forecast.py 自测通过")
