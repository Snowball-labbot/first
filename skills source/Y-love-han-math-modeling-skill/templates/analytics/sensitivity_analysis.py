# -*- coding: utf-8 -*-
"""
sensitivity_analysis.py — 模型验证与灵敏度分析
用途：多方法交叉验证、Sobol 全局灵敏度、蒙特卡洛稳健性、Tornado 图
理论分析：Sobol 方差分解、Saltelli 采样、Jansen 估计器
"""
import numpy as np
import matplotlib.pyplot as plt
from utils import (save_fig, COLORS, RNG, confidence_interval,
                   bootstrap_ci, OUTPUT_DIR)


# ============================================================
# 单因素灵敏度分析
# ============================================================

def single_factor_sensitivity(base_params, param_name, model_func,
                              variation_range=(-0.5, 0.5), n_points=21):
    """单因素灵敏度分析

    Args:
        base_params: dict, 基准参数 {name: value}
        param_name: str, 要变化的参数名
        model_func: callable, 模型函数 model_func(params) -> float
        variation_range: tuple, 变化比例范围（默认 ±50%）
        n_points: int, 采样点数

    Returns:
        ratios, outputs, sensitivity_coeff
    """
    ratios = np.linspace(variation_range[0], variation_range[1], n_points)
    outputs = []
    base_output = model_func(base_params)
    for ratio in ratios:
        params = base_params.copy()
        params[param_name] = base_params[param_name] * (1 + ratio)
        outputs.append(model_func(params))
    outputs = np.array(outputs)
    delta_y = (np.max(outputs) - np.min(outputs))
    delta_y_rel = delta_y / abs(base_output) if base_output != 0 else 0
    delta_p = variation_range[1] - variation_range[0]
    sensitivity_coeff = delta_y_rel / delta_p if delta_p != 0 else 0
    return ratios, outputs, sensitivity_coeff


# ============================================================
# Tornado 图（多参数灵敏度对比）
# ============================================================

def plot_tornado(param_names, base_params, model_func, variation=0.2):
    """绘制 Tornado 图

    Tornado 图以基准输出值为中心，向左右各延伸参数变化引起的偏差。
    参数按影响幅度从大到小排序。

    Returns:
        fig: matplotlib figure
    """
    base_output = model_func(base_params)
    sensitivities = []
    for name in param_names:
        delta = base_params[name] * variation
        p_low, p_high = base_params.copy(), base_params.copy()
        p_low[name] -= delta
        p_high[name] += delta
        y_low = model_func(p_low) - base_output
        y_high = model_func(p_high) - base_output
        sensitivities.append((name, y_low, y_high))

    sensitivities.sort(key=lambda x: abs(x[2]) + abs(x[1]), reverse=True)

    fig, ax = plt.subplots(figsize=(8, max(4, len(param_names) * 0.6)))
    pos_label_set, neg_label_set = False, False
    for i, (name, yl, yh) in enumerate(sensitivities):
        if yh >= 0:
            ax.barh(i, yh, height=0.6, color=COLORS[0], alpha=0.8,
                    label='+变化' if not pos_label_set else '')
            pos_label_set = True
        else:
            ax.barh(i, yh, height=0.6, color=COLORS[1], alpha=0.8,
                    label='-变化' if not neg_label_set else '')
            neg_label_set = True
        if yl <= 0:
            ax.barh(i, yl, height=0.6, color=COLORS[1], alpha=0.8,
                    label='-变化' if not neg_label_set else '')
            neg_label_set = True
        else:
            ax.barh(i, yl, height=0.6, color=COLORS[0], alpha=0.8,
                    label='+变化' if not pos_label_set else '')
            pos_label_set = True
    ax.axvline(0, color='black', linewidth=0.8, linestyle='--')
    ax.set_yticks(range(len(sensitivities)))
    ax.set_yticklabels([s[0] for s in sensitivities])
    ax.set_xlabel('输出相对基准值的变化')
    ax.set_title(f'Tornado 图（参数变化 ±{variation * 100:.0f}%）')
    ax.legend()
    plt.tight_layout()
    return fig


