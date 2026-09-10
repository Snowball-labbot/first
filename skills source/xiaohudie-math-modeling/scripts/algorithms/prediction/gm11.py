# -*- coding: utf-8 -*-
"""GM(1,1) 灰色预测 —— 小样本（4~15 个数据点）短期预测。

适用：单调递增或近似指数增长的非负序列。
防错：
  - 只适合单调/近似指数序列，震荡或递减序列失效（先做级比检验）；
  - 不适合长期预测，报告外推步数与精度衰减；
  - 发展系数 -a > 0.3 时慎用外推（误差快速放大）。

运行自测：python gm11.py
"""
import numpy as np


def level_ratio_check(x0, bound=(np.exp(-2 / 3), np.exp(2 / 3))):
    """级比检验：lambda(k)=x0(k-1)/x0(k) 必须落在 (e^{-2/(n+1)}, e^{2/(n+1)}) 内。
    返回 (通过?, 各级比)。不通过时可对数据取对数或平移变换。"""
    x0 = np.asarray(x0, dtype=float)
    n = len(x0)
    lam = x0[:-1] / x0[1:]
    ok = bool(((lam > bound[0]) & (lam < bound[1])).all())
    return ok, lam


def gm11(x0, steps=3):
    """GM(1,1) 建模与预测。

    x0: 原始非负序列；steps: 向后预测步数。
    返回 dict：a/b（发展系数/灰作用量）、拟合值、预测值、拟合 MAPE。
    """
    x0 = np.asarray(x0, dtype=float)
    assert (x0 > 0).all(), "GM(1,1) 要求非负序列（含 0 时先平移）"
    ok, _ = level_ratio_check(x0)
    if not ok:
        print("[GM(1,1)][警告] 级比检验未通过，预测可能失真（考虑取对数/平移变换）")

    n = len(x0)
    x1 = np.cumsum(x0)                                  # 1-AGO
    z1 = 0.5 * (x1[1:] + x1[:-1])                       # 紧邻均值序列
    B = np.vstack([-z1, np.ones(n - 1)]).T
    a, b = np.linalg.lstsq(B, x0[1:], rcond=None)[0]    # 最小二乘估计

    # 时间响应式还原
    x1_hat = (x0[0] - b / a) * np.exp(-a * np.arange(n + steps)) + b / a
    x0_hat = np.r_[x1_hat[0], np.diff(x1_hat)]

    fit = x0_hat[:n]
    pred = x0_hat[n:]
    mape = np.mean(np.abs((x0 - fit) / x0)) * 100
    return {"a": a, "b": b, "fit": fit, "pred": pred, "mape": mape,
            "level_ratio_ok": ok}


if __name__ == "__main__":
    # 自测：近指数增长序列，预测 3 期
    x0 = [120, 137, 155, 178, 203, 231, 264]
    r = gm11(x0, steps=3)
    print(f"发展系数 a = {r['a']:.4f}（|a|<0.3 外推较稳），灰作用量 b = {r['b']:.2f}")
    print(f"拟合值 = {np.round(r['fit'], 1)}")
    print(f"未来 3 期预测 = {np.round(r['pred'], 1)}")
    print(f"拟合 MAPE = {r['mape']:.2f}%  级比检验通过 = {r['level_ratio_ok']}")
    assert r["mape"] < 5.0, "指数序列拟合 MAPE 应很小"
    assert (np.diff(r["pred"]) > 0).all(), "单调序列预测应保持单调"
    print("gm11.py 自测通过")
