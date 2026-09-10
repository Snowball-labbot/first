# -*- coding: utf-8 -*-
"""
statistical_tests.py — 统计显著性检验
用途：方法对比的统计检验、效应量计算、多重比较校正、检验力分析
输入：各方法的输出结果（CSV/数组）
输出：统计检验报告（含 p 值、效应量、检验力）
"""
import numpy as np
from scipy import stats
from utils import RNG, OUTPUT_DIR


def t_test_two_groups(group_a, group_b, alpha=0.05):
    """两组均值对比：自动选择 t 检验或 Mann-Whitney U

    自动判断正态性（Shapiro-Wilk），选择参数/非参数检验。
    报告统计量、p 值、效应量（Cohen's d 或 r）。

    Returns:
        dict: {test, statistic, p_value, effect_size_name, effect_size, significant}
    """
    group_a, group_b = np.asarray(group_a), np.asarray(group_b)
    p_norm_a = stats.shapiro(group_a)[1] if len(group_a) >= 3 else 0
    p_norm_b = stats.shapiro(group_b)[1] if len(group_b) >= 3 else 0

    if p_norm_a > alpha and p_norm_b > alpha:
        # 正态 → t 检验（含方差齐性检验）
        equal_var = stats.levene(group_a, group_b)[1] > alpha
        t_stat, p_val = stats.ttest_ind(group_a, group_b, equal_var=equal_var)
        pooled_std = np.sqrt(
            ((len(group_a) - 1) * np.var(group_a, ddof=1) +
             (len(group_b) - 1) * np.var(group_b, ddof=1)) /
            (len(group_a) + len(group_b) - 2)
        )
        cohen_d = ((np.mean(group_a) - np.mean(group_b)) / pooled_std
                   if pooled_std > 0 else 0)
        return {
            'test': 't-test', 'statistic': t_stat, 'p_value': p_val,
            'effect_size_name': "Cohen's d", 'effect_size': cohen_d,
            'significant': p_val < alpha
        }
    else:
        # 非正态 → Mann-Whitney U
        u_stat, p_val = stats.mannwhitneyu(
            group_a, group_b, alternative='two-sided')
        n_total = len(group_a) + len(group_b)
        z_stat = abs(u_stat - len(group_a) * len(group_b) / 2) / \
                 np.sqrt(len(group_a) * len(group_b) * n_total / 12)
        effect_r = z_stat / np.sqrt(n_total)
        return {
            'test': 'Mann-Whitney U', 'statistic': u_stat, 'p_value': p_val,
            'effect_size_name': 'r', 'effect_size': effect_r,
            'significant': p_val < alpha
        }


def friedman_test(results_matrix, alpha=0.05):
    """多组方法对比：Friedman 检验 + Nemenyi 事后检验

    Args:
        results_matrix: 2D array (n_datasets, n_methods)

    Returns:
        dict: {chi2, p_value, significant, nemenyi}
    """
    results_matrix = np.asarray(results_matrix)
    n_datasets, n_methods = results_matrix.shape
    chi2, p_val = stats.friedmanchisquare(
        *[results_matrix[:, i] for i in range(n_methods)])

    result = {'chi2': chi2, 'p_value': p_val,
              'significant': p_val < alpha, 'nemenyi': None}

    if p_val < alpha and n_methods > 2:
        ranks = np.zeros_like(results_matrix, dtype=float)
        for i in range(n_datasets):
            order = np.argsort(results_matrix[i])[::-1]
            for rank, idx in enumerate(order):
                ranks[i, idx] = rank + 1
        avg_ranks = np.mean(ranks, axis=0)
        # Nemenyi 检验临界值 q_α（studentized range 分布，df=∞，采用 q/√2 约定，
        # 即 Nemenyi 原文约定：CD = q_α,k·√[k(k+1)/(6N)]）。来源：Demšar (2006)
        # "Statistical Comparisons of Classifiers over Multiple Data Sets"。
        # k=3 → 2.344；k=4 → 2.569；k=5 → 2.728；k=6 → 2.850。
        q_alpha = {0.05: {2: 1.960, 3: 2.344, 4: 2.569, 5: 2.728,
                          6: 2.850, 7: 2.949, 8: 3.031, 9: 3.102, 10: 3.164}}
        q_val = q_alpha.get(alpha, {}).get(n_methods, 3.164)
        cd = q_val * np.sqrt(n_methods * (n_methods + 1) / (6 * n_datasets))
        result['nemenyi'] = {
            'avg_ranks': avg_ranks,
            'critical_difference': cd
        }
    return result


def bonferroni_correction(p_values, alpha=0.05):
    """Bonferroni 多重比较校正

    Returns:
        dict: {corrected_alpha, significant_mask, n_tests, original_p_values}
    """
    p_values = np.asarray(p_values)
    n_tests = len(p_values)
    corrected_alpha = alpha / n_tests
    return {
        'corrected_alpha': corrected_alpha,
        'significant': p_values < corrected_alpha,
        'n_tests': n_tests,
        'original_p_values': p_values
    }


