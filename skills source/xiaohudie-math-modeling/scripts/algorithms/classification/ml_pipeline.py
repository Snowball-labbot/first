# -*- coding: utf-8 -*-
"""分类任务标准流水线（sklearn）—— 有标签数据的分类建模模板。

流程：训练/测试划分 -> 标准化（只 fit 训练集）-> 双模型对比（随机森林 vs Logistic）
-> 交叉验证 -> 混淆矩阵与 F1/AUC 报告。
防错：
  - 类别不平衡时 Accuracy 失效，看 F1/AUC-ROC（本实现同时输出）；
  - 标准化与编码在划分之后做；
  - 随机森林 feature_importances_ 对相关特征有偏，重要场景补 SHAP；
  - 随机森林外推弱，不适合趋势外推任务。

运行自测：python ml_pipeline.py
"""
import numpy as np


def classification_pipeline(X, y, test_ratio=0.25, seed=42, cv=5):
    """端到端分类流水线。返回 dict：模型对比表、最佳模型、评估指标、混淆矩阵。"""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                                 roc_auc_score)
    from sklearn.model_selection import cross_val_score, train_test_split
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    X = np.asarray(X, dtype=float)
    y = np.asarray(y)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=test_ratio,
                                          random_state=seed, stratify=y)
    models = {
        "随机森林": RandomForestClassifier(n_estimators=200, random_state=seed),
        "逻辑回归": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
    }
    report = {}
    for name, model in models.items():
        model.fit(Xtr, ytr)
        pred = model.predict(Xte)
        entry = {
            "accuracy": accuracy_score(yte, pred),
            "f1_macro": f1_score(yte, pred, average="macro"),
            "cv_mean": cross_val_score(model, Xtr, ytr, cv=cv).mean(),
            "confusion": confusion_matrix(yte, pred),
        }
        try:  # 二分类才有 AUC
            if len(np.unique(y)) == 2:
                entry["auc"] = roc_auc_score(yte, model.predict_proba(Xte)[:, 1])
        except Exception:
            pass
        report[name] = entry
    best_name = max(report, key=lambda k: report[k]["f1_macro"])
    importances = None
    if best_name == "随机森林":
        importances = models["随机森林"].feature_importances_
    return {"report": report, "best_name": best_name,
            "importances": importances, "models": models}


if __name__ == "__main__":
    from sklearn.datasets import make_classification
    X, y = make_classification(n_samples=400, n_features=6, n_informative=4,
                               n_redundant=1, weights=[0.65, 0.35],
                               random_state=7, flip_y=0.03)
    r = classification_pipeline(X, y)
    for name, e in r["report"].items():
        auc = f"  AUC={e['auc']:.4f}" if "auc" in e else ""
        print(f"[{name}] Acc={e['accuracy']:.4f}  F1(macro)={e['f1_macro']:.4f}  "
              f"CV={e['cv_mean']:.4f}{auc}")
        print(f"        混淆矩阵 = \n{e['confusion']}")
    print(f"最佳模型：{r['best_name']}（不平衡数据以 F1 为准，而非 Accuracy）")
    if r["importances"] is not None:
        print(f"特征重要性 = {np.round(r['importances'], 3)}")
        assert len(r["importances"]) == X.shape[1]
    assert r["report"][r["best_name"]]["f1_macro"] > 0.6
    print("ml_pipeline.py 自测通过")
