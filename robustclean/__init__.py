"""robustclean —— 面向科研数据的多方法共识异常值检测与清洗工具。

设计目标：让「剔除异常值」这一步在论文里站得住脚。

三条原则：
1. 只用稳健统计量（中位数、MAD、分位数），不让异常值本身影响判定标准；
2. 不依赖单一方法，多个检测器投票，结果更稳、更容易辩护；
3. 每一次剔除都留下审计痕迹：谁被剔除、被几个方法标记、剔除前后统计量怎么变。
"""

from .detectors import (
    DETECTOR_REGISTRY,
    DEFAULT_PARAMS,
    DetectionResult,
    detect_dbscan,
    detect_gmm,
    detect_hampel,
    detect_iqr,
    detect_isolation_forest,
    detect_knn,
    detect_lof,
    detect_mad_zscore,
    detect_mahalanobis,
    detect_pca,
)
from .consensus import ConsensusResult, combine_consensus, robust_rank
from .pipeline import RobustCleaner

__version__ = "0.1.0"

__all__ = [
    "RobustCleaner",
    "DetectionResult",
    "ConsensusResult",
    "combine_consensus",
    "robust_rank",
    "DETECTOR_REGISTRY",
    "DEFAULT_PARAMS",
    "detect_mad_zscore",
    "detect_iqr",
    "detect_hampel",
    "detect_mahalanobis",
    "detect_pca",
    "detect_knn",
    "detect_lof",
    "detect_isolation_forest",
    "detect_dbscan",
    "detect_gmm",
    "__version__",
]
