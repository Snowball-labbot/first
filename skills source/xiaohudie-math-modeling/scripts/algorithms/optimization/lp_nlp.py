# -*- coding: utf-8 -*-
"""线性规划与非线性的规划（scipy）—— 优化类首选精确算法。

防错（极易被扣分）：
  - scipy.optimize.linprog 默认最小化：最大化利润时目标系数取负，结果再还原；
  - scipy 不等式约束统一为 A_ub @ x <= b_ub（与 NLP 的 fun(x)>=0 方向不同，勿混）；
  - minimize 的不等式约束是 fun(x) >= 0，容量上限 x<=C 要写成 C-x>=0；
  - 不只信 success：最优解回代全部约束输出松弛量；
  - 每个变量必须有物理上下界。

运行自测：python lp_nlp.py
"""
import numpy as np


def solve_lp(c, A_ub=None, b_ub=None, A_eq=None, b_eq=None, bounds=None, maximize=False):
    """线性规划。maximize=True 时自动对目标取负并在结果还原真实目标值。"""
    from scipy.optimize import linprog
    c = np.asarray(c, dtype=float)
    res = linprog(-c if maximize else c, A_ub=A_ub, b_ub=b_ub,
                  A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    obj = (res.x @ c) if maximize else res.fun   # 还原真实目标值
    return res, obj


def solve_nlp(objective, x0, bounds=None, constraints=None, maximize=False):
    """非线性规划（SLSQP）。constraints 遵循 scipy 约定：
    不等式约束 fun(x) >= 0；等式约束 fun(x) == 0。
    返回（res, 约束校验明细）——自动回代每条约束输出松弛量，验证 success。"""
    from scipy.optimize import minimize
    obj = (lambda x: -objective(x)) if maximize else objective
    res = minimize(obj, x0, method="SLSQP", bounds=bounds, constraints=constraints or [])
    detail = []
    for c in (constraints or []):
        val = c["fun"](res.x)
        detail.append({"type": c.get("type"), "value": float(val),
                       "satisfied": (val >= -1e-6) if c.get("type") == "ineq" else abs(val) < 1e-6})
    return res, detail


if __name__ == "__main__":
    # ============ 自测1：LP 生产计划（最大化利润） ============
    # 两种产品 x1,x2；利润 3x1+5x2；约束：工时 x1<=40；原料 x2<=30；2x1+x2<=60
    res, obj = solve_lp(
        c=[3, 5], maximize=True,
        A_ub=[[1, 0], [0, 1], [2, 1]], b_ub=[40, 30, 60],
        bounds=[(0, None), (0, None)],
    )
    print(f"[LP] 最优解 x = {np.round(res.x, 4)}  最大利润 = {obj:.2f}")
    assert res.success and abs(obj - 195) < 1e-6   # 顶点 (15,30) -> 3*15+5*30 = 195

    # 回代约束输出松弛量（论文可直接引用）
    slack = np.array([40, 30, 60]) - np.array([[1, 0], [0, 1], [2, 1]]) @ res.x
    print(f"[LP] 约束松弛量 = {np.round(slack, 4)}（>=0 才可行）")
    assert (slack >= -1e-9).all()

    # ============ 自测2：NLP 带物理约束（含"无约束解违反物理"的演示） ============
    # 目标：max f(x) = 20*x - 0.4*x^2（如产量收益，x 为构件长度 mm）
    f = lambda x: 20 * x[0] - 0.4 * x[0] ** 2
    # 无约束最优：x* = 25mm
    from scipy.optimize import minimize_scalar
    unc = minimize_scalar(lambda v: -(20 * v - 0.4 * v ** 2))
    print(f"[NLP] 无约束最优 x* = {unc.x:.2f}mm")
    assert unc.x > 20
    # 物理约束：桌面模型高度限制 x <= 12mm（fun = 12 - x >= 0）
    cons = [{"type": "ineq", "fun": lambda x: 12 - x[0]}]
    res2, detail = solve_nlp(f, x0=[5.0], bounds=[(0, 1e9)], constraints=cons, maximize=True)
    print(f"[NLP] 约束后最优 x* = {res2.x[0]:.2f}mm  目标值 = {res2.fun:.2f}")
    print(f"[NLP] 约束校验：{detail}")
    # 教科书话术：无约束解违反物理限制，引入约束后取边界解
    assert abs(res2.x[0] - 12.0) < 1e-3, "约束激活时应取边界解 12mm"
    print("[NLP] 无约束解 25mm 违反物理限制（≤12mm），约束下最优解为 12mm —— 论文按此话术写")
    print("lp_nlp.py 自测通过")