# ============================================================
# Sobol 全局灵敏度分析
# ============================================================

def sobol_sensitivity(param_names, param_ranges, model_func, n_samples=1024):
    """Sobol 全局灵敏度分析

    优先使用 SALib（需 pip install SALib），不可用时使用自实现版本。
    自实现使用 scipy Sobol 准随机序列 + Jansen/Saltelli 估计器 + Bootstrap CI。

    Args:
        param_names: list, 参数名称
        param_ranges: dict, {name: (lower, upper)}
        model_func: callable, model_func(param_dict) -> float
        n_samples: int, 基础样本量（推荐 1024 或 2048）

    Returns:
        S1, ST: dict, 一阶和总阶 Sobol 指数
        S1_conf, ST_conf: dict, 95% 置信区间
    """
    try:
        from SALib.analyze import sobol as sobol_analyze
        from SALib.sample import saltelli
        problem = {
            'num_vars': len(param_names),
            'names': param_names,
            'bounds': [param_ranges[p] for p in param_names]
        }
        param_values = saltelli.sample(problem, n_samples,
                                       calc_second_order=True)
        Y = np.array([model_func(dict(zip(param_names, X)))
                      for X in param_values])
        Si = sobol_analyze.analyze(problem, Y, print_to_console=False)
        return (
            dict(zip(param_names, Si['S1'])),
            dict(zip(param_names, Si['ST'])),
            dict(zip(param_names, Si['S1_conf'])),
            dict(zip(param_names, Si['ST_conf'])),
        )
    except ImportError:
        return _sobol_fallback(param_names, param_ranges, model_func, n_samples)


def _sobol_fallback(param_names, param_ranges, model_func, n_samples):
    """自实现 Sobol（scipy Sobol 序列 + Jansen/Saltelli 估计器）"""
    from scipy.stats import qmc

    d = len(param_names)
    sampler = qmc.Sobol(d=d, scramble=True, seed=42)
    all_samples = sampler.random(2 * n_samples)
    A, B = all_samples[:n_samples], all_samples[n_samples:]

    def _scale(samples):
        scaled = np.zeros_like(samples)
        for i, name in enumerate(param_names):
            lo, hi = param_ranges[name]
            scaled[:, i] = samples[:, i] * (hi - lo) + lo
        return scaled

    A_scaled, B_scaled = _scale(A), _scale(B)

    def _eval_batch(X_batch):
        return np.array([model_func(dict(zip(param_names, X)))
                         for X in X_batch])

    Y_A, Y_B = _eval_batch(A_scaled), _eval_batch(B_scaled)
    total_var = np.var(np.concatenate([Y_A, Y_B]))
    if total_var <= 0:
        return ({n: 0.0 for n in param_names},
                {n: 0.0 for n in param_names},
                {n: 0.0 for n in param_names},
                {n: 0.0 for n in param_names})

    n_boot = 1000
    S1, ST, S1_conf, ST_conf = {}, {}, {}, {}

    for i, name in enumerate(param_names):
        AB_i = A_scaled.copy()
        AB_i[:, i] = B_scaled[:, i]
        Y_AB_i = _eval_batch(AB_i)
        S1[name] = np.mean(Y_B * (Y_AB_i - Y_A)) / total_var
        ST[name] = np.mean((Y_A - Y_AB_i) ** 2) / (2 * total_var)
        s1_boots, st_boots = [], []
        N = len(Y_A)
        for _ in range(n_boot):
            idx = RNG.choice(N, N, replace=True)
            s1_boots.append(
                np.mean(Y_B[idx] * (Y_AB_i[idx] - Y_A[idx])) / total_var)
            st_boots.append(
                np.mean((Y_A[idx] - Y_AB_i[idx]) ** 2) / (2 * total_var))
        S1_conf[name] = 1.96 * np.std(s1_boots)
        ST_conf[name] = 1.96 * np.std(st_boots)

    return S1, ST, S1_conf, ST_conf


