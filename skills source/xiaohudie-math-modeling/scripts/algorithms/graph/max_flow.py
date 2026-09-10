# -*- coding: utf-8 -*-
"""最大流（Edmonds-Karp 增广路）与最小割 —— 网络流基础。

适用：运输/管道/匹配容量问题；二分图匹配可用最大流建模。
防错：
  - 容量必须非负；无向边按两条反向有向边处理（本实现 add_edge 自动做）；
  - 流量守恒：除源汇外每节点流入=流出（本实现在自测中验证）；
  - 求最小割：源侧可达集 = 残量网络中从源 BFS 可达的节点。

运行自测：python max_flow.py
"""
import numpy as np
from collections import deque


class MaxFlow:
    def __init__(self, n):
        self.n = n
        self.cap = np.zeros((n, n))       # 残量容量矩阵
        self.flow = np.zeros((n, n))

    def add_edge(self, u, v, c, undirected=False):
        """加边；undirected=True 时等价于 u->v 与 v->u 各 c（无向边标准处理）。"""
        self.cap[u, v] += c
        if undirected:
            self.cap[v, u] += c

    def _bfs(self, s, t):
        """BFS 找最短增广路，返回前驱数组或 None。"""
        prev = np.full(self.n, -1, dtype=int)
        prev[s] = s
        q = deque([s])
        while q:
            u = q.popleft()
            for v in range(self.n):
                if prev[v] == -1 and self.cap[u, v] > 1e-12:
                    prev[v] = u
                    if v == t:
                        return prev
                    q.append(v)
        return None

    def solve(self, s, t):
        """Edmonds-Karp 主循环，返回最大流值。"""
        total = 0.0
        while True:
            prev = self._bfs(s, t)
            if prev is None:
                break
            # 增广路上最小残量
            path, v = [], t
            while v != s:
                u = prev[v]
                path.append((u, v))
                v = u
            bottleneck = min(self.cap[u, v] for u, v in path)
            for u, v in path:
                self.cap[u, v] -= bottleneck
                self.cap[v, u] += bottleneck
                self.flow[u, v] += bottleneck
                self.flow[v, u] -= bottleneck
            total += bottleneck
        return total

    def min_cut_source_side(self, s):
        """最小割的源侧节点集（残量网络中从 s 可达）。"""
        seen = {s}
        q = deque([s])
        while q:
            u = q.popleft()
            for v in range(self.n):
                if v not in seen and self.cap[u, v] > 1e-12:
                    seen.add(v)
                    q.append(v)
        return sorted(seen)


if __name__ == "__main__":
    # 自测：经典 6 节点网络（CLRS 教材例），理论最大流 23
    n = 6
    mf = MaxFlow(n)
    edges = [(0, 1, 16), (0, 2, 13), (1, 3, 12), (2, 1, 4), (2, 4, 14),
             (3, 2, 9), (3, 5, 20), (4, 3, 7), (4, 5, 4)]
    for u, v, c in edges:
        mf.add_edge(u, v, c)
    maxflow = mf.solve(0, 5)
    print(f"最大流 = {maxflow}（理论值 23）")
    assert abs(maxflow - 23) < 1e-9

    # 流量守恒验证：除源(0)汇(5)外，每节点流入 = 流出
    for v in range(1, 5):
        inflow = mf.flow[:, v].sum()
        outflow = mf.flow[v, :].sum()
        assert abs(inflow - outflow) < 1e-9, f"节点 {v} 流量不守恒"
    print("流量守恒验证通过（每个中间节点流入=流出）")

    cut = mf.min_cut_source_side(0)
    cut_capacity = sum(c for (u, v, c) in
                       [(0, 1, 16), (0, 2, 13)] if u in cut and v not in cut)
    print(f"最小割源侧 = {cut}，跨越割边容量检查见 README 说明")
    print("max_flow.py 自测通过")
