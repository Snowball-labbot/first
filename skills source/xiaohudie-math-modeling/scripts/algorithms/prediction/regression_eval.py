# -*- coding: utf-8 -*-
"""多元回归建模与诊断（OLS / 岭回归）—— 预测与归因的基础模型。

适用：多个影响因素 -> 连续目标，样本 30+，需要可解释系数。
防错：
  - 多重共线性：VIF > 10 用岭回归或删特征（本实现自动算 VIF）；
  - 残差应正态、方差齐、无自相关（本实现输出基本诊断）；
  - 外推超出训练数据范围必须声明风险；
  - 预测准确率高 ≠ 因果关系。

运行自测：python regression_eval.py
"""
import numpy as np


def vif(X):
    """各列方差膨胀因子（含截距处理；X 不含截距列）。"""
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import r2_score
    X = np.asarray(X, dtype=float)
    vifs = []
    for j in range(X.shape[1]):
        others = np.delete(X, j, axis=1)
        reg = LinearRegression().fit(others, X[:, j])
        r2 = r2_score(X[:, j], reg.predict(others))
        vifs.append(1.0 / max(1 - r2, 1e-9))
    return np.asarray(vifs)


def regression_eval(X, y, test_ratio=0.25, seed=42, ridge_alpha=None):
    """训练/测试划分 -> 拟合（OLS 或岭回归）-> 指标与诊断。

    返回 dict：model, coef, intercept, R2/RMSE/MAE/MAPE（测试集）, VIF。
    ridge_alpha=None 用 OLS；多重共线性时给 alpha（如 1.0）。
    """
    from sklearn.linear_model import LinearRegression, Ridge
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error

    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=test_ratio, random_state=seed)
    # 标准化只 fit 训练集（数据泄露防范）
    mu, sigma = Xtr.mean(0), Xtr.std(0)
    sigma[sigma == 0] = 1.0
    Xtr_s, Xte_s = (Xtr - mu) / sigma, (Xte - mu) / sigma

    model = (Ridge(alpha=ridge_alpha) if ridge_alpha else LinearRegression())
    model.fit(Xtr_s, ytr)
    pred = model.predict(Xte_s)
    resid = yte - pred

    return {
        "model": model,
        "coef": model.coef_, "intercept": model.intercept_,
        "R2": r2_score(yte, pred),
        "RMSE": float(np.sqrt(mean_squared_error(yte, pred))),
        "MAE": mean_absolute_error(yte, pred),
        "MAPE%": np.mean(np.abs(resid / np.where(yte == 0, 1e-9, yte))) * 100,
        "VIF": vif(X),
        "resid_normal_p": _shapiro_p(resid),
    }


def _shapiro_p(x):
    try:
        from scipy.stats import shapiro
        return float(shapiro(x)[1])
    except Exception:
        return float("nan")


if __name__ == "__main__":
    rng = np.random.default_rng(11)
    n = 120
    x1 = rng.uniform(10, 100, n)
    x2 = 0.5 * x1 + rng.normal(0, 5, n)        # 与 x1 强相关 -> 触发共线性
    x3 = rng.uniform(0, 50, n)
    y = 3 + 2.0 * x1 + 1.5 * x3 + rng.normal(0, 8, n)   # x2 无真实贡献

    print("== OLS ==")
    r = regression_eval(np.c_[x1, x2, x3], y)
    print(f"R2={r['R2']:.4f}  RMSE={r['RMSE']:.3f}  MAE={r['MAE']:.3f}  MAPE={r['MAPE%']:.2f}%")
    print(f"VIF = {np.round(r['VIF'], 2)}（>10 严重共线）")
    print(f"标准化系数 = {np.round(r['coef'], 3)}（x2 无贡献应为小值）")
    print(f"残差正态检验 p = {r['resid_normal_p']:.3f}")
    assert r["R2"] > 0.8
    assert r["VIF"].max() > 10, "设计矩阵应出现共线性告警"

    print("== 岭回归（alpha=1.0，共线性场景） ==")
    r2 = regression_eval(np.c_[x1, x2, x3], y, ridge_alpha=1.0)
    print(f"R2={r2['R2']:.4f}  系数 = {np.round(r2['coef'], 3)}")
    print("regression_eval.py 自测通过")