# ============================================================
# 蒙特卡洛稳健性验证
# ============================================================

def monte_carlo_robustness(model_func, param_ranges, n_samples=10000):
    """蒙特卡洛稳健性验证

    Args:
        model_func: callable, model_func(params) -> float
        param_ranges: dict, {name: (lower, upper)}
        n_samples: int, 采样次数

    Returns:
        dict: {mean, std, median, ci_95, ci_99, all_results,
              param_records, param_names}——param_records 与 all_results
              逐行对应（同一组采样参数），供 3D 分布图使用（避免
              参数-输出错配）。
    """
    results = []
    param_records = []
    param_names = list(param_ranges.keys())
    for _ in range(n_samples):
        params = {}
        for name, (lo, hi) in param_ranges.items():
            params[name] = RNG.uniform(lo, hi)
        param_records.append([params[name] for name in param_names])
        results.append(model_func(params))

    results = np.array(results)
    mean, ci_low, ci_high = confidence_interval(results, confidence=0.95)
    _, ci99_low, ci99_high = confidence_interval(results, confidence=0.99)

    return {
        'mean': mean,
        'std': np.std(results),
        'median': np.median(results),
        'ci_95': (ci_low, ci_high),
        'ci_99': (ci99_low, ci99_high),
        'all_results': results,
        'param_records': np.array(param_records),
        'param_names': param_names,
    }


# ============================================================
# 可视化
# ============================================================

def plot_sensitivity_curve(ratios, outputs, param_name, base_value):
    """绘制单因素灵敏度曲线"""
    fig, ax = plt.subplots(figsize=(8, 5))
    param_values = base_value * (1 + ratios)
    ax.plot(param_values, outputs, 'o-', color=COLORS[0], linewidth=2)
    ax.axvline(base_value, color='red', linestyle='--', alpha=0.5,
               label=f'基准值 = {base_value:.3g}')
    ax.set_xlabel(f'{param_name} 的取值')
    ax.set_ylabel('模型输出')
    ax.set_title(f'{param_name} 的灵敏度分析')
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig


def plot_sobol_results(S1, ST, S1_conf, ST_conf):
    """绘制 Sobol 指数对比图"""
    names = list(S1.keys())
    x = np.arange(len(names))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    bars1 = ax.bar(x - width / 2, [S1[n] for n in names], width,
                   label='一阶指数 $S_i$', color=COLORS[0], alpha=0.8)
    bars2 = ax.bar(x + width / 2, [ST[n] for n in names], width,
                   label='总阶指数 $S_{Ti}$', color=COLORS[1], alpha=0.8)

    # 误差棒
    ax.errorbar(x - width / 2, [S1[n] for n in names],
                yerr=[S1_conf[n] for n in names],
                fmt='none', ecolor='black', capsize=3)
    ax.errorbar(x + width / 2, [ST[n] for n in names],
                yerr=[ST_conf[n] for n in names],
                fmt='none', ecolor='black', capsize=3)

    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylabel('Sobol 指数')
    ax.set_title('全局灵敏度分析（Sobol 方法）')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    return fig


def plot_mc_distribution(results, ci_95, ci_99):
    """绘制蒙特卡洛结果分布"""
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(results, bins=50, density=True, alpha=0.7,
            color=COLORS[0], edgecolor='white')
    ax.axvline(ci_95[0], color=COLORS[1], linestyle='--', linewidth=2,
               label=f'95% CI: [{ci_95[0]:.4f}, {ci_95[1]:.4f}]')
    ax.axvline(ci_95[1], color=COLORS[1], linestyle='--', linewidth=2)
    ax.axvline(ci_99[0], color=COLORS[2], linestyle=':', linewidth=2,
               label=f'99% CI: [{ci_99[0]:.4f}, {ci_99[1]:.4f}]')
    ax.axvline(ci_99[1], color=COLORS[2], linestyle=':', linewidth=2)
    ax.axvline(np.mean(results), color='red', linewidth=2,
               label=f'均值 = {np.mean(results):.4f}')
    ax.set_xlabel('模型输出')
    ax.set_ylabel('概率密度')
    ax.set_title(f'蒙特卡洛模拟结果分布（N={len(results)}）')
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig


