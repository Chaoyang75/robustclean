"""主流程：RobustCleaner。"""

from __future__ import annotations

import json
import platform
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .consensus import ConsensusResult, combine_consensus
from .detectors import DEFAULT_METHODS, DEFAULT_PARAMS, DETECTOR_REGISTRY, DetectionResult


class RobustCleaner:
    """多方法共识异常值检测与清洗。

    基本用法::

        from robustclean import RobustCleaner

        cleaner = RobustCleaner().fit(df)
        print(cleaner.summary())
        cleaned = cleaner.clean(df, strategy="remove")
        cleaner.save("output/", df)

    参数
    ----
    methods
        启用的检测器 key 列表，默认 :data:`DEFAULT_METHODS`（9 个）。
        可选：mad / iqr / hampel / mahalanobis / pca / knn / lof / iforest / dbscan / gmm。
    params
        覆盖默认参数，例如 ``{"mad": {"threshold": 4.0}}``。
    vote_ratio
        投票阈值，默认 0.5（多数票）。
    group_column
        分组列名。给出后会**在每个组内单独检测**——科研数据里不同处理组的
        量纲和分布本来就不同，混在一起检测会把整组当成异常。
    contamination
        不用投票、改为按共识分数剔除固定比例时给出，例如 0.05。
    drop_duplicates
        检测前是否删除完全重复的行（默认 False，因为重复测量在科研中可能合法）。
    """

    def __init__(
        self,
        methods: list[str] | tuple[str, ...] | None = None,
        params: dict | None = None,
        vote_ratio: float = 0.5,
        group_column: str | None = None,
        contamination: float | None = None,
        targets: dict[str, object] | None = None,
    ) -> None:
        self.methods = list(methods) if methods else list(DEFAULT_METHODS)
        unknown = [m for m in self.methods if m not in DETECTOR_REGISTRY]
        if unknown:
            raise ValueError(f"未知的检测器: {unknown}；可选 {sorted(DETECTOR_REGISTRY)}")
        self.params = dict(params or {})
        self.vote_ratio = float(vote_ratio)
        self.group_column = group_column
        self.contamination = contamination
        self.targets = dict(targets or {})

        self.columns_: list[str] = []
        self.index_: pd.Index | None = None
        self.results_: list[DetectionResult] = []
        self.consensus_: ConsensusResult | None = None
        self.outlier_mask_: pd.Series | None = None
        self.skipped_: dict[str, str] = {}
        self.imputed_counts_: dict[str, int] = {}
        self.n_groups_: int = 1

    # ------------------------------------------------------------------
    # 拟合
    # ------------------------------------------------------------------

    def _method_params(self, key: str) -> dict:
        p = dict(DEFAULT_PARAMS.get(key, {}))
        p.update(self.params.get(key, {}))
        return p

    def _run_detectors(self, X: np.ndarray) -> list[DetectionResult]:
        out: list[DetectionResult] = []
        for key in self.methods:
            fn = DETECTOR_REGISTRY[key]
            try:
                res = fn(X, **self._method_params(key))
            except Exception as exc:  # 单个检测器失败不应中断整个流程
                self.skipped_[key] = f"{type(exc).__name__}: {exc}"
                continue
            out.append(res)
        return out

    def fit(self, df: pd.DataFrame, columns: list[str] | None = None) -> "RobustCleaner":
        """在数据上拟合检测器。``df`` 不会被修改。"""
        if not isinstance(df, pd.DataFrame):
            raise TypeError("fit() 需要 pandas DataFrame")
        if df.empty:
            raise ValueError("数据为空")

        if columns is None:
            excluded = {self.group_column} if self.group_column else set()
            columns = [
                c for c in df.columns
                if c not in excluded and pd.api.types.is_numeric_dtype(df[c])
            ]
        if not columns:
            raise ValueError("没有找到可用的数值列，请用 columns= 显式指定")

        self.columns_ = list(columns)
        self.index_ = df.index
        self.skipped_ = {}

        work = df.reset_index(drop=True)
        X_raw = work[self.columns_].to_numpy(dtype=float)

        # 整行缺失的样本不参与检测：它们是缺失数据，不是异常值
        all_missing = ~np.isfinite(X_raw).any(axis=1)
        self.n_all_missing_ = int(all_missing.sum())

        n = X_raw.shape[0]
        score_mat = np.full((n, len(self.methods)), np.nan)
        flag_mat = np.zeros((n, len(self.methods)), dtype=bool)
        meta: dict[str, DetectionResult] = {}
        self.imputed_counts_ = {}

        def prepare(rows: np.ndarray) -> np.ndarray:
            """组内中位数填补（仅用于检测，不改动用户原始数据）。"""
            Xg = X_raw[rows].copy()
            for j, c in enumerate(self.columns_):
                col = Xg[:, j]
                miss = ~np.isfinite(col)
                if not miss.any():
                    continue
                fill = float(np.nanmedian(col)) if np.isfinite(col).any() else 0.0
                col[miss] = fill
                Xg[:, j] = col
                self.imputed_counts_[c] = self.imputed_counts_.get(c, 0) + int(miss.sum())
            return Xg

        def run_block(rows: np.ndarray) -> bool:
            rows = rows[~all_missing[rows]]
            if rows.size < 10:  # 样本太少，检测没有统计意义
                return False
            for res in self._run_detectors(prepare(rows)):
                if res.key in self.methods:
                    meta.setdefault(res.key, res)
                    pos = self.methods.index(res.key)
                    score_mat[rows, pos] = res.score
                    flag_mat[rows, pos] = res.flag
            return True

        if self.group_column and self.group_column in work.columns:
            groups = work[self.group_column].astype(str).to_numpy()
            self.n_groups_ = len(set(groups))
            for g in pd.unique(groups):
                idx = np.flatnonzero(groups == g)
                if not run_block(idx):
                    valid = int((~all_missing[idx]).sum())
                    self.skipped_[f"group:{g}"] = f"有效样本数 {valid} < 10，跳过"
        else:
            self.n_groups_ = 1
            if not run_block(np.arange(n)):
                raise ValueError(f"有效样本数不足（{int((~all_missing).sum())} < 10），无法检测")

        # 未参与检测的样本（整行缺失或所在组样本过少）：分数压到最低，标签保持 False
        for i in range(len(self.methods)):
            col = score_mat[:, i]
            bad = ~np.isfinite(col)
            if bad.any():
                good = col[~bad]
                col[bad] = (float(good.min()) - 1.0) if good.size else 0.0
                score_mat[:, i] = col

        # 组装成 DetectionResult（整表长度），供融合与报告使用
        self.results_ = []
        for i, key in enumerate(self.methods):
            if not np.isfinite(score_mat[:, i]).any():
                continue  # 该检测器在所有分组里都失败了
            ref = meta.get(key)
            self.results_.append(
                DetectionResult(
                    key=key,
                    name=ref.name if ref else key,
                    score=score_mat[:, i],
                    flag=flag_mat[:, i],
                    params=ref.params if ref else self._method_params(key),
                    kind=ref.kind if ref else "multivariate",
                    note=ref.note if ref else "",
                )
            )

        self.consensus_ = combine_consensus(
            self.results_,
            vote_ratio=self.vote_ratio,
            mode="quantile" if self.contamination else "vote",
            contamination=self.contamination,
        )
        self.outlier_mask_ = pd.Series(self.consensus_.flag, index=self.index_, name="is_outlier")
        # 把「被几个方法标记」也挂到每个检测器结果上，方便写报告
        for res in self.results_:
            res.note = (res.note + " " if res.note else "") + f"标记 {res.n_flagged} 个"
        return self

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def summary(self) -> pd.DataFrame:
        """每个检测器的标记数量与占比。"""
        self._require_fit()
        rows = []
        n = len(self.outlier_mask_)
        for res in self.results_:
            rows.append({
                "检测器": res.name,
                "key": res.key,
                "标记数": res.n_flagged,
                "占比%": round(100.0 * res.n_flagged / n, 2) if n else 0.0,
            })
        cons = self.consensus_
        rows.append({
            "检测器": f"共识 (投票阈值 {cons.vote_ratio:.0%})",
            "key": "consensus",
            "标记数": cons.n_flagged,
            "占比%": round(100.0 * cons.flag_ratio, 2),
        })
        return pd.DataFrame(rows)

    def outlier_report(self, df: pd.DataFrame) -> pd.DataFrame:
        """逐样本的判定明细：共识分数、投票数、各检测器是否标记。"""
        self._require_fit()
        out = pd.DataFrame(index=self.index_)
        out["共识分数"] = np.round(self.consensus_.score, 4)
        out["被几个检测器标记"] = self.consensus_.n_votes
        out["投票比例"] = np.round(self.consensus_.vote_share, 4)
        out["是否异常"] = self.consensus_.flag
        for res in self.results_:
            out[f"标记_{res.key}"] = res.flag
        return out

    # ------------------------------------------------------------------
    # 清洗
    # ------------------------------------------------------------------

    def clean(self, df: pd.DataFrame, strategy: str = "remove") -> pd.DataFrame:
        """按拟合结果处理数据，返回**新的** DataFrame。

        strategy
        --------
        ``"remove"``
            直接删除被标记的样本（最常用，但报告里必须说明剔除了多少、为什么）。
        ``"flag"``
            不删数据，加三列：``is_outlier``、``outlier_score``、``outlier_votes``。
            适合「先标记、后人工判断」或需要给审稿人看原始数据的场景。
        ``"winsorize"``
            不删样本，只把被标记样本的数值**截断**到正常样本的取值范围。
            保留样本量，同时压掉极端值的影响。
        ``"nan"``
            把被标记样本的数值置为缺失，交给后续统计方法自行处理缺失。
        """
        self._require_fit()
        if len(df) != len(self.outlier_mask_):
            raise ValueError("传入的数据行数与拟合时不一致")
        if strategy not in {"remove", "flag", "winsorize", "nan"}:
            raise ValueError(f"未知的 strategy: {strategy}")

        mask = self.outlier_mask_.to_numpy()
        out = df.copy()

        if strategy == "remove":
            return out.loc[~mask].copy()

        if strategy == "flag":
            out["is_outlier"] = mask
            out["outlier_score"] = np.round(self.consensus_.score, 4)
            out["outlier_votes"] = self.consensus_.n_votes
            return out

        if strategy == "nan":
            out.loc[mask, self.columns_] = np.nan
            return out

        keep = ~mask
        for c in self.columns_:
            values = out[c].to_numpy(dtype=float, copy=True)
            if not keep.any():
                continue
            kept = values[keep]
            kept = kept[np.isfinite(kept)]
            if kept.size == 0:
                continue
            lo, hi = float(np.min(kept)), float(np.max(kept))
            values[mask] = np.clip(values[mask], lo, hi)
            out[c] = values
        return out

    # ------------------------------------------------------------------
    # 敏感性分析 / 报告 / 导出
    # ------------------------------------------------------------------

    def sensitivity(self, df: pd.DataFrame) -> pd.DataFrame:
        """剔除前后各数值列统计量的变化——审稿人一定会问这个。"""
        self._require_fit()
        from scipy import stats

        mask = self.outlier_mask_.to_numpy()
        keep = ~mask
        rows = []
        for c in self.columns_:
            v = df[c].to_numpy(dtype=float)
            before = v[np.isfinite(v)]
            after = v[keep & np.isfinite(v)]
            if before.size == 0 or after.size == 0:
                continue
            rows.append({
                "变量": str(c),
                "剔除点数": int(mask.sum()),
                "均值_前": float(np.mean(before)),
                "均值_后": float(np.mean(after)),
                "均值变化%": 100.0 * (np.mean(after) - np.mean(before)) / (abs(np.mean(before)) + 1e-12),
                "标准差_前": float(np.std(before, ddof=1)) if before.size > 1 else 0.0,
                "标准差_后": float(np.std(after, ddof=1)) if after.size > 1 else 0.0,
                "偏度_前": float(stats.skew(before)) if before.size > 2 else 0.0,
                "偏度_后": float(stats.skew(after)) if after.size > 2 else 0.0,
            })
        return pd.DataFrame(rows)

    def save(self, outdir: str | Path, df: pd.DataFrame, strategy: str = "remove") -> dict:
        """一次性导出：清洗后数据、被剔除的点、明细表、报告、图、审计日志。"""
        from .report import build_report, build_figures

        self._require_fit()
        outdir = Path(outdir)
        outdir.mkdir(parents=True, exist_ok=True)

        cleaned = self.clean(df, strategy=strategy)
        mask = self.outlier_mask_.to_numpy()

        cleaned_path = outdir / "cleaned.csv"
        cleaned.to_csv(cleaned_path, index=False, encoding="utf-8-sig")

        outlier_path = outdir / "outliers.csv"
        detail = self.outlier_report(df)
        # 被剔除的样本：原始数据 + 判定依据，方便逐条核对「到底删了谁」
        removed_rows = pd.concat(
            [df.loc[mask].reset_index(drop=True), detail.loc[mask].reset_index(drop=True)],
            axis=1,
        )
        removed_rows.to_csv(outlier_path, index=False, encoding="utf-8-sig")

        detail_all = outdir / "outlier_detail_all.csv"
        detail.to_csv(detail_all, index=False, encoding="utf-8-sig")

        summary_path = outdir / "detector_summary.csv"
        self.summary().to_csv(summary_path, index=False, encoding="utf-8-sig")

        sensitivity_path = outdir / "sensitivity.csv"
        sens = self.sensitivity(df)
        sens.to_csv(sensitivity_path, index=False, encoding="utf-8-sig")

        report_path = outdir / "report.md"
        report_path.write_text(build_report(self, df, sens), encoding="utf-8")

        methods_path = outdir / "methods_paragraph.md"
        methods_path.write_text(build_report(self, df, sens, only_methods=True), encoding="utf-8")

        figures = build_figures(self, df, outdir)

        audit = {
            "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "robustclean 版本": _version(),
            "随机种子": 0,
            "python": platform.python_version(),
            "检测器": self.methods,
            "每个检测器参数": {r.key: r.params for r in self.results_},
            "投票阈值": self.vote_ratio,
            "分组列": self.group_column,
            "分组数": self.n_groups_,
            "参与检测的列": self.columns_,
            "样本数": int(len(df)),
            "异常样本数": int(mask.sum()),
            "异常占比": round(float(mask.mean()) * 100, 4),
            "缺失值填补（仅用于检测）": self.imputed_counts_,
            "跳过的检测器": self.skipped_,
            "策略": strategy,
        }
        audit_path = outdir / "audit.json"
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "cleaned": cleaned_path,
            "outliers": outlier_path,
            "detail": detail_all,
            "summary": summary_path,
            "sensitivity": sensitivity_path,
            "report": report_path,
            "methods": methods_path,
            "audit": audit_path,
            "figures": figures,
            "cleaned_df": cleaned,
        }

    # ------------------------------------------------------------------
    def _require_fit(self) -> None:
        if self.consensus_ is None or self.outlier_mask_ is None:
            raise RuntimeError("请先调用 fit(df)")


def _version() -> str:
    try:
        from . import __version__
        return __version__
    except Exception:
        return "unknown"
