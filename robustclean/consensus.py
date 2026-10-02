"""多检测器共识：分数融合与投票。

单个检测器的判断都可以被质疑（「你凭什么用这个阈值？」），
但「8 个原理互不相同的检测器里有 6 个都认为它是异常值」这种结论好辩护得多。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.stats import rankdata

from .detectors import DetectionResult


def robust_rank(score: np.ndarray) -> np.ndarray:
    """把任意尺度的异常分数压成 (0, 1) 的稳健秩。

    不同检测器的分数尺度天差地别（马氏距离可以到几十，LOF 只在 1 附近），
    直接平均会被大尺度的方法绑架。转成秩之后，每个方法的话语权相同。
    """
    s = np.asarray(score, dtype=float)
    n = s.size
    if n == 0:
        return s
    r = rankdata(s, method="average")
    return (r - 0.5) / n


@dataclass
class ConsensusResult:
    """共识结果。"""

    score: np.ndarray
    vote_share: np.ndarray
    n_votes: np.ndarray
    flag: np.ndarray
    method_keys: list[str] = field(default_factory=list)
    method_names: list[str] = field(default_factory=list)
    vote_ratio: float = 0.5

    @property
    def n_flagged(self) -> int:
        return int(np.sum(self.flag))

    @property
    def flag_ratio(self) -> float:
        return float(np.mean(self.flag)) if self.flag.size else 0.0

    def vote_distribution(self) -> dict[int, int]:
        """被 k 个检测器同时标记的样本数。"""
        counts: dict[int, int] = {}
        for k in range(0, len(self.method_keys) + 1):
            counts[k] = int(np.sum(self.n_votes == k))
        return counts


def combine_consensus(
    results: list[DetectionResult],
    vote_ratio: float = 0.5,
    weights: np.ndarray | None = None,
    mode: str = "vote",
    contamination: float | None = None,
) -> ConsensusResult:
    """把多个检测器的结果合成一个结论。

    参数
    ----
    results
        各检测器的输出，长度需一致。
    vote_ratio
        投票模式下的阈值：被 ``vote_ratio`` 比例的检测器标记即判为异常。
        0.5 表示「多数票」，0.3 更保守（更容易剔除），0.7 更严格。
    weights
        各检测器权重，默认等权。
    mode
        ``"vote"``：按投票比例判定（默认，可解释性最好）；
        ``"quantile"``：按共识分数的分位点判定，需要同时给出 ``contamination``。
    contamination
        ``mode="quantile"`` 时预期异常比例，例如 0.05 表示剔除共识分数最高的 5%。

    返回
    ----
    :class:`ConsensusResult`
    """
    if not results:
        raise ValueError("至少需要一个检测器结果")
    n = results[0].score.shape[0]
    for r in results:
        if r.score.shape[0] != n:
            raise ValueError("各检测器结果长度不一致")

    rank_mat = np.column_stack([robust_rank(r.score) for r in results])
    flag_mat = np.column_stack([np.asarray(r.flag, dtype=float) for r in results])

    if weights is None:
        w = np.ones(len(results), dtype=float)
    else:
        w = np.asarray(weights, dtype=float)
        if w.shape[0] != len(results):
            raise ValueError("权重个数与检测器个数不一致")
    w = w / w.sum()

    score = rank_mat @ w
    vote_share = flag_mat @ w
    n_votes = flag_mat.sum(axis=1).astype(int)

    if mode == "vote":
        flag = vote_share >= vote_ratio
    elif mode == "quantile":
        if contamination is None:
            raise ValueError("mode='quantile' 需要给出 contamination")
        cut = float(np.quantile(score, 1.0 - contamination))
        flag = score >= cut
    else:
        raise ValueError(f"未知的 mode: {mode}")

    return ConsensusResult(
        score=score,
        vote_share=vote_share,
        n_votes=n_votes,
        flag=flag,
        method_keys=[r.key for r in results],
        method_names=[r.name for r in results],
        vote_ratio=vote_ratio,
    )