# ============================================================
# 3D 灵敏度图（阶段 6 门禁(4)：Sobol 3D / MC 3D / Pareto 3D，锁9 分批第 2 批）
# 文件名含 3d 标识 + 强制双视角（45° 主视图 + 90° 俯视图）
# ============================================================

def plot_sobol_3d_interaction(param_names, param_ranges, model_func,
                              pair=('a', 'b'), n_grid=30):
    """
    NOTE: 仅在结果具备真实三维语义（曲面/轨迹/前沿）时调用；
    二维或表格可表达时不使用 3D——见 references/paper-and-visuals.md「三维图使用边界」。
    双参数交互 3D 曲面（Sobol 3D 交互曲面）

    固定其他参数为基准值，绘制 pair 两参数网格上的模型输出曲面，
    直观展示交互效应（曲面非可加分解 = 强交互）。

    Returns:
        fig: matplotlib figure（含 45° 主视图 + 90° 俯视图两个子图）
    """
    fig = plt.figure(figsize=(14, 6))
    p1, p2 = pair
    lo1, hi1 = param_ranges[p1]
    lo2, hi2 = param_ranges[p2]
    x = np.linspace(lo1, hi1, n_grid)
    y = np.linspace(lo2, hi2, n_grid)
    X, Y = np.meshgrid(x, y)
    Z = np.zeros_like(X)
    base = {k: (param_ranges[k][0] + param_ranges[k][1]) / 2
            for k in param_ranges if k not in pair}
    for i in range(n_grid):
        for j in range(n_grid):
            params = dict(base)
            params[p1], params[p2] = X[i, j], Y[i, j]
            try:
                Z[i, j] = model_func(params)
            except Exception:
                Z[i, j] = np.nan
    for k, (elev, azim, title) in enumerate(
            [(30, 45, '45°主视图'), (90, 0, '90°俯视图')]):
        ax = fig.add_subplot(1, 2, k + 1, projection='3d')
        surf = ax.plot_surface(X, Y, Z, cmap='viridis', alpha=0.85,
                               linewidth=0, antialiased=True)
        ax.view_init(elev=elev, azim=azim)
        ax.set_xlabel(p1); ax.set_ylabel(p2); ax.set_zlabel('模型输出')
        ax.set_title(f'双参数交互 3D 曲面（{title}）')
        fig.colorbar(surf, ax=ax, shrink=0.6, label='模型输出')
    fig.suptitle(f'Sobol 3D 交互曲面：{p1} × {p2}')
    plt.tight_layout()
    return fig


