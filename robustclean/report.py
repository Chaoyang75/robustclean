"""报告生成：可直接写进论文方法学部分的文字、表格与图。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _fmt(v, nd: int = 4) -> str:
    try:
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return "-"
        return f"{float(v):.{nd}g}"
    except Exception:
        return str(v)


def _table(rows: list[dict], headers: list[str]) -> str:
    if not rows:
        return "（无）\n"
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(h, "")) for h in headers) + " |")
    return "\n".join(out) + "\n"


def methods_paragraph(cleaner, lang: str = "zh") -> str:
    """生成可直接粘贴进论文 Methods 的段落。"""
    cons = cleaner.consensus_
    n = len(cleaner.outlier_mask_)
    n_out = int(cleaner.outlier_mask_.sum())
    pct = 100.0 * n_out / n if n else 0.0
    names = "、".join(r.name.split(" (")[0] for r in cleaner.results_)
    group_txt = f"，并在变量「{cleaner.group_column}」的每个水平内分别执行" if cleaner.group_column else ""

    if lang == "en":
        group_en = f" applied within each level of {cleaner.group_column}" if cleaner.group_column else ""
        parts = [
            f"Outliers were identified using a multi-detector consensus procedure{group_en}.",
            f"The following detectors were applied: {', '.join(r.key for r in cleaner.results_)}.",
            "Each detector produced a continuous outlier score; scores were converted to robust ranks "
            "and combined by equal weighting.",
            f"A sample was labelled as an outlier when at least {cons.vote_ratio:.0%} of the detectors flagged it.",
            f"This procedure identified {n_out} of {n} observations ({pct:.2f}%), which were excluded from downstream analyses.",
            "All detector thresholds are reported in the accompanying audit log; the analysis is fully reproducible.",
        ]
        return " ".join(parts)

    return (
        f"本研究采用多检测器共识策略识别异常值{group_txt}。"
        f"参与判定的检测器包括：{names}，共 {len(cleaner.results_)} 种。"
        f"每种检测器先输出连续的异常分数，再经稳健秩变换归一化后等权融合；"
        f"当某样本被不低于 {cons.vote_ratio:.0%} 的检测器判为异常时，判定为异常值。"
        f"据此共识别出 {n_out} 个异常样本，占全部 {n} 个样本的 {pct:.2f}%，"
        f"这些样本未纳入后续统计分析。全部检测器及其参数、阈值与逐样本判定明细见审计日志。"
    )


def build_report(cleaner, df: pd.DataFrame, sensitivity: pd.DataFrame | None = None, only_methods: bool = False) -> str:
    """生成 Markdown 报告。"""
    cons = cleaner.consensus_
    n = len(df)
    mask = cleaner.outlier_mask_.to_numpy()
    n_out = int(mask.sum())
    pct = 100.0 * n_out / n if n else 0.0

    if only_methods:
        return (
            "# 论文方法学段落\n\n## 中文\n\n" + methods_paragraph(cleaner, "zh")
            + "\n\n## English\n\n" + methods_paragraph(cleaner, "en") + "\n"
        )

    if sensitivity is None:
        sensitivity = cleaner.sensitivity(df)

    lines: list[str] = []
    lines.append("# 异常值检测与清洗报告\n")

    # 1 数据概况
    lines.append("## 1. 数据概况\n")
    lines.append(f"- 样本数：{n}")
    lines.append(f"- 参与检测的变量（{len(cleaner.columns_)} 个）：{'、'.join(map(str, cleaner.columns_))}")
    if cleaner.group_column:
        lines.append(f"- 分组检测：按「{cleaner.group_column}」分为 {cleaner.n_groups_} 组，组内独立判定")
    if cleaner.imputed_counts_:
        detail = "、".join(f"{k} {v} 个" for k, v in cleaner.imputed_counts_.items())
        lines.append(f"- 缺失值：{detail}（**仅用于检测阶段**的临时填补，原始数据未被改动）")
    lines.append("")

    # 2 方法
    lines.append("## 2. 检测方法\n")
    lines.append(f"共启用 {len(cleaner.results_)} 个检测器，等权融合，投票阈值 {cons.vote_ratio:.0%}。\n")
    rows = []
    for r in cleaner.results_:
        params = "、".join(f"{k}={v}" for k, v in r.params.items())
        rows.append({
            "检测器": r.name,
            "类别": {"univariate": "单变量", "multivariate": "多变量", "timeseries": "时序"}.get(r.kind, r.kind),
            "关键参数": params,
            "标记数": r.n_flagged,
            "占比": f"{100.0 * r.n_flagged / n:.2f}%" if n else "-",
        })
    lines.append(_table(rows, ["检测器", "类别", "关键参数", "标记数", "占比"]))

    if cleaner.skipped_:
        lines.append("**未参与判定的检测器：**\n")
        for k, v in cleaner.skipped_.items():
            lines.append(f"- {k}：{v}")
        lines.append("")

    # 3 共识结果
    lines.append("## 3. 共识结果\n")
    lines.append(f"被判定为异常值的样本：**{n_out} 个（{pct:.2f}%）**。\n")
    dist = cons.vote_distribution()
    rows = [{"被标记次数": k, "样本数": v, "占全部样本": f"{100.0 * v / n:.2f}%"} for k, v in dist.items()]
    lines.append(_table(rows, ["被标记次数", "样本数", "占全部样本"]))
    lines.append(
        f"\n被 ≥{cons.vote_ratio:.0%} 检测器同时标记（即最终判定为异常）的样本共 {n_out} 个；"
        f"仅被 1–2 个检测器标记的样本保留在数据中，可在 `outlier_detail_all.csv` 中单独查看。\n"
    )

    # 4 敏感性分析
    lines.append("## 4. 敏感性分析（剔除前后）\n")
    if sensitivity is None or sensitivity.empty:
        lines.append("（无可比较的数值列）\n")
    else:
        rows = [{
            "变量": r["变量"],
            "均值_前": _fmt(r["均值_前"]),
            "均值_后": _fmt(r["均值_后"]),
            "均值变化": f"{r['均值变化%']:+.2f}%",
            "标准差_前": _fmt(r["标准差_前"]),
            "标准差_后": _fmt(r["标准差_后"]),
            "偏度_前": _fmt(r["偏度_前"], 3),
            "偏度_后": _fmt(r["偏度_后"], 3),
        } for _, r in sensitivity.iterrows()]
        lines.append(_table(rows, ["变量", "均值_前", "均值_后", "均值变化", "标准差_前", "标准差_后", "偏度_前", "偏度_后"]))
        lines.append(
            "\n**怎么读这张表**：标准差明显变小、偏度绝对值下降，说明剔除的是把分布拖歪的极端点，"
            "剩下的数据更接近对称分布；如果均值变化很大（比如超过 5%），"
            "说明结论对异常值敏感，需要在论文里明确说明处理方式，或改用 `strategy=\"winsorize\"` 保留样本。\n"
        )

    # 5 可复现信息
    lines.append("## 5. 可复现信息\n")
    lines.append("- 工具：robustclean " + str(_version_safe()))
    lines.append(f"- 随机种子：0（孤立森林、高斯混合模型均为确定性结果）")
    lines.append(f"- 检测器与参数：见附录 `audit.json`")
    lines.append(f"- 生成时间：{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # 6 方法学段落
    lines.append("## 6. 可直接用于论文方法学的段落\n")
    lines.append("**中文：**\n")
    lines.append(methods_paragraph(cleaner, "zh") + "\n")
    lines.append("**English：**\n")
    lines.append(methods_paragraph(cleaner, "en") + "\n")

    return "\n".join(lines)


def _version_safe() -> str:
    try:
        from . import __version__
        return __version__
    except Exception:
        return "unknown"


def build_figures(cleaner, df: pd.DataFrame, outdir: str | Path) -> list[str]:
    """生成两张诊断图：共识分数分布 + PCA 二维投影。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    setup_cjk_font(matplotlib)

    outdir = Path(outdir)
    figures: list[str] = []
    cons = cleaner.consensus_
    mask = cleaner.outlier_mask_.to_numpy()
    cols = [str(c) for c in cleaner.columns_]

    # 图 1：共识分数分布 + 投票数分布
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), dpi=150)
    axes[0].hist(cons.score, bins=40, color="#4c72b0", alpha=0.85)
    axes[0].axvline(float(np.min(cons.score[mask])) if mask.any() else 0.0,
                    color="#c44e52", linestyle="--", linewidth=1.2, label="判定阈值")
    axes[0].set_xlabel("共识异常分数")
    axes[0].set_ylabel("样本数")
    axes[0].set_title("共识分数分布")
    axes[0].legend(fontsize=8)

    dist = cons.vote_distribution()
    ks = sorted(dist)
    axes[1].bar([str(k) for k in ks], [dist[k] for k in ks], color="#55a868", alpha=0.9)
    axes[1].set_xlabel("被几个检测器标记")
    axes[1].set_ylabel("样本数")
    axes[1].set_title("投票分布")
    fig.tight_layout()
    p1 = outdir / "fig1_score_distribution.png"
    fig.savefig(p1)
    plt.close(fig)
    figures.append(str(p1))

    # 图 2：PCA 二维投影
    if len(cols) >= 2:
        from sklearn.decomposition import PCA
        from .detectors import robust_scale

        X = df[cleaner.columns_].to_numpy(dtype=float)
        X = np.where(np.isfinite(X), X, np.nan)
        med = np.nanmedian(X, axis=0)
        X = np.where(np.isfinite(X), X, med)
        Z = robust_scale(X)
        coords = PCA(n_components=2, random_state=0).fit_transform(Z)

        fig, ax = plt.subplots(figsize=(5.2, 4.2), dpi=150)
        ax.scatter(coords[~mask, 0], coords[~mask, 1], s=12, c="#4c72b0", alpha=0.55, label="保留")
        if mask.any():
            ax.scatter(coords[mask, 0], coords[mask, 1], s=26, c="#c44e52", marker="x", label="判定为异常")
        ax.set_xlabel("主成分 1")
        ax.set_ylabel("主成分 2")
        ax.set_title("样本分布（PCA 投影）")
        ax.legend(fontsize=8)
        fig.tight_layout()
        p2 = outdir / "fig2_pca_scatter.png"
        fig.savefig(p2)
        plt.close(fig)
        figures.append(str(p2))

    return figures


def setup_cjk_font(matplotlib) -> str:
    """让图里的中文能正常显示（否则会是方块）。"""
    from matplotlib import font_manager

    candidates = (
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "PingFang SC",
        "WenQuanYi Zen Hei",
    )
    try:
        available = {f.name for f in font_manager.fontManager.ttflist}
    except Exception:
        available = set()
    chosen = next((c for c in candidates if c in available), None)
    if chosen:
        matplotlib.rcParams["font.sans-serif"] = [chosen]
    else:
        matplotlib.rcParams["font.sans-serif"] = list(candidates) + ["DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    return chosen or ""
