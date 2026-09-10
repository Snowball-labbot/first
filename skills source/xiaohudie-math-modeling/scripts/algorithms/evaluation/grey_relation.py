# -*- coding: utf-8 -*-
"""灰色关联分析 GRA —— 数据少、信息不完整时的评价/因素分析。

适用：样本少（如每年一个点）、无法做回归时，衡量各因素序列与母序列的关联度。
防错：
  - 分辨系数 rho 通常取 0.5，敏感性分析时可试 0.3/0.5/0.7 对比排序是否稳定；
  - 序列必须先无量纲化（初值像/均值像），否则量纲淹没差异；
  - 关联度只表相对强弱，不是绝对精度。

运行自测：python grey_relation.py
"""
import numpy as np


def grey_relation_degree(mother, factors, rho=0.5, normalize="initial"):
    """计算各因素序列与母序列的灰色关联度。

    mother: 母序列（1D，如"销售额"）。
    factors: (n_factors, T) 因素序列矩阵（如各影响因素逐年值）。
    rho: 分辨系数，默认 0.5。
    normalize: 'initial' 初值像 / 'mean' 均值像。
    返回（关联度数组[按 factors 行序], 无量纲化后的差值矩阵信息）。
    """
    x0 = np.asarray(mother, dtype=float)
    X = np.asarray(factors, dtype=float)
    assert x0.shape[0] == X.shape[1], "母序列与因素序列长度必须一致"

    def _norm(s):
        if normalize == "initial":
            base = s[0] if s[0] != 0 else s[s != 0][0] if (s != 0).any() else 1.0
            return s / base
        m = s.mean() if s.mean() != 0 else 1.0
        return s / m

    x0n = np.abs(_norm(x0))
    Xn = np.abs(np.vstack([_norm(s) for s in X]))

    # 差值矩阵、两级最小差/最大差
    D = np.abs(Xn - x0n)
    d_min, d_max = D.min(), D.max()
    xi = (d_min + rho * d_max) / (D + rho * d_max)   # 关联系数
    r = xi.mean(axis=1)                              # 关联度
    return r, xi


if __name__ == "__main__":
    # 自测：某产品 8 年销量（母序列）与 3 个影响因素
    years = np.arange(2018, 2026)
    mother = [120, 135, 150, 148, 170, 188, 205, 230]      # 销量
    factors = [
        [35, 38, 42, 44, 50, 55, 60, 66],   # 广告投入（强相关）
        [8.5, 8.2, 8.0, 8.1, 7.6, 7.4, 7.2, 7.0],  # 价格（中等）
        [2, 9, 1, 7, 4, 8, 2, 6],           # 随机噪声（弱相关）
    ]
    r, _ = grey_relation_degree(mother, factors)
    print("灰色关联度 =", np.round(r, 4), "（广告/价格/噪声）")
    order = np.argsort(-r) + 1
    print(f"关联度排序（从强到弱）= {order}")
    assert r[0] > r[2] and r[1] > r[2], "强相关因素关联度应高于噪声"
    # 分辨系数稳定性检查
    r3, _ = grey_relation_degree(mother, factors, rho=0.3)
    assert (np.argsort(-r) == np.argsort(-r3)).all(), "排序对 rho 不稳定，需在论文中说明"
    print("rho=0.3 下排序一致（稳定性检查通过）")
    print("grey_relation.py 自测通过")