def plot_mc_3d_distribution(mc_results, param_ranges, key_params=None):
    """
    NOTE: 仅在结果具备真实三维语义（曲面/轨迹/前沿）时调用；
    二维或表格可表达时不使用 3D——见 references/paper-and-visuals.md「三维图使用边界」。
    MC 稳健性 3D 分布图

    以 MC 采样中变化最大的 2 个关键参数为 x/y、模型输出为 z（颜色编码），
    展示输出在参数空间中的稳健分布（集中 = 稳健，弥散 = 敏感）。

    Args:
        mc_results: monte_carlo_robustness 的返回 dict（含 'param_records'
                    与 'all_results' 逐行对应）；或 (param_records, outputs)
                    元组直接使用。
        param_ranges: {name: (lo, hi)}
        key_params: 指定的 2 个关键参数名（默认取 param_ranges 前 2 个）

    Returns:
        fig: matplotlib figure（双视角）
    """
    if isinstance(mc_results, tuple):
        recs, outputs = mc_results
        # 元组入参（recs, outputs）不携带参数名元数据：轴标签回退为
        # 通用占位，避免 NameError；需要真实轴名时请传完整 MC 结果 dict。
        label_names = ['param1', 'param2']
    else:
        # ⚠️ 必须用 monte_carlo_robustness 记录的 param_records（与输出
        #    逐行对应）——禁止重新采样参数坐标（会造成 x/y 与 z 错配）。
        recs = np.asarray(mc_results['param_records'])
        outputs = np.asarray(mc_results['all_results'])
        all_names = mc_results.get('param_names',
                                   list(param_ranges.keys()))
        names = key_params or all_names[:2]
        idx = [all_names.index(n) for n in names[:2] if n in all_names]
        recs = recs[:, idx] if len(idx) == 2 else recs[:, :2]
        # ⚠️ 轴标签必须用"实际选中的列名"——在 key_params
        #    含无效名（回退到前 2 列）时仍用无效名做轴标签，图例与数据错配
        label_names = ([all_names[i] for i in idx]
                       if len(idx) == 2 else list(all_names[:2]))
    fig = plt.figure(figsize=(14, 6))
    for k, (elev, azim, title) in enumerate(
            [(30, 45, '45°主视图'), (90, 0, '90°俯视图')]):
        ax = fig.add_subplot(1, 2, k + 1, projection='3d')
        # ⚠️ 输出为单极值量 → 用顺序色 viridis（RdBu 中间白带对单极值
        #    数据无意义且暗示正负语义，非最适——科研标准为单极值用顺序色）
        sc = ax.scatter(recs[:, 0], recs[:, 1], outputs,
                        c=outputs, cmap='viridis', s=8, alpha=0.6)
        ax.view_init(elev=elev, azim=azim)
        ax.set_xlabel(label_names[0] if label_names else 'param1')
        ax.set_ylabel(label_names[1] if len(label_names) > 1 else 'param2')
        ax.set_zlabel('模型输出')
        ax.set_title(f'MC 稳健性 3D 分布（{title}）')
        fig.colorbar(sc, ax=ax, shrink=0.6, label='模型输出')
    fig.suptitle('蒙特卡洛稳健性 3D 分布（集中=稳健，弥散=敏感）')
    plt.tight_layout()
    return fig


def plot_pareto_3d(pareto_results, third_metric=None):
    """
    NOTE: 仅在结果具备真实三维语义（曲面/轨迹/前沿）时调用；
    二维或表格可表达时不使用 3D——见 references/paper-and-visuals.md「三维图使用边界」。
    Pareto 前沿 3D 曲面/散点

    x=复杂度 y=性能 z=第三指标（默认：性能/复杂度的边际效率，
    即 性能 ÷ 复杂度 的比值作为第三维），展示三维权衡结构。

    Args:
        pareto_results: pareto_frontier_analysis 的返回 dict
        third_metric: 可选 dict {name: value}，作为第三维

    Returns:
        fig: matplotlib figure（双视角）
    """
    names = list(pareto_results.keys())
    cx = np.array([pareto_results[n]['complexity'] for n in names],
                  dtype=float)
    py = np.array([pareto_results[n]['performance'] for n in names],
                  dtype=float)
    if third_metric is not None:
        zz = np.array([third_metric.get(n, 0.0) for n in names], dtype=float)
    else:
        zz = np.array([py[i] / (cx[i] + 1e-12) for i in range(len(names))],
                      dtype=float)
    fig = plt.figure(figsize=(14, 6))
    for k, (elev, azim, title) in enumerate(
            [(30, 45, '45°主视图'), (90, 0, '90°俯视图')]):
        ax = fig.add_subplot(1, 2, k + 1, projection='3d')
        is_ours = [n == '本文方法' for n in names]
        sizes = [300 if o else 120 for o in is_ours]
        sc = ax.scatter(cx, py, zz, s=sizes, c=range(len(names)),
                        cmap='viridis', alpha=0.9, edgecolors='black')
        for i, n in enumerate(names):
            ax.text(cx[i], py[i], zz[i], n, fontsize=9,
                    fontweight='bold' if is_ours[i] else 'normal')
        ax.view_init(elev=elev, azim=azim)
        ax.set_xlabel('模型复杂度'); ax.set_ylabel('模型性能')
        ax.set_zlabel('边际效率 (性能/复杂度)')
        ax.set_title(f'复杂度-性能-效率 3D 权衡（{title}）')
    fig.suptitle('Pareto 前沿 3D 分析（本文方法大点标记）')
    plt.tight_layout()
    return fig


