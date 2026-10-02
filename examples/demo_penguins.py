"""真实数据演示：企鹅形态数据（palmerpenguins，CC0 公有领域）。

这份数据是生物学教学里的经典数据集：344 只企鹅、3 个物种、4 个形态指标，
并且**不同物种的体型量级本来就不同**——正好用来说明「分组检测」为什么必须做。

运行：``python examples/demo_penguins.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from robustclean import RobustCleaner  # noqa: E402

DATA = ROOT / "examples" / "data" / "penguins_size.csv"
COLS = ["culmen_length_mm", "culmen_depth_mm", "flipper_length_mm", "body_mass_g"]


def main() -> int:
    if not DATA.exists():
        print(f"找不到数据文件：{DATA}")
        return 1
    df = pd.read_csv(DATA)
    print(f"数据：{len(df)} 只企鹅，{df['species'].nunique()} 个物种，缺失值 {int(df[COLS].isna().sum().sum())} 个\n")

    # ---- 对照组：不分组 ----
    ungrouped = RobustCleaner(methods=["mahalanobis"]).fit(df, columns=COLS)
    print(f"[不分组] 单用马氏距离标记 {ungrouped.consensus_.n_flagged} 个 "
          f"({100 * ungrouped.consensus_.flag_ratio:.2f}%)")

    # ---- 正确做法：按物种分组 + 九方法共识 ----
    cleaner = RobustCleaner(vote_ratio=0.5, group_column="species").fit(df, columns=COLS)
    print("\n[分组 + 共识] 各检测器结果：")
    print(cleaner.summary().to_string(index=False))
    print(f"\n最终判定异常：{cleaner.consensus_.n_flagged} 只 "
          f"({100 * cleaner.consensus_.flag_ratio:.2f}%)")

    result = cleaner.save(ROOT / "output" / "penguins", df, strategy="remove")
    kept = result["cleaned_df"]
    print(f"清洗后剩余 {len(kept)} 只")

    sens = cleaner.sensitivity(df)
    print("\n剔除前后均值变化（越小说明结论越稳健）：")
    for _, row in sens.iterrows():
        print(f"  {row['变量']:<20} {row['均值变化%']:+.2f}%")

    print(f"\n输出目录：{ROOT / 'output' / 'penguins'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
