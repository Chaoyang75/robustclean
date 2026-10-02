"""三分钟上手：跑通一次完整的检测 → 清洗 → 报告。

运行：``python examples/quickstart.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from robustclean import RobustCleaner  # noqa: E402
from robustclean.datasets import make_synthetic  # noqa: E402


def main() -> int:
    # 1. 造一份带已知异常值的数据（真实场景换成 pd.read_csv("你的数据.csv")）
    df, truth = make_synthetic(n=600, d=5, contamination=0.05, seed=2026)
    print(f"数据规模：{df.shape[0]} 行 × {df.shape[1]} 列，其中真异常值 {truth.sum()} 个\n")

    # 2. 检测
    cleaner = RobustCleaner(vote_ratio=0.5).fit(df)
    print("各检测器的判定结果：")
    print(cleaner.summary().to_string(index=False))

    hit = int((cleaner.consensus_.flag & truth).sum())
    print(f"\n共识判定 {cleaner.consensus_.n_flagged} 个异常值，其中 {hit} 个确实是我们注入的")

    # 3. 清洗并导出全部产物
    outdir = ROOT / "output" / "quickstart"
    result = cleaner.save(outdir, df, strategy="remove")

    print(f"\n清洗后剩余 {len(result['cleaned_df'])} 行")
    print(f"\n输出目录：{outdir}")
    for key in ("cleaned", "outliers", "report", "methods", "audit"):
        print(f"  - {Path(result[key]).name}")
    print("\n报告预览（前 600 字）：")
    print(Path(result["report"]).read_text(encoding="utf-8")[:600])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
