# -*- coding: utf-8 -*-
"""层次分析法 AHP（主观赋权）—— 评价类基础组件。

适用：需要体现专家经验/层次结构的权重确定。
防错（见 references/model-selection.md）：
  - 判断矩阵 ≤ 9×9，超过应拆多级层次；
  - 一致性比率 CR = CI/RI < 0.1 才通过，不通过必须调整矩阵（本实现自动提示）；
  - 只能从已有方案中选优，不能生成新方案。

运行自测：python ahp.py
"""
import numpy as np

# 1-9 阶随机一致性指标 RI 表（Saaty）
RI_TABLE = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12,
            6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45}


def ahp_weights(judgement_matrix):
    """由 n×n 判断矩阵求权重（特征值法），返回 (weights, CR, passed)。

    judgement_matrix[i][j] = 指标i 相对 指标j 的重要性（Saaty 1-9 标度，互反矩阵）。
    """
    A = np.asarray(judgement_matrix, dtype=float)
    n = A.shape[0]
    assert A.shape == (n, n), "判断矩阵必须是方阵"
    assert n <= 9, "判断矩阵超过 9 阶，一致性极难保证，请拆成多级层次"
    # 互反性检查
    if not np.allclose(A * A.T, 1, atol=0.01):
        print("[AHP][警告] 判断矩阵互反性校验偏差 >0.01，请检查 a_ij * a_ji = 1")

    eigvals, eigvecs = np.linalg.eig(A)
    k = int(np.argmax(eigvals.real))
    lam_max = eigvals[k].real
    w = np.abs(eigvecs[:, k].real)
    w = w / w.sum()                       # 归一化，和为 1

    CI = (lam_max - n) / (n - 1) if n > 1 else 0.0
    RI = RI_TABLE.get(n, 1.45)
    CR = CI / RI if RI > 0 else 0.0
    passed = CR < 0.1
    return w, CR, passed


def score_alternatives(alternatives_matrix, weights):
    """方案得分 = 权重向量 × 方案指标矩阵（每列一个指标，已同向化）。
    返回每个方案的综合得分（不改变指标方向，调用前先统一正向化）。"""
    X = np.asarray(alternatives_matrix, dtype=float)
    return X @ np.asarray(weights)


if __name__ == "__main__":
    # 自测：3 指标判断矩阵（经典教材示例）
    A = [[1,   3,   5],
         [1/3, 1,   3],
         [1/5, 1/3, 1]]
    w, cr, ok = ahp_weights(A)
    print(f"权重 = {np.round(w, 4)}  和 = {w.sum():.4f}")
    print(f"CR = {cr:.4f}（<0.1 通过：{ok}）")
    assert ok and abs(w.sum() - 1) < 1e-9

    # 自测：4 个方案 × 3 指标（已正向化）
    X = [[0.8, 0.5, 0.9],
         [0.6, 0.7, 0.8],
         [0.9, 0.4, 0.6],
         [0.5, 0.9, 0.7]]
    s = score_alternatives(X, w)
    print("方案综合得分 =", np.round(s, 4), " 最高分方案 =", int(np.argmax(s)) + 1)
    print("ahp.py 自测通过")
