# -*- coding: utf-8 -*-
"""CRITIC 客观赋权法 —— 兼顾指标对比强度（标准差）与冲突性（相关性）的客观权重。

适用：数据驱动的指标权重，弥补熵权法"只看离散度、忽略指标间冲突"的不足。
公式：信息量 C_j = sigma_j * sum_k(1 - r_jk)；权重 w_j = C_j / sum(C)。
防错：指标需先同向化；强相关指标（r→1）会被降权，这是设计行为。

运行自测：python critic.py
"""
import numpy as np


def critic_weights(X, positive_idx=None):
    """CRITIC 权重。

    X: m 方案 × n 指标原始矩阵。
    positive_idx: True=正向指标，False=负向；None 默认全正向。
    返回（权重向量, 标准化矩阵）。
    """
    X = np.asarray(X, dtype=float)
    m, n = X.shape
    if positive_idx is None:
        positive_idx = [True] * n

    # 同向化 + Min-Max 标准化
    Z = np.zeros_like(X, dtype=float)
    for j in range(n):
        col = X[:, j]
        rng = col.max() - col.min()
        if rng == 0:
            Z[:, j] = 0.0
            continue
        if positive_idx[j]:
            Z[:, j] = (col - col.min()) / rng
        else:
            Z[:, j] = (col.max() - col) / rng

    sigma = Z.std(axis=0, ddof=0)
    corr = np.corrcoef(Z, rowvar=False)
    corr = np.nan_to_num(corr, nan=0.0)          # 常数列相关系数为 nan
    conflict = (1 - corr).sum(axis=1)            # 每个指标与其他指标的冲突总和
    info = sigma * conflict                      # 信息承载量
    info = np.where(info < 0, 0, info)
    w = info / info.sum()
    return w, Z


def score_alternatives(Z, w):
    """CRITIC 综合得分 = 标准化矩阵 × 权重（越大越优）。"""
    return np.asarray(Z) @ np.asarray(w)


if __name__ == "__main__":
    # 自测：5 城市 × 4 指标（GDP↑、失业率↓、绿化率↑、通勤时间↓）
    # 其中 GDP 与绿化率设计为强相关，验证 CRITIC 对冗余指标的降权。
    X = np.array([
        [5200, 4.2, 41, 38],
        [4300, 5.1, 36, 45],
        [6100, 3.8, 48, 36],
        [3800, 6.0, 33, 52],
        [5600, 4.5, 45, 40],
    ])
    direction = [True, False, True, False]
    w, Z = critic_weights(X, direction)
    s = score_alternatives(Z, w)
    print(f"CRITIC 权重 = {np.round(w, 4)}  和 = {w.sum():.4f}")
    print(f"城市综合得分 = {np.round(s, 4)}（城市1~5）")
    corr = np.corrcoef(Z, rowvar=False)
    print(f"GDP-绿化率相关系数 = {corr[0, 2]:.3f}（强相关 -> 两者权重被分摊）")
    assert abs(w.sum() - 1) < 1e-9 and (w >= 0).all()
    print("critic.py 自测通过")
