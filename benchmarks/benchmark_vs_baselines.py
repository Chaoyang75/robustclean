"""基准测试：把单个方法、常见基线和 robustclean 共识放在一起比。

运行：``python benchmarks/benchmark_vs_baselines.py``
输出：控制台表格 + output/benchmark.csv + output/fig3_benchmark.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from robustclean import RobustCleaner, combine_consensus  # noqa: E402
from robustclean.detectors import DETECTOR_REGISTRY, DEFAULT_PARAMS  # noqa: E402
from robustclean.datasets import make_synthetic  # noqa: E402


def f1(pred: np.ndarray, true: np.ndarray) -> float:
    tp = int(np.sum(pred & true))
    fp = int(np.sum(pred & ~true))
    fn = int(np.sum(~pred & true))
    if tp == 0:
        return 0.0
    p = tp / (tp + fp)
    r = tp / (tp + fn)
    return 2 * p * r / (p + r)


def fp_rate(pred: np.ndarray, true: np.ndarray) -> float:
    clean = ~true
    return float(np.mean(pred[clean])) if clean.any() else 0.0


def mean_bias_after_removal(df: pd.DataFrame, pred: np.ndarray, true_mean: np.ndarray) -> float:
    """剔除后均值估计的相对误差（越小越好，衡量「有没有把分布搞坏」）。"""
    kept = df.to_numpy(dtype=float)[~pred]
    if kept.size == 0:
        return np.inf
    return float(np.mean(np.abs(kept.mean(axis=0) - true_mean) / (np.abs(true_mean) + 1.0)))


def baseline_zscore(X: np.ndarray, k: float = 3.0) -> np.ndarray:
    z = np.abs((X - X.mean(axis=0)) / (X.std(axis=0) + 1e-12))
    return z.max(axis=1) > k


def baseline_iqr(X: np.ndarray, k: float = 1.5) -> np.ndarray:
    q1, q3 = np.percentile(X, [25, 75], axis=0)
    iqr = q3 - q1
    mask = (X < q1 - k * iqr) | (X > q3 + k * iqr)
    return mask.any(axis=1)


def single_detector(df: pd.DataFrame, key: str) -> np.ndarray:
    X = df.to_numpy(dtype=float)
    res = DETECTOR_REGISTRY[key](X, **DEFAULT_PARAMS.get(key, {}))
    return res.flag


def consensus_mask(df: pd.DataFrame, vote_ratio: float = 0.5) -> np.ndarray:
    X = df.to_numpy(dtype=float)
    results = []
    for key in ("mad", "iqr", "mahalanobis", "pca", "knn", "lof", "iforest", "dbscan", "gmm"):
        res = DETECTOR_REGISTRY[key](X, **DEFAULT_PARAMS.get(key, {}))
        res.key = key
        results.append(res)
    return combine_consensus(results, vote_ratio=vote_ratio).flag


def main() -> int:
    scenarios = ["univariate", "multivariate", "cluster", "mixed"]
    n, d, cont = 800, 5, 0.05
    rows = []

    for scen in scenarios:
        df, true = make_synthetic(n=n, d=d, contamination=cont, kind=scen, seed=42)
        rng = np.random.default_rng(0)
        clean_df = pd.DataFrame(
            rng.normal(size=(5000, d)) * df.std().to_numpy() + df.mean().to_numpy(),
            columns=df.columns,
        )
        true_mean = clean_df.mean().to_numpy()
        X = df.to_numpy(dtype=float)

        methods = {
            "3σ（均值+标准差）": baseline_zscore(X),
            "IQR 1.5": baseline_iqr(X),
            "孤立森林": single_detector(df, "iforest"),
            "LOF": single_detector(df, "lof"),
            "马氏距离": single_detector(df, "mahalanobis"),
            "robustclean 共识(9 方法, 50% 投票)": consensus_mask(df, 0.5),
        }
        for name, pred in methods.items():
            rows.append({
                "场景": scen,
                "方法": name,
                "F1": round(f1(pred, true), 4),
                "召回": round(float(np.sum(pred & true) / max(1, int(true.sum()))), 4),
                "假阳性率": round(fp_rate(pred, true), 4),
                "剔除后均值偏差": round(mean_bias_after_removal(df, pred, true_mean), 5),
            })
        print(f"完成场景：{scen}")

    table = pd.DataFrame(rows)
    outdir = ROOT / "output"
    outdir.mkdir(exist_ok=True)
    table.to_csv(outdir / "benchmark.csv", index=False, encoding="utf-8-sig")

    print("\n=== 各场景 F1（越高越好）===")
    pivot = table.pivot(index="方法", columns="场景", values="F1")
    print(pivot.to_string())
    print("\n=== 各场景 剔除后均值偏差（越低越好）===")
    pivot2 = table.pivot(index="方法", columns="场景", values="剔除后均值偏差")
    print(pivot2.to_string())

    # 汇总平均
    agg = table.groupby("方法", as_index=False).agg(
        平均F1=("F1", "mean"),
        平均假阳性率=("假阳性率", "mean"),
        平均均值偏差=("剔除后均值偏差", "mean"),
    ).sort_values("平均F1", ascending=False)
    agg = agg.round(4)
    print("\n=== 四种场景平均 ===")
    print(agg.to_string(index=False))
    agg.to_csv(outdir / "benchmark_summary.csv", index=False, encoding="utf-8-sig")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from robustclean.report import setup_cjk_font

        setup_cjk_font(matplotlib)

        fig, ax = plt.subplots(figsize=(9, 4.2), dpi=150)
        methods_order = list(dict.fromkeys(table["方法"]))
        width = 0.8 / len(methods_order)
        xs = np.arange(len(scenarios))
        for i, m in enumerate(methods_order):
            vals = [float(table[(table["场景"] == s) & (table["方法"] == m)]["F1"].iloc[0]) for s in scenarios]
            ax.bar(xs + i * width - 0.4 + width / 2, vals, width=width, label=m)
        ax.set_xticks(xs)
        ax.set_xticklabels(scenarios)
        ax.set_ylabel("F1")
        ax.set_ylim(0, 1.0)
        ax.set_title("不同异常值类型下的检测 F1")
        ax.legend(fontsize=7, loc="upper left", ncol=2)
        fig.tight_layout()
        fig.savefig(outdir / "fig3_benchmark.png")
        print(f"\n图已保存：{outdir / 'fig3_benchmark.png'}")
    except Exception as exc:  # noqa: BLE001
        print(f"绘图跳过：{exc}")

    print(f"\n结果已保存：{outdir / 'benchmark.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
