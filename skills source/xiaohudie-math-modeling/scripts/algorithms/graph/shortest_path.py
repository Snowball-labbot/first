# -*- coding: utf-8 -*-
"""最短路径：Dijkstra（非负权单源）与 Floyd-Warshall（全对最短路）。

防错：
  - 负权边禁用 Dijkstra（改 Bellman-Ford，本实现给出告警）；
  - 明确有向/无向：无向图邻接矩阵对称；
  - 节点 >1000 时 Floyd 的 O(n³) 不可接受，改多次 Dijkstra；
  - 不可达节点距离记为 np.inf，报告中要说明。

运行自测：python shortest_path.py
"""
import heapq

import numpy as np


def dijkstra(adj, source):
    """单源最短路（非负权）。

    adj: n×n 权重矩阵，adj[i][j]=w，无边记 np.inf（对角线 0）。
    返回（dist 数组, 前驱数组 用于还原路径）。
    """
    adj = np.asarray(adj, dtype=float)
    n = adj.shape[0]
    if (adj[np.isfinite(adj) & (adj > 0)] ).size and (adj[np.isfinite(adj)] < 0).any():
        raise ValueError("检测到负权边，Dijkstra 不适用（用 Bellman-Ford）")
    dist = np.full(n, np.inf)
    prev = np.full(n, -1, dtype=int)
    dist[source] = 0.0
    heap = [(0.0, source)]
    done = np.zeros(n, dtype=bool)
    while heap:
        d, u = heapq.heappop(heap)
        if done[u]:
            continue
        done[u] = True
        for v in range(n):
            w = adj[u, v]
            if np.isfinite(w) and d + w < dist[v]:
                dist[v] = d + w
                prev[v] = u
                heapq.heappush(heap, (dist[v], v))
    return dist, prev


def floyd(adj):
    """全对最短路（O(n³)，n ≤ 数百）。返回 dist 矩阵（含 np.inf 不可达）。"""
    dist = np.asarray(adj, dtype=float).copy()
    n = dist.shape[0]
    np.fill_diagonal(dist, 0.0)
    for k in range(n):
        dist = np.minimum(dist, dist[:, [k]] + dist[[k], :])
    return dist


def restore_path(prev, target):
    """由 Dijkstra 前驱数组还原 source->target 路径。"""
    path, node = [], target
    while node != -1:
        path.append(int(node))
        node = prev[node]
    return path[::-1]


def make_undirected(adj):
    """对称化：无向图邻接矩阵。"""
    a = np.asarray(adj, dtype=float).copy()
    np.fill_diagonal(a, 0.0)
    return np.minimum(a, a.T)


if __name__ == "__main__":
    n = 6
    INF = np.inf
    adj = np.full((n, n), INF)
    np.fill_diagonal(adj, 0)
    edges = [(0, 1, 7), (0, 2, 9), (0, 5, 14), (1, 2, 10), (1, 3, 15),
             (2, 3, 11), (2, 5, 2), (3, 4, 6), (4, 5, 9)]
    for u, v, w in edges:      # 无向图
        adj[u, v] = adj[v, u] = w

    dist, prev = dijkstra(adj, 0)
    print(f"Dijkstra 0->4 最短距离 = {dist[4]:.2f}，路径 = {restore_path(prev, 4)}")
    assert dist[4] == 20  # 0->2->5->4 = 9+2+9

    fd = floyd(adj)
    print(f"Floyd 全对最短路（0->4）= {fd[0, 4]:.2f}")
    assert abs(fd[0, 4] - dist[4]) < 1e-9
    # 负权告警检查
    bad = adj.copy(); bad[1, 2] = -3
    try:
        dijkstra(bad, 0)
        raise AssertionError("应抛出负权异常")
    except ValueError as e:
        print(f"负权保护生效：{e}")
    print("shortest_path.py 自测通过")
