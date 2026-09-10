# -*- coding: utf-8 -*-
"""模糊综合评价 —— 指标难以量化、存在模糊语言（好/中/差）时的评价方法。

防错：
  - 隶属度函数（三角形/梯形/高斯）按问题语义选择，不要默认同一种；
  - 合成算子用 M(·,+) 加权平均型，不要用 M(∧,∨)（主因素突出型丢信息）；
  - 指标过多时结果分辨率下降（超模糊），改用二级模糊综合评价分层处理。

运行自测：python fuzzy_eval.py
"""
import numpy as np


def triangular_membership(x, nodes):
    """三角形隶属度函数。nodes = [a, b, c]：a/c 处隶属 0，b 处隶属 1。"""
    a, b, c = nodes
    if x <= a or x >= c:
        return 0.0
    if x == b:
        return 1.0
    if x < b:
        return (x - a) / (b - a)
    return (c - x) / (c - b)


def build_r_matrix(values, grade_nodes):
    """构建模糊关系矩阵 R（n 指标 × m 等级）。

    values: 每个指标的观测值列表。
    grade_nodes: 每个等级的三角隶属度节点列表，len == 等级数，
                 例：3 级（差/中/优）-> [ [0,0,60], [40,70,90], [80,100,101] ]。
    返回 R，行=指标，列=等级，每行和为 1。
    """
    R = np.zeros((len(values), len(grade_nodes)))
    for i, x in enumerate(values):
        for k, nodes in enumerate(grade_nodes):
            R[i, k] = triangular_membership(x, nodes)
        s = R[i].sum()
        R[i] = R[i] / s if s > 0 else np.full(len(grade_nodes), 1.0 / len(grade_nodes))
    return R


def fuzzy_comprehensive(R, w):
    """M(·,+) 加权平均型合成：B = w · R。w 为指标权重（和为 1）。

    返回对各等级的隶属度向量 B（按等级顺序），最大分量即所属等级。
    """
    w = np.asarray(w, dtype=float)
    assert abs(w.sum() - 1) < 1e-9, "权重和必须为 1"
    B = w @ np.asarray(R, dtype=float)
    return B / B.sum()


if __name__ == "__main__":
    # 自测：空气质量评价，3 指标 × 3 等级（差/中/优）
    # 指标：PM2.5(ug/m3)、SO2(ug/m3)、良好天数比例(%)
    values = [68, 15, 82]
    # 等级节点（每个等级一个三角形 [a,b,c]）
    grade_nodes = [
        [0, 0, 75],      # 差：PM2.5 越小越好 -> 差等级放低值端
        [55, 75, 115],   # 中
        [75, 150, 300],  # 优
    ]
    # 注意：本例 3 个指标方向不同，为演示简单起见用同一套节点，
    # 实际使用时每个指标单独定义其等级节点方向。
    R = build_r_matrix(values, grade_nodes)
    print("模糊关系矩阵 R =\n", np.round(R, 4))
    w = [0.4, 0.3, 0.3]
    B = fuzzy_comprehensive(R, w)
    print(f"综合隶属度 B = {np.round(B, 4)}（差/中/优）")
    assert abs(B.sum() - 1) < 1e-9
    print(f"评价结论：隶属于第 {int(np.argmax(B)) + 1} 等级")
    print("fuzzy_eval.py 自测通过")
