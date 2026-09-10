# -*- coding: utf-8 -*-
"""熵权法 + TOPSIS（客观赋权 + 距离排序）—— 评价类最常用组合。

适用：完全数据驱动的多方案综合排序（>=2 个方案）。
防错：
  - 某指标所有方案取值相同时熵权为 0，是正常结果（无区分度），不是 bug；
  - 必须先同向化+标准化，再算距离（欧氏距离对量纲敏感）；
  - 贴近度 C = D⁻/(D⁺+D⁻) 越接近 1 越优，不是百分制，不要乘 100；
  - 指标高度相关时 TOPSIS 会重复计数，先用 PCA 降维。
  - 正向指标 (x-min)/(max-min)；负向指标 (max-x)/(max-min)。

运行自测：python entropy_topsis.py
"""
import numpy as np


def entropy_weight(X, positive_idx=None):
    """熵权法。

    X: m 个方案 × n 个指标 原始矩阵。
    positive_idx: 指标方向列表（True=正向/效益型，False=负向/成本型），
                  None 时默认全部正向。
    返回（熵权向量, 标准化矩阵）。
    """
    X = np.asarray(X, dtype=float)
    m, n = X.shape
    if positive_idx is None:
        positive_idx = [True] * n
    assert len(positive_idx) == n

    # 同向化 + Min-Max 标准化到 [0.0001, 1]（避免 log(0)）
    Z = np.zeros_like(X, dtype=float)
    for j in range(n):
        col = X[:, j]
        rng = col.max() - col.min()
        if rng == 0:
            Z[:, j] = 1.0          # 全列相同 -> 无区分度
            continue
        if positive_idx[j]:
            Z[:, j] = (col - col.min()) / rng
        else:
            Z[:, j] = (col.max() - col) / rng
    Z = Z * 0.9999 + 0.0001

    # 信息熵
    P = Z / Z.sum(axis=0)
    E = -(P * np.log(P)).sum(axis=0) / np.log(m)
    d = 1 - E                       # 差异系数
    w = d / d.sum()                 # 熵权（全同列权重自然为 0）
    return w, Z


def topsis(Z, w):
    """对标准化矩阵 Z（同向化后）与权重 w 做 TOPSIS，返回贴近度 C（越大越优）。"""
    Z = np.asarray(Z, dtype=float)
    w = np.asarray(w, dtype=float)
    m = Z.shape[0]
    V = Z * w                                    # 加权规范化矩阵
    v_best, v_worst = V.max(axis=0), V.min(axis=0)
    # 同向化后统一取 max 为理想解、min 为负理想解
    D_plus = np.sqrt(((V - v_best) ** 2).sum(axis=1))
    D_minus = np.sqrt(((V - v_worst) ** 2).sum(axis=1))
    C = D_minus / (D_plus + D_minus + 1e-12)
    return C, D_plus, D_minus


def entropy_topsis(X, positive_idx=None):
    """一行式入口：原始矩阵 -> (熵权, 贴近度排名)。"""
    w, Z = entropy_weight(X, positive_idx)
    C, Dp, Dm = topsis(Z, w)
    return w, C


if __name__ == "__main__":
    # 自测：5 个方案 × 4 指标（第3个是负向指标，如成本）
    rng = np.random.default_rng(42)
    X = np.array([
        [0.82, 250, 0.31, 3.5],
        [0.75, 310, 0.29, 4.1],
        [0.91, 400, 0.27, 3.8],
        [0.68, 220, 0.33, 4.6],
        [0.85, 280, 0.30, 4.0],
    ])
    direction = [True, False, False, True]   # 产量↑ 成本↓ 损耗↑(示例负向) 评分↑
    w, Z = entropy_weight(X, direction)
    C, Dp, Dm = topsis(Z, w)
    print(f"熵权 = {np.round(w, 4)}  和 = {w.sum():.4f}")
    print(f"贴近度 C = {np.round(C, 4)}")
    rank = np.argsort(-C) + 1
    print(f"排名（从优到劣）= {rank}")
    assert abs(w.sum() - 1) < 1e-9 and C.min() >= 0 and C.max() <= 1
    # 自测：全同列指标 -> 熵权为 0 是正常行为
    X2 = X.copy(); X2[:, 0] = 5.0
    w2, _ = entropy_weight(X2, direction)
    assert abs(w2[0]) < 1e-12, "全同列指标熵权应为 0"
    print("全同列指标熵权 = 0（无区分度，正常）")
    print("entropy_topsis.py 自测通过")
