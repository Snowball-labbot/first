# -*- coding: utf-8 -*-
"""指数平滑（一次 / 二次 / 三次 Holt-Winters）—— 中短期预测，数据量少（10+）也适用。

适用：中短期趋势预测；有季节周期用三次（可加或可乘）。
防错：长期趋势或复杂非线性表现差；季节周期需预先指定；alpha/beta/gamma 在 (0,1)。

本实现纯 numpy，无 statsmodels 依赖；结果与教科书递推式一致。
运行自测：python exp_smoothing.py
"""
import numpy as np


def simple_es(y, alpha, steps=1):
    """一次指数平滑：适合无趋势序列。返回（拟合序列, 未来 steps 期预测）。"""
    y = np.asarray(y, dtype=float)
    assert 0 < alpha < 1
    s = np.empty_like(y)
    s[0] = y[0]
    for t in range(1, len(y)):
        s[t] = alpha * y[t] + (1 - alpha) * s[t - 1]
    pred = np.full(steps, s[-1])
    return s, pred


def holt_es(y, alpha=0.5, beta=0.3, steps=3):
    """二次（Holt 线性趋势）指数平滑。返回（拟合, 水平, 趋势, 未来预测）。"""
    y = np.asarray(y, dtype=float)
    n = len(y)
    level, trend = y[0], y[1] - y[0]
    fit = np.empty(n)
    fit[0] = level
    for t in range(1, n):
        prev_level = level
        level = alpha * y[t] + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
        fit[t] = level + trend          # 预测一期
    pred = level + trend * np.arange(1, steps + 1)
    return fit, level, trend, pred


def holt_winters(y, period=12, alpha=0.3, beta=0.2, gamma=0.4, steps=6, seasonal="add"):
    """三次 Holt-Winters（可加/可乘季节）。返回（拟合, 未来预测）。

    需要至少两个完整周期的数据（len(y) >= 2*period）。
    """
    y = np.asarray(y, dtype=float)
    n = len(y)
    assert n >= 2 * period, "Holt-Winters 至少需要两个完整季节周期"
    m = period
    if seasonal == "add":
        season_init = y[:m] - y[:m].mean()
    else:
        season_init = y[:m] / max(y[:m].mean(), 1e-9)
    seas = list(season_init)
    level = y[:m].mean()
    trend = (y[m:2 * m].mean() - y[:m].mean()) / m
    fit = np.empty(n)
    for t in range(n):
        s_t = seas[-m] if seasonal == "add" else seas[-m]
        if seasonal == "add":
            f = level + trend + s_t
            new_level = alpha * (y[t] - s_t) + (1 - alpha) * (level + trend)
        else:
            f = (level + trend) * s_t
            new_level = alpha * (y[t] / max(s_t, 1e-9)) + (1 - alpha) * (level + trend)
        fit[t] = f
        trend = beta * (new_level - level) + (1 - beta) * trend
        level = new_level
        if seasonal == "add":
            new_s = gamma * (y[t] - level) + (1 - gamma) * s_t
        else:
            new_s = gamma * (y[t] / max(level, 1e-9)) + (1 - gamma) * s_t
        seas.append(new_s)
    pred = []
    for h in range(1, steps + 1):
        s_h = seas[-m + (h - 1) % m]
        if seasonal == "add":
            pred.append(level + h * trend + s_h)
        else:
            pred.append((level + h * trend) * s_h)
    return fit, np.asarray(pred)


if __name__ == "__main__":
    rng = np.random.default_rng(3)
    # 自测1：Holt 线性趋势（信号起点放大到 100，避免前段小基数放大 MAPE）
    t = np.arange(40)
    y = 100 + 1.2 * t + rng.normal(0, 1.5, 40)
    fit, _, _, pred = holt_es(y, steps=5)
    mape = np.mean(np.abs((y - fit) / y)) * 100
    print(f"[Holt] 拟合 MAPE = {mape:.2f}%  未来 5 期 = {np.round(pred, 2)}")
    assert mape < 5 and np.all(np.diff(pred) > 0.5)
    # 自测2：Holt-Winters 可加季节（周期 12）
    tt = np.arange(48)
    y2 = 100 + 0.5 * tt + 15 * np.sin(2 * np.pi * tt / 12) + rng.normal(0, 2, 48)
    fit2, pred2 = holt_winters(y2, period=12, steps=6)
    mape2 = np.mean(np.abs((y2 - fit2) / y2)) * 100
    print(f"[HW-加法] 拟合 MAPE = {mape2:.2f}%  未来 6 期 = {np.round(pred2, 2)}")
    assert mape2 < 10
    print("exp_smoothing.py 自测通过")
