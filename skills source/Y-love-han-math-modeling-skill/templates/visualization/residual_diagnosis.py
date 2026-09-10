from __future__ import annotations
try:
    from .plotting_common import save_figure
except ImportError:  # 单文件复制到项目后与 plotting_common.py 同目录的松散导入回退
    from plotting_common import save_figure

# Acklam 逆标准正态 CDF 有理近似（|相对误差| < 1.15e-9），
# 使本模板只依赖 numpy 即可绘制正态分位图。
_A = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
      1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
_B = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
      6.680131188771972e+01, -1.328068155288572e+01]
_C = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
      -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
_D = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
      3.754408661907416e+00]
_P_LOW = 0.02425
_P_HIGH = 1.0 - _P_LOW


def _norm_ppf(probability: float) -> float:
    import numpy as np

    if probability <= 0.0 or probability >= 1.0:
        raise ValueError("probability must be within (0, 1)")
    if probability < _P_LOW:
        q = np.sqrt(-2.0 * np.log(probability))
        return (((((_A[0] * q + _A[1]) * q + _A[2]) * q + _A[3]) * q + _A[4]) * q + _A[5]) / \
               ((((_B[0] * q + _B[1]) * q + _B[2]) * q + _B[3]) * q + _B[4])
    if probability > _P_HIGH:
        q = np.sqrt(-2.0 * np.log(1.0 - probability))
        return -(((((_A[0] * q + _A[1]) * q + _A[2]) * q + _A[3]) * q + _A[4]) * q + _A[5]) / \
               ((((_B[0] * q + _B[1]) * q + _B[2]) * q + _B[3]) * q + _B[4])
    q = probability - 0.5
    r = q * q
    return (((((_C[0] * r + _C[1]) * r + _C[2]) * r + _C[3]) * r + _C[4]) * r + _C[5]) * q / \
           ((((_D[0] * r + _D[1]) * r + _D[2]) * r + _D[3]) * r + 1.0)


def _draw(fig, data):
    import numpy as np

    fitted = data.get("fitted")
    residuals = data.get("residuals")
    if not isinstance(fitted, list) or not isinstance(residuals, list) or not fitted:
        raise ValueError("residual_diagnosis input requires non-empty 'fitted' and 'residuals'")
    if len(fitted) != len(residuals):
        raise ValueError("'fitted' and 'residuals' must have equal length")
    fit_values = np.asarray(fitted, dtype=float)
    res_values = np.asarray(residuals, dtype=float)
    sigma = float(res_values.std(ddof=1)) if res_values.size > 1 else 0.0
    standardized = res_values / sigma if sigma > 0 else res_values

    # 面板一：残差-拟合值散点 + ±2σ 带（异方差/系统性偏差可视化）
    ax1 = fig.add_subplot(121)
    ax1.scatter(fit_values, res_values, s=16, color="#0072B2", alpha=0.75)
    ax1.axhline(0.0, color="#555555", linewidth=1.0)
    for multiple in (2.0, -2.0):
        ax1.axhline(multiple * sigma, color="#D55E00",
                    linewidth=1.1, linestyle="--")
    ax1.set_xlabel(data["units"].get("x", "fitted value"))
    ax1.set_ylabel(data["units"].get("y", "residual"))
    ax1.set_title("Residual vs fitted (±2σ)")

    # 面板二：标准化残差正态分位图（重尾/偏态识别）
    ax2 = fig.add_subplot(122)
    ordered = np.sort(standardized)
    count = ordered.size
    probabilities = (np.arange(1, count + 1) - 0.375) / (count + 0.25)
    theoretical = np.asarray([_norm_ppf(float(item)) for item in probabilities])
    ax2.scatter(theoretical, ordered, s=16, color="#0072B2", alpha=0.75)
    line_xy = [float(theoretical.min()), float(theoretical.max())]
    ax2.plot(line_xy, line_xy, "--", color="#D55E00", linewidth=1.2,
             label="y = x reference")
    ax2.set_xlabel("theoretical normal quantile")
    ax2.set_ylabel("standardized residual")
    ax2.set_title("Normal Q-Q of residuals")
    ax2.legend(frameon=False, fontsize=8)


def generate(data, output_dir):
    return save_figure(data, output_dir, role="residual_diagnosis", drawer=_draw)
