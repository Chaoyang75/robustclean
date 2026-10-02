"""基本功能与效果验证。

可以直接运行：``python tests/test_robustclean.py``
（没装 pytest 也能跑；装了 pytest 就 ``pytest tests``。）
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from robustclean import RobustCleaner, combine_consensus  # noqa: E402
from robustclean.datasets import make_synthetic, make_synthetic_grouped  # noqa: E402


def _f1(pred: np.ndarray, true: np.ndarray) -> float:
    tp = int(np.sum(pred & true))
    fp = int(np.sum(pred & ~true))
    fn = int(np.sum(~pred & true))
    if tp == 0:
        return 0.0
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    return 2 * precision * recall / (precision + recall)


def test_single_detector_flags_injected_outliers():
    """单变量极端值：MAD 检测器至少要抓住一半以上。"""
    df, true = make_synthetic(n=600, d=3, contamination=0.05, kind="univariate", seed=3)
    cleaner = RobustCleaner(methods=["mad", "iqr"], vote_ratio=0.5).fit(df)
    assert _f1(cleaner.consensus_.flag, true) > 0.5, "单变量异常值检测效果不足"


def test_consensus_beats_3sigma_on_hard_case():
    """核心卖点：单变量看不出来的异常值（次特征方向偏移），共识必须明显赢过 3σ。

    这类异常值每个变量上只偏 1.5–2.5 个标准差，均值±3σ 原理上抓不到，
    但联合分布上它们是离群的——这正是多方法共识存在的理由。
    """
    df, true = make_synthetic(n=800, d=5, contamination=0.05, kind="multivariate", seed=7)
    cleaner = RobustCleaner(vote_ratio=0.5).fit(df)
    f1_consensus = _f1(cleaner.consensus_.flag, true)

    X = df.to_numpy(dtype=float)
    z = np.abs((X - X.mean(axis=0)) / (X.std(axis=0) + 1e-12))
    f1_z = _f1(z.max(axis=1) > 3, true)

    assert f1_z < 0.5, f"这个场景本该是 3σ 的盲区，却拿到了 F1={f1_z:.3f}"
    assert f1_consensus > 0.55, f"共识在困难场景下 F1 过低：{f1_consensus:.3f}"
    assert f1_consensus > f1_z + 0.25, (
        f"共识({f1_consensus:.3f}) 未明显优于 3σ({f1_z:.3f})"
    )


def test_consensus_is_reasonable_on_mixed_case():
    """混合场景：共识 F1 应达到可用水平，且不能靠乱杀换召回。"""
    df, true = make_synthetic(n=800, d=5, contamination=0.05, kind="mixed", seed=7)
    cleaner = RobustCleaner(vote_ratio=0.5).fit(df)
    f1_consensus = _f1(cleaner.consensus_.flag, true)
    fpr = float(np.mean(cleaner.consensus_.flag[~true]))
    assert f1_consensus > 0.8, f"混合场景 F1 过低：{f1_consensus:.3f}"
    assert fpr < 0.03, f"干净样本被误杀的比例过高：{fpr:.3%}"


def test_low_false_positive_on_clean_data():
    """干净数据上不能乱杀：假阳性率应低于 2%。"""
    rng = np.random.default_rng(11)
    df = pd.DataFrame(rng.normal(size=(500, 4)), columns=list("abcd"))
    cleaner = RobustCleaner(vote_ratio=0.5).fit(df)
    rate = cleaner.consensus_.flag_ratio
    assert rate < 0.03, f"干净数据假阳性率过高：{rate:.3%}"


def test_grouped_detection_does_not_kill_whole_group():
    """分组检测：量纲大的组不该被整组判为异常。"""
    df, _ = make_synthetic_grouped(n_per_group=200, d=3, contamination=0.05, seed=5)
    cleaner = RobustCleaner(methods=["mad", "iqr", "mahalanobis"], group_column="group").fit(df)
    for g in df["group"].unique():
        sub = df["group"] == g
        ratio = cleaner.outlier_mask_.to_numpy()[sub].mean()
        assert ratio < 0.20, f"组 {g} 被判为异常的比例过高：{ratio:.1%}"


def test_clean_strategies_and_input_untouched():
    df, _ = make_synthetic(n=300, d=3, contamination=0.05, seed=9)
    original = df.copy()
    cleaner = RobustCleaner(methods=["mad", "iqr", "iforest"], vote_ratio=0.5).fit(df)

    removed = cleaner.clean(df, strategy="remove")
    flagged = cleaner.clean(df, strategy="flag")
    wins = cleaner.clean(df, strategy="winsorize")

    assert len(removed) < len(df)
    assert len(flagged) == len(df) and "is_outlier" in flagged.columns
    assert len(wins) == len(df)
    assert wins.to_numpy(dtype=float).max() <= original.to_numpy(dtype=float).max() + 1e-9
    pd.testing.assert_frame_equal(df, original), "clean() 不应改动传入的数据"


def test_report_and_save(tmp_path: Path | None = None):
    df, _ = make_synthetic(n=300, d=3, contamination=0.05, seed=13)
    cleaner = RobustCleaner(methods=["mad", "iqr", "pca", "iforest"], vote_ratio=0.5).fit(df)
    from robustclean.report import build_report

    text = build_report(cleaner, df)
    assert "共识结果" in text and "敏感性分析" in text and "方法学" in text
    assert "Outliers were identified" in text

    outdir = Path(tmp_path) if tmp_path else Path(__file__).resolve().parents[1] / "output" / "_test"
    result = cleaner.save(outdir, df)
    for key in ("cleaned", "outliers", "report", "methods", "audit"):
        assert Path(result[key]).exists(), f"缺少输出文件：{key}"
    assert len(result["figures"]) >= 1
    return str(outdir)


def test_consensus_quantile_mode():
    df, _ = make_synthetic(n=400, d=3, contamination=0.1, seed=21)
    cleaner = RobustCleaner(contamination=0.05).fit(df)
    ratio = cleaner.consensus_.flag_ratio
    assert 0.03 <= ratio <= 0.08, f"定量模式剔除比例不对：{ratio:.3%}"


def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = []
    for fn in tests:
        try:
            out = fn()
            print(f"[通过] {fn.__name__}" + (f"  -> {out}" if out else ""))
        except AssertionError as exc:
            failed.append(fn.__name__)
            print(f"[失败] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed.append(fn.__name__)
            print(f"[报错] {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n共 {len(tests)} 项，失败 {len(failed)} 项")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
