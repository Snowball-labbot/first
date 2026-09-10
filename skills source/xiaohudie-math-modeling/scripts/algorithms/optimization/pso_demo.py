# -*- coding: utf-8 -*-
"""粒子群优化 PSO —— 连续空间优化效果好，实现简单。

适用：连续变量、目标光滑性无要求的优化；离散变量需特殊编码（改用 GA/SA）。
防错：
  - 惯性权重 w、学习因子 c1/c2 有常用经验值（本实现默认 w=0.7298, c1=c2=1.4962，
    Clerc 收敛因子参数，文献常用）；
  - 不保证全局最优：固定种子 + 多次运行；
  - 高维（>20）易早熟，先降维/分组。

运行自测：python pso_demo.py
"""
import numpy as np


def pso_optimize(fitness, dim, bounds, pop_size=40, iters=300,
                 w=0.7298, c1=1.4962, c2=1.4962, seed=42, maximize=False):
    """标准 PSO（全局拓扑）。

    fitness(x)->float；bounds [(lo,hi),...]；maximize=True 求最大。
    返回 dict：best_x, best_f, 每代最优曲线。
    """
    rng = np.random.default_rng(seed)
    lo = np.array([b[0] for b in bounds], dtype=float)
    hi = np.array([b[1] for b in bounds], dtype=float)
    sign = -1 if maximize else 1              # 内部统一最小化

    X = lo + rng.random((pop_size, dim)) * (hi - lo)
    V = (rng.random((pop_size, dim)) - 0.5) * (hi - lo) * 0.2
    F = np.array([sign * fitness(x) for x in X])      # 内部最小化
    Pbest, Pf = X.copy(), F.copy()
    g = int(np.argmin(Pf)); Gbest, Gf = Pbest[g].copy(), Pf[g]
    history = [Gf]

    for _ in range(iters):
        r1, r2 = rng.random((pop_size, dim)), rng.random((pop_size, dim))
        V = w * V + c1 * r1 * (Pbest - X) + c2 * r2 * (Gbest - X)
        X = np.clip(X + V, lo, hi)
        F = np.array([sign * fitness(x) for x in X])
        upd = F < Pf
        Pbest[upd], Pf[upd] = X[upd], F[upd]
        g = int(np.argmin(Pf))
        if Pf[g] < Gf:
            Gbest, Gf = Pbest[g].copy(), Pf[g]
        history.append(Gf)
    return {"best_x": Gbest, "best_f": Gf * sign, "history": history, "seed": seed}


if __name__ == "__main__":
    # 自测1：Rastrigin（多峰，理论最小 0 @ 原点）
    def rastrigin(x):
        return sum(xi ** 2 - 10 * np.cos(2 * np.pi * xi) + 10 for xi in x)

    fits = []
    for seed in range(5):
        r = pso_optimize(rastrigin, dim=2, bounds=[(-5.12, 5.12), (-5.12, 5.12)], seed=seed)
        fits.append(r["best_f"])
    fits = np.array(fits)
    print(f"Rastrigin 2D：5 次运行最优值 = {np.round(fits, 4)}（理论 0）")
    print(f"均值 = {fits.mean():.4f} ± {fits.std():.4f}")
    assert fits.mean() < 5
    # 自测2：最大化
    r2 = pso_optimize(lambda x: 10 - (x[0] + 3) ** 2, dim=1, bounds=[(-10, 10)],
                      maximize=True, seed=0)
    print(f"最大化：x* = {r2['best_x'][0]:.4f}（理论 -3），f* = {r2['best_f']:.4f}（理论 10）")
    assert abs(r2["best_x"][0] + 3) < 0.05
    print("pso_demo.py 自测通过")