# ============================================================
# 假设松弛分析（特等奖关键——性能 vs 假设违反程度）
# ============================================================

def hypothesis_relaxation_analysis(base_params, model_func,
                                    assumption_name, relax_func,
                                    relaxation_levels=11):
    """假设松弛分析：逐条放松假设（0%完全满足→100%完全违反），
    绘制性能退化曲线，展示模型如何优雅退化而非突然崩溃。

    Args:
        base_params: dict, 基准参数
        model_func: callable, model_func(params) -> float
        assumption_name: str, 假设名称
        relax_func: callable, relax_func(base_params, level) -> params
                     level in [0, 1], 0=完全满足, 1=完全违反
        relaxation_levels: int, 松弛级别数（默认11，含0%和100%）

    Returns:
        dict: {levels, outputs, degradation_pct, acceptable_threshold}
    """
    levels = np.linspace(0, 1, relaxation_levels)
    base_output = model_func(base_params)
    outputs = []
    for level in levels:
        relaxed_params = relax_func(base_params, level)
        try:
            outputs.append(model_func(relaxed_params))
        except Exception:
            outputs.append(np.nan)
    outputs = np.array(outputs)
    degradation = (outputs - base_output) / (abs(base_output) + 1e-12) * 100
    acceptable = 5.0
    return {
        'assumption_name': assumption_name,
        'levels': levels,
        'outputs': outputs,
        'base_output': base_output,
        'degradation_pct': degradation,
        'acceptable_threshold': acceptable,
    }


def plot_hypothesis_relaxation(relaxation_results, n_assumptions=2):
    """绘制假设松弛退化曲线（支持多条假设同时展示）"""
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = [COLORS[0], COLORS[1], COLORS[3], COLORS[2]]
    for i, result in enumerate(relaxation_results[:n_assumptions]):
        color = colors[i % len(colors)]
        ax.plot(result['levels'] * 100, result['degradation_pct'],
                'o-', color=color, linewidth=2.5, markersize=8,
                label=result['assumption_name'])
        for pct_thresh, style in [(5, '--'), (10, ':')]:
            idx = np.argmax(np.abs(result['degradation_pct']) >= pct_thresh)
            if idx > 0:
                ax.axvline(result['levels'][idx] * 100,
                          color=color, linestyle=style, alpha=0.4)
    ax.axhline(5, color='orange', linestyle='--', linewidth=1.5,
               label='可接受退化线 (5%)')
    ax.axhline(10, color='red', linestyle=':', linewidth=1.5,
               label='不可接受退化线 (10%)')
    ax.fill_between([0, 100], -5, 5, alpha=0.08, color='green')
    ax.set_xlabel('假设违反程度 (%)')
    ax.set_ylabel('性能退化 (%)')
    ax.set_title('假设松弛分析——模型性能退化曲线')
    ax.legend(loc='lower right', fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 100)
    plt.tight_layout()
    return fig


# ============================================================
# 复杂度-性能 Pareto 前沿分析（特等奖关键——论证"复杂度值得"）
# ============================================================

