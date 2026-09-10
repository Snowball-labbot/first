# -*- coding: utf-8 -*-
"""模拟退火求解 TSP —— 组合优化经典组合（SA + 2-opt 邻域）。

适用：路径规划/排列类组合优化；也可替换邻域算子用于 VRP/调度。
防错：
  - 结果是近似解：固定种子 + 多次运行报告均值±标准差；
  - 初始温度/降温率需与问题尺度匹配（本实现自动按初始解波动定初温）；
  - TSP 解必须验证为一条 Hamilton 回路（无子回路——置换编码天然保证）。

运行自测：python sa_tsp.py
"""
import numpy as np


def tour_length(order, dist):
    """给定访问顺序与距离矩阵，返回回路总长（自动回到起点）。"""
    idx = np.r_[order, order[0]]
    return float(sum(dist[idx[i], idx[i + 1]] for i in range(len(order))))


def sa_tsp(dist, iters=20000, seed=42, T0=None, cooling=0.9995):
    """模拟退火 TSP。

    dist: n×n 对称距离矩阵。iters: 总迭代；T0: 初温（None 自动估计）；
    cooling: 降温系数（0.99~0.9999，越慢越精细）。
    返回 dict：best_order（从 0 城市出发的回路）、best_len、温度曲线、历史最优。
    """
    rng = np.random.default_rng(seed)
    n = dist.shape[0]
    cur = rng.permutation(n)
    cur_len = tour_length(cur, dist)
    if T0 is None:                       # 初温估计：邻域移动目标差的均值
        diffs = []
        for _ in range(200):
            a, b = rng.integers(0, n, 2)
            trial = cur.copy(); trial[[a, b]] = trial[[b, a]]
            diffs.append(abs(tour_length(trial, dist) - cur_len))
        T0 = max(float(np.mean(diffs)), 1.0)
    T, best, best_len = T0, cur.copy(), cur_len
    history, temps = [cur_len], [T]

    for _ in range(iters):
        i, j = rng.integers(0, n, 2)     # 交换邻域（也可换 2-opt/逆转片段）
        trial = cur.copy()
        trial[[i, j]] = trial[[j, i]]
        d = tour_length(trial, dist) - cur_len
        if d < 0 or rng.random() < np.exp(-d / T):   # Metropolis 准则
            cur, cur_len = trial, cur_len + d
            if cur_len < best_len:
                best, best_len = cur.copy(), cur_len
        T *= cooling
        history.append(best_len); temps.append(T)

    # 规范化输出：把 0 号城市转到队首
    k = int(np.where(best == 0)[0][0])
    best = np.r_[best[k:], best[:k]]
    return {"best_order": best, "best_len": tour_length(best, dist),
            "history": history, "temps": temps, "iters": iters, "seed": seed}


def euclid_dist(pts):
    """由坐标点生成对称距离矩阵。"""
    pts = np.asarray(pts, dtype=float)
    diff = pts[:, None, :] - pts[None, :, :]
    return np.sqrt((diff ** 2).sum(-1))


if __name__ == "__main__":
    rng = np.random.default_rng(5)
    pts = rng.uniform(0, 100, (30, 2))      # 30 城市随机分布
    dist = euclid_dist(pts)
    lens = []
    for seed in range(5):
        r = sa_tsp(dist, iters=30000, seed=seed)
        lens.append(r["best_len"])
        order = r["best_order"]
        assert sorted(order.tolist()) == list(range(30)), "必须是 Hamilton 回路（无子回路/无重复）"
    lens = np.array(lens)
    print(f"30 城 TSP：5 次独立运行回路长 = {np.round(lens, 2)}")
    print(f"均值 = {lens.mean():.2f} ± {lens.std():.2f}（标准差小说明结果稳定）")
    # 合理性参照：最近邻贪心
    cur, visited, nn_len = 0, {0}, 0.0
    while len(visited) < 30:
        nxt = min((j for j in range(30) if j not in visited), key=lambda j: dist[cur, j])
        nn_len += dist[cur, nxt]; cur = nxt; visited.add(nxt)
    nn_len += dist[cur, 0]
    print(f"最近邻贪心参照 = {nn_len:.2f}（SA 应不劣于它）")
    assert lens.mean() <= nn_len * 1.01
    print("sa_tsp.py 自测通过")