def power_analysis(effect_size, n_samples, alpha=0.05, n_groups=2):
    """检验力分析（Power Analysis）

    ⚠️ 双样本 t 检验的非中心参数为 d·√(n/2)（n = 每组样本数），
    与统计标准公式一致。

    Returns:
        dict: {power, adequate (>=0.8), required_n}
    """
    n_per_group = n_samples / n_groups
    df = n_samples * n_groups - n_groups
    ncp_val = effect_size * np.sqrt(n_per_group / 2)
    t_crit = stats.t.ppf(1 - alpha / 2, df)
    power = (1 - stats.t.cdf(t_crit - ncp_val, df) +
             stats.t.cdf(-t_crit - ncp_val, df))

    required_n = n_samples
    for n in range(5, 1000):
        df_n = n * n_groups - n_groups
        ncp_n = effect_size * np.sqrt(n / n_groups / 2)
        t_crit_n = stats.t.ppf(1 - alpha / 2, df_n)
        power_n = (1 - stats.t.cdf(t_crit_n - ncp_n, df_n) +
                   stats.t.cdf(-t_crit_n - ncp_n, df_n))
        if power_n >= 0.8:
            required_n = n
            break

    return {'power': power, 'adequate': power >= 0.8,
            'required_n': required_n}


def generate_report(test_results):
    """生成统计检验报告"""
    report = []
    report.append("=" * 60)
    report.append("统计显著性检验报告")
    report.append("=" * 60)

    for name, result in test_results.items():
        report.append(f"\n{name}:")
        report.append(f"  检验方法: {result.get('test', 'N/A')}")
        # ⚠️ statistic/p_value 缺失时直接对字符串做 :.4f 会抛
        #    ValueError（f-string 不能格式化 'N/A'）——先判类型再格式化
        stat = result.get('statistic', 'N/A')
        report.append(f"  统计量: {stat:.4f}" if isinstance(stat, (int, float))
                      else f"  统计量: {stat}")
        pval = result.get('p_value', 'N/A')
        report.append(f"  p 值: {pval:.6f}" if isinstance(pval, (int, float))
                      else f"  p 值: {pval}")
        if 'effect_size_name' in result:
            es = result.get('effect_size', 'N/A')
            report.append(f"  效应量 ({result['effect_size_name']}): "
                          f"{es:.4f}" if isinstance(es, (int, float))
                          else f"  效应量 ({result['effect_size_name']}): {es}")
        report.append(f"  显著性: "
                      f"{'✅ 显著' if result.get('significant') else '❌ 不显著'}")

    report.append("\n" + "=" * 60)
    return '\n'.join(report)


if __name__ == '__main__':
    from utils import harden_console
    harden_console()
    print("=" * 60)
    print("统计显著性检验")
    print("=" * 60)

    # 示例：两组对比
    data_a = RNG.normal(10, 2, 50)
    data_b = RNG.normal(11, 2, 50)
    result = t_test_two_groups(data_a, data_b)
    print(f"\n两组对比示例:")
    print(f"  检验: {result['test']}")
    print(f"  p 值: {result['p_value']:.4f}")
    print(f"  效应量 ({result['effect_size_name']}): "
          f"{result['effect_size']:.3f}")
    print(f"  显著: {'是' if result['significant'] else '否'}")

    # 示例：多方法 Friedman
    matrix = np.column_stack([
        RNG.normal(0.85, 0.05, 10),
        RNG.normal(0.88, 0.05, 10),
        RNG.normal(0.90, 0.05, 10)
    ])
    fr = friedman_test(matrix)
    print(f"\n多方法对比示例 (Friedman):")
    print(f"  χ² = {fr['chi2']:.3f}, p = {fr['p_value']:.4f}")
    if fr['nemenyi']:
        print(f"  平均秩次: {fr['nemenyi']['avg_ranks']}")
        print(f"  临界差异 CD = {fr['nemenyi']['critical_difference']:.3f}")

    # ============================================================
    # ⛔ 统计检验报告落盘（阶段 6 门禁(2) + 锁 4(6) 强制要求）
    #    实际赛题中：将真实检验结果 dict 传入 generate_report 后写盘；
    #    示例运行也生成样例报告，保证门禁可核验。
    # ============================================================
    test_results = {
        '两组对比 (示例)': result,
        '多方法 Friedman (示例)': {
            'test': 'Friedman',
            'statistic': fr['chi2'],
            'p_value': fr['p_value'],
            'significant': fr['significant'],
        },
    }
    report = generate_report(test_results)
    report += "\n\n【检验力分析】\n"
    pw = power_analysis(effect_size=0.5, n_samples=50)
    report += (f"  power = {pw['power']:.3f} "
               f"({'✅ ≥0.8' if pw['adequate'] else '⚠️ <0.8，需增加样本'})\n")
    report += (f"  达到 0.8 所需样本量: {pw['required_n']}\n")
    report += "\n" + "=" * 60 + "\n✅ 统计检验完成"
    report_path = OUTPUT_DIR / '结果' / 'statistical_test_report.txt'
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n统计检验报告已保存至: {report_path}")