def pareto_frontier_analysis(model_versions, test_data, metric_func,
                              complexity_metric='n_params'):
    """复杂度-性能 Pareto 前沿分析

    Args:
        model_versions: dict, {name: (model_func, complexity_value)}
        test_data: 测试数据
        metric_func: callable, metric_func(model_func, test_data) -> score
        complexity_metric: str, 复杂度度量名

    Returns:
        dict: {name: {complexity, performance, is_pareto_optimal}}
    """
    results = {}
    for name, (model_func, complexity) in model_versions.items():
        try:
            perf = metric_func(model_func, test_data)
        except Exception:
            perf = np.nan
        results[name] = {'complexity': complexity, 'performance': perf}
    names = list(results.keys())
    for i, name_a in enumerate(names):
        is_pareto = True
        for j, name_b in enumerate(names):
            if i == j:
                continue
            a, b = results[name_a], results[name_b]
            if (b['complexity'] <= a['complexity'] and
                b['performance'] >= a['performance'] and
                (b['complexity'] < a['complexity'] or
                 b['performance'] > a['performance'])):
                is_pareto = False
                break
        results[name_a]['is_pareto_optimal'] = is_pareto
    return results


def plot_pareto_frontier(pareto_results, our_method_name='本文方法'):
    """绘制复杂度-性能 Pareto 前沿图"""
    fig, ax = plt.subplots(figsize=(9, 6))
    names, complexities, performances = [], [], []
    for name, data in pareto_results.items():
        names.append(name)
        complexities.append(data['complexity'])
        performances.append(data['performance'])
        marker = 's' if data.get('is_pareto_optimal') else 'o'
        size = 250 if name == our_method_name else 150
        color = COLORS[0] if name == our_method_name else (
            COLORS[2] if data.get('is_pareto_optimal') else COLORS[1])
        edgewidth = 3 if name == our_method_name else 1
        ax.scatter(data['complexity'], data['performance'],
                  marker=marker, s=size, c=color, edgecolors=COLORS[6],
                  linewidth=edgewidth, zorder=5 if name == our_method_name else 1,
                  alpha=0.9)
        ax.annotate(name, (data['complexity'], data['performance']),
                   fontsize=9 if name == our_method_name else 8,
                   fontweight='bold' if name == our_method_name else 'normal',
                   textcoords='offset points', xytext=(5, 8),
                   ha='left', va='bottom')
    pareto_names = [n for n, d in pareto_results.items()
                    if d.get('is_pareto_optimal')]
    if pareto_names:
        # ⚠️ 前沿连线必须先按复杂度排序——按 dict 插入顺序
        #    连线，插入顺序与复杂度无关时连线来回折返，图形误导
        front_pts = sorted(
            (pareto_results[n]['complexity'], pareto_results[n]['performance'])
            for n in pareto_names
            if not np.isnan(pareto_results[n]['performance']))
        ax.plot([p[0] for p in front_pts], [p[1] for p in front_pts],
                '--', color='gray', alpha=0.5, linewidth=1.5,
                label='Pareto 前沿')
    ax.set_xlabel('模型复杂度')
    ax.set_ylabel('模型性能')
    ax.set_title('复杂度-性能 Pareto 前沿分析')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig


