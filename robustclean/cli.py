"""命令行入口：python -m robustclean 或 robustclean。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .detectors import DETECTOR_REGISTRY
from .pipeline import RobustCleaner


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        try:
            return pd.read_excel(path)
        except ImportError as exc:
            raise SystemExit("读取 Excel 需要 openpyxl：pip install openpyxl") from exc
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="robustclean",
        description="多方法共识异常值检测与清洗（面向科研数据）",
    )
    p.add_argument("input", help="输入数据文件（csv / xlsx）")
    p.add_argument("-o", "--output", default="output", help="输出目录（默认 output）")
    p.add_argument("-c", "--columns", nargs="*", default=None, help="参与检测的列名，默认全部数值列")
    p.add_argument("-g", "--group", default=None, help="分组列名：在每个组内分别检测")
    p.add_argument("-m", "--methods", nargs="*", default=None,
                   choices=sorted(DETECTOR_REGISTRY), help="启用的检测器（默认全部 9 个）")
    p.add_argument("-v", "--vote-ratio", type=float, default=0.5, help="投票阈值，默认 0.5")
    p.add_argument("-q", "--contamination", type=float, default=None,
                   help="改用固定比例剔除，例如 0.05 表示剔除共识分数最高的 5%%")
    p.add_argument("-s", "--strategy", default="remove",
                   choices=["remove", "flag", "winsorize", "nan"], help="清洗策略，默认 remove")
    p.add_argument("--dry-run", action="store_true", help="只打印摘要，不写出文件")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.input)
    if not path.exists():
        print(f"找不到文件：{path}", file=sys.stderr)
        return 2

    df = _read_table(path)
    cleaner = RobustCleaner(
        methods=args.methods,
        vote_ratio=args.vote_ratio,
        group_column=args.group,
        contamination=args.contamination,
    )
    cleaner.fit(df, columns=args.columns)

    print(f"样本数：{len(df)}    参与检测的列：{len(cleaner.columns_)}")
    print(cleaner.summary().to_string(index=False))
    cons = cleaner.consensus_
    print(f"\n共识判定异常：{cons.n_flagged} 个（{100 * cons.flag_ratio:.2f}%）")
    if cleaner.skipped_:
        print("跳过的检测器：")
        for k, v in cleaner.skipped_.items():
            print(f"  - {k}: {v}")

    if args.dry_run:
        return 0

    result = cleaner.save(args.output, df, strategy=args.strategy)
    print(f"\n输出目录：{Path(args.output).resolve()}")
    for key in ("cleaned", "outliers", "report", "methods", "audit"):
        print(f"  - {result[key]}")
    for f in result["figures"]:
        print(f"  - {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
