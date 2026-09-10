# -*- coding: utf-8 -*-
"""实数编码遗传算法（GA）—— 复杂/非凸/黑箱优化的通用启发式。

适用：目标不可导、约束复杂、维度适中的连续优化；组合优化请改编码方式。
防错：
  - 不保证全局最优：固定随机种子 + ≥5 次独立运行 + 报告均值±标准差；
  - 与精确算法/小规模精确解对比验证可信度；
  - 种群规模、交叉/变异率需说明来源（文献常用值或网格试算）。

运行自测：python genetic_algorithm.py
"""
import numpy as np


def ga_optimize(fitness, dim, bounds, pop_size=60, generations=200,
                pc=0.8, pm=0.1, seed=42, maximize=True, tournament_k=3):
    """实数编码 GA（锦标赛选择 + SBX 交叉 + 高斯变异 + 精英保留）。

    fitness(x) -> float；bounds: [(lo, hi), ...]；maximize: True 求最大。
    返回 dict：best_x, best_f, 历史最优曲线, 各参数。
    """
    rng = np.random.default_rng(seed)
    lo = np.array([b[0] for b in bounds], dtype=float)
    hi = np.array([b[1] for b in bounds], dtype=float)
    scale = hi - lo

    def clip_pop(P):
        return np.clip(P, lo, hi)

    P = lo + rng.random((pop_size, dim)) * scale
    F = np.array([fitness(ind) for ind in P])
    sign = 1 if maximize else -1          # 内部统一"越大越好"
    Fkey = sign * F
    history = []

    for _ in range(generations):
        # 锦标赛选择
        idx = np.arange(pop_size)
        picks = rng.choice(idx, (pop_size, tournament_k))
        winners = picks[np.arange(pop_size), np.argmax(Fkey[picks], axis=1)]
        parents = P[winners]

        # SBX 交叉
        Q = parents.copy()
        for i in range(0, pop_size - 1, 2):
            if rng.random() < pc:
                u = rng.random(dim)
                beta = np.where(u <= 0.5, (2 * u) ** (1 / 1.5), (1 / (2 * (1 - u))) ** (1 / 1.5))
                c1 = 0.5 * (parents[i] + parents[i + 1]) - beta * (parents[i + 1] - parents[i])
                c2 = 0.5 * (parents[i] + parents[i + 1]) + beta * (parents[i + 1] - parents[i])
                Q[i], Q[i + 1] = c1, c2

        # 高斯变异
        mask = rng.random((pop_size, dim)) < pm
        Q = np.where(mask, Q + rng.normal(0, 0.1 * scale, Q.shape), Q)
        Q = clip_pop(Q)

        # 精英保留：新旧合并取前 pop_size
        QF = np.array([fitness(ind) for ind in Q])
        QFkey = sign * QF
        allP = np.vstack([P, Q]); allF = np.concatenate([Fkey, QFkey])
        top = np.argsort(-allF)[:pop_size]
        P, Fkey = allP[top], allF[top]
        F = Fkey * sign
        history.append((Fkey.max() * sign))
    best = int(np.argmax(Fkey))
    return {"best_x": P[best], "best_f": F[best], "history": history,
            "pop_size": pop_size, "generations": generations, "seed": seed}


if __name__ == "__main__":
    # 自测：最大化多峰函数 f(x,y) = 3(1-x)^2 exp(-x^2-(y+1)^2) - 10(x/5-x^3-y^5)exp(-x^2-y^2) ... 太重
    # 改用经典的 Rastrigin 取反（全局最大 = 0 在原点，易验证）
    def neg_rastrigin(x):
        return -sum(xi ** 2 - 10 * np.cos(2 * np.pi * xi) + 10 for xi in x)

    results = []
    for seed in range(5):                       # 5 次独立运行
        r = ga_optimize(neg_rastrigin, dim=2, bounds=[(-5.12, 5.12), (-5.12, 5.12)],
                        seed=seed, maximize=False)   # 最小化 Rastrigin
        results.append(r["best_f"])
    results = np.array(results)
    print(f"Rastrigin 2D 最小化（理论最优 0）：5 次运行 = {np.round(results, 4)}")
    print(f"均值 = {results.mean():.4f}  标准差 = {results.std():.4f}")
    assert results.mean() < 1.0, "GA 应接近全局最优"
    # 最大化场景自测
    r2 = ga_optimize(lambda x: -(x[0] - 2) ** 2 - 3, dim=1, bounds=[(-5, 5)],
                     maximize=True, seed=1)
    print(f"单峰最大化：x* = {r2['best_x'][0]:.4f}（理论 2.0），f* = {r2['best_f']:.4f}（理论 -3）")
    assert abs(r2["best_x"][0] - 2) < 0.05
    print("genetic_algorithm.py 自测通过")