if __name__ == '__main__':
    from utils import harden_console
    harden_console()
    print("=" * 60)
    print("模型验证与灵敏度分析（冲刺档完整版）")
    print("=" * 60)

    def example_model(params):
        a, b, c = params['a'], params['b'], params['c']
        return a * np.sin(b) + np.exp(-c * a)

    example_params = {'a': 2.0, 'b': 1.5, 'c': 0.5}
    example_ranges = {'a': (0.5, 5.0), 'b': (0.0, np.pi), 'c': (0.1, 2.0)}
    param_names = list(example_ranges.keys())

    print("\n[1/5] Tornado 单因素灵敏度分析...")
    fig1 = plot_tornado(param_names, example_params, example_model)
    save_fig(fig1, 'figS1_tornado.png')

    print("[2/5] Sobol 全局灵敏度分析...")
    S1, ST, S1_c, ST_c = sobol_sensitivity(
        param_names, example_ranges, example_model, n_samples=512)
    fig2 = plot_sobol_results(S1, ST, S1_c, ST_c)
    save_fig(fig2, 'figS2_sobol.png')
    print(f"  S1: {S1}, ST: {ST}")

    # 锁9 分批第 2 批：Sobol 3D 交互曲面（双视角，文件名含 3d）
    print("[2.5/5] Sobol 3D 交互曲面...")
    fig2_3d = plot_sobol_3d_interaction(param_names, example_ranges,
                                        example_model, pair=('a', 'b'))
    save_fig(fig2_3d, 'figS2_3d_sobol.png')

    print("[3/5] 蒙特卡洛稳健性分析...")
    mc = monte_carlo_robustness(example_model, example_ranges, n_samples=2000)
    fig3 = plot_mc_distribution(mc['all_results'], mc['ci_95'], mc['ci_99'])
    save_fig(fig3, 'figS3_mc.png')

    # 锁9 分批第 2 批：MC 稳健性 3D 分布（双视角）
    print("[3.5/5] MC 稳健性 3D 分布...")
    fig3_3d = plot_mc_3d_distribution(mc, example_ranges,
                                      key_params=['a', 'b'])
    save_fig(fig3_3d, 'figS3_3d_mc.png')

    print("[4/5] 假设松弛分析...")
    results_hypo = []
    for i, (assump_name, relax_fn) in enumerate([
        ('假设1: 参数独立性',
         lambda p, lv: {**p, 'a': p['a'] + lv * p['a'] * np.sin(p['b']) * 0.5}),
        ('假设2: 线性响应',
         lambda p, lv: {**p, 'b': p['b'] * (1 + lv * 0.3 * np.sign(np.sin(p['b'])))}),
    ]):
        res = hypothesis_relaxation_analysis(
            example_params, example_model, assump_name, relax_fn)
        results_hypo.append(res)
        print(f"  {assump_name}: 最大退化={res['degradation_pct'][-1]:.1f}%")
    fig4 = plot_hypothesis_relaxation(results_hypo, n_assumptions=2)
    save_fig(fig4, 'figS4_hypothesis_relaxation.png')

    print("[5/5] Pareto 前沿分析...")
    test_data = [{'a': RNG.uniform(0.5, 5.0), 'b': RNG.uniform(0, np.pi),
                   'c': RNG.uniform(0.1, 2.0)} for _ in range(50)]
    model_versions = {
        '简单线性': (lambda p: 2*p['a'] + 0.5*p['b'], 3),
        '中等非线性': (lambda p: p['a']*np.sin(p['b']*0.8), 12),
        '复杂方法A': (lambda p: p['a']*np.sin(p['b'])*np.exp(-0.3*p['c']*p['a']), 45),
        '本文方法': (example_model, 28),
    }
    def perf_metric(mf, td):
        return -np.mean([abs(mf(d) - 1.5) for d in td])
    pareto = pareto_frontier_analysis(model_versions, test_data, perf_metric)
    fig5 = plot_pareto_frontier(pareto, '本文方法')
    save_fig(fig5, 'figS5_pareto.png')

    # 锁9 分批第 2 批：Pareto 3D 权衡（双视角）
    print("[5.5/5] Pareto 3D 权衡...")
    fig5_3d = plot_pareto_3d(pareto)
    save_fig(fig5_3d, 'figS5_3d_pareto.png')

    print("\n✅ 全 5+3 张灵敏度图已生成（含 Sobol/MC/Pareto 3D，锁9 分批第 2 批）")
    print("详细使用方法参见整合版 references/validation-by-model-type.md 与 references/extended-competition-playbook.md。")
