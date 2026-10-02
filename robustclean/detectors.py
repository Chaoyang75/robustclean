"""异常值检测器集合。

每个检测器统一返回 :class:`DetectionResult`：

``score``
    连续异常分数，**越大越异常**。用于多方法融合。
``flag``
    布尔数组，True 表示该检测器单独判为异常。用于投票。

为什么分数比标签重要
--------------------
先前的做法通常是「跑一个算法，取它给的标签」。但任何单一算法的阈值都是拍的，
评审要问「你凭什么用这个阈值」时不好回答。这里改成：每个检测器先给出连续的
异常程度，再由投票规则决定去留，阈值在报告里写得明明白白。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np


@dataclass
class DetectionResult:
    """单个检测器的输出。"""

    key: str
    name: str
    score: np.ndarray
    flag: np.ndarray
    params: dict = field(default_factory=dict)
    kind: str = "multivariate"
    note: str = ""

    @property
    def n_flagged(self) -> int:
        return int(np.sum(self.flag))


# --------------------------------------------------------------------------
# 内部工具
# --------------------------------------------------------------------------

def robust_scale(X: np.ndarray) -> np.ndarray:
    """稳健标准化：中位数中心化，MAD 定标。"""
    X = np.asarray(X, dtype=float)
    med = np.nanmedian(X, axis=0)
    mad = np.nanmedian(np.abs(X - med), axis=0)
    scale = 1.4826 * mad
    std = np.nanstd(X, axis=0)
    scale = np.where(scale > 0, scale, np.where(std > 0, std, 1.0))
    with np.errstate(invalid="ignore"):
        Z = (X - med) / scale
    return np.nan_to_num(Z, nan=0.0, posinf=0.0, neginf=0.0)


def robust_cut(score: np.ndarray, n_sigma: float = 3.0) -> float:
    """在分数自身上用「中位数 + n×MAD」定阈值，不预设分布。"""
    score = np.asarray(score, dtype=float)
    med = float(np.median(score))
    mad = float(np.median(np.abs(score - med)))
    scale = 1.4826 * mad
    if scale <= 0:
        return float(np.inf)
    return med + n_sigma * scale


def _row_max(per_column: np.ndarray) -> np.ndarray:
    """把「每列一个分数」压成「每行一个分数」（取最异常的列）。"""
    per_column = np.atleast_2d(per_column)
    if per_column.shape[1] == 0:
        return np.zeros(per_column.shape[0])
    return np.max(np.nan_to_num(per_column, nan=0.0, posinf=0.0, neginf=0.0), axis=1)


def _check(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    if X.ndim != 2:
        raise ValueError("输入必须是二维数组 (样本数, 特征数)")
    return X


def _knn_k(n_samples: int, k: int) -> int:
    return int(max(2, min(k, n_samples - 1)))


# --------------------------------------------------------------------------
# 单变量类检测器
# --------------------------------------------------------------------------

def detect_mad_zscore(X: np.ndarray, threshold: float = 3.5) -> DetectionResult:
    """MAD 稳健 Z 分数（Hampel 标识 / 修正 Z 分数）。

    用中位数代替均值、用 MAD 代替标准差，判据不会被极端值拖走。
    经验阈值 3.5 等价于正态下的约 3σ，但不假设正态。
    """
    X = _check(X)
    med = np.nanmedian(X, axis=0)
    mad = np.nanmedian(np.abs(X - med), axis=0)
    scale = 1.4826 * mad
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.abs(X - med) / np.where(scale > 0, scale, np.nan)
    z = np.nan_to_num(z, nan=0.0, posinf=0.0, neginf=0.0)
    score = _row_max(z)
    return DetectionResult(
        key="mad",
        name="MAD 稳健 Z 分数",
        score=score,
        flag=score > threshold,
        params={"threshold": threshold},
        kind="univariate",
        note="中位数 + MAD，不假设正态分布",
    )


def detect_iqr(X: np.ndarray, k: float = 1.5) -> DetectionResult:
    """Tukey 箱线图准则：超出 Q1-k·IQR 或 Q3+k·IQR 判为异常。

    k=1.5 是常规「离群点」，k=3.0 是「极端离群点」。
    分数定义为超出边界的 IQR 倍数，连续可比。
    """
    X = _check(X)
    q1, q3 = np.nanpercentile(X, [25.0, 75.0], axis=0)
    iqr = q3 - q1
    iqr_safe = np.where(iqr > 0, iqr, np.nan)
    below = (q1 - k * iqr - X) / iqr_safe
    above = (X - (q3 + k * iqr)) / iqr_safe
    excess = np.fmax(np.nan_to_num(below, nan=-np.inf), np.nan_to_num(above, nan=-np.inf))
    excess = np.where(np.isfinite(excess), excess, 0.0)
    excess[excess < 0] = 0.0
    score = _row_max(excess)
    return DetectionResult(
        key="iqr",
        name=f"IQR 箱线图准则 (k={k})",
        score=score,
        flag=score > 0,
        params={"k": k},
        kind="univariate",
        note="经典 Tukey 准则，k=1.5 常规 / k=3.0 极端",
    )


def detect_hampel(X: np.ndarray, window: int = 7, n_sigma: float = 3.0) -> DetectionResult:
    """Hampel 滤波：滑动窗口内的中位数与 MAD 判定。

    只适合**有顺序**的数据（时间序列、按测量顺序排列的样本）。
    对无序数据使用它会引入人为的顺序依赖，所以默认不启用。
    """
    X = _check(X)
    n, d = X.shape
    half = max(0, window // 2)
    score = np.zeros(n)
    for j in range(d):
        x = X[:, j]
        s = np.zeros(n)
        for i in range(n):
            lo, hi = max(0, i - half), min(n, i + half + 1)
            w = x[lo:hi]
            med = np.nanmedian(w)
            mad = np.nanmedian(np.abs(w - med))
            scale = 1.4826 * mad
            s[i] = abs(x[i] - med) / scale if scale > 0 else 0.0
        score = np.maximum(score, s)
    return DetectionResult(
        key="hampel",
        name=f"Hampel 滤波 (窗口={window})",
        score=score,
        flag=score > n_sigma,
        params={"window": window, "n_sigma": n_sigma},
        kind="timeseries",
        note="仅适用于有序数据；无序数据请勿启用",
    )


# --------------------------------------------------------------------------
# 多变量类检测器
# --------------------------------------------------------------------------

def detect_mahalanobis(
    X: np.ndarray,
    support_fraction: float = 0.75,
    chi2_alpha: float = 0.975,
) -> DetectionResult:
    """稳健马氏距离：MCD 估计协方差，卡方分布定阈值。

    普通马氏距离用样本均值与协方差，而这两者本身就被异常值污染；
    改用最小协方差行列式（MCD）后，判据来自「多数正常点」。
    """
    from scipy.stats import chi2
    from sklearn.covariance import MinCovDet

    X = _check(X)
    d = X.shape[1]
    mcd = MinCovDet(support_fraction=support_fraction, random_state=0).fit(X)
    dist = mcd.mahalanobis(X)
    thr = float(chi2.ppf(chi2_alpha, df=d))
    return DetectionResult(
        key="mahalanobis",
        name="马氏距离 (MCD 稳健协方差)",
        score=dist,
        flag=dist > thr,
        params={"support_fraction": support_fraction, "chi2_alpha": chi2_alpha},
        kind="multivariate",
        note=f"阈值来自 χ²({d}) 的 {chi2_alpha:.3f} 分位点 = {thr:.2f}",
    )


def detect_pca(
    X: np.ndarray,
    var_ratio: float = 0.95,
    n_sigma: float = 3.5,
) -> DetectionResult:
    """PCA / SVD 重构误差：正常样本能被少数主成分重建，异常样本不能。

    先用稳健标准化消除量纲，再取累计方差贡献率达到 ``var_ratio`` 的主成分，
    以重构残差平方和（SPE）作为异常分数。对应《统计学习方法》第 15、16 章
    的奇异值分解与主成分分析。
    """
    from sklearn.decomposition import PCA

    X = _check(X)
    Z = robust_scale(X)
    pca = PCA(n_components=var_ratio, svd_solver="full", random_state=0)
    T = pca.fit_transform(Z)
    rec = pca.inverse_transform(T)
    spe = np.sum((Z - rec) ** 2, axis=1)
    cut = robust_cut(spe, n_sigma)
    return DetectionResult(
        key="pca",
        name="PCA/SVD 重构误差",
        score=spe,
        flag=spe > cut,
        params={"var_ratio": var_ratio, "n_sigma": n_sigma},
        kind="multivariate",
        note=f"保留 {pca.n_components_} 个主成分",
    )


def detect_knn(X: np.ndarray, k: int = 10, n_sigma: float = 3.5) -> DetectionResult:
    """k 近邻距离：正常样本周围邻居密集，异常样本「孤零零」。

    对应《统计学习方法》第 3 章 k 近邻法——第 k 距离本身就是局部密度的一种度量。
    """
    from sklearn.neighbors import NearestNeighbors

    X = _check(X)
    Z = robust_scale(X)
    k = _knn_k(len(Z), k)
    nn = NearestNeighbors(n_neighbors=k + 1, n_jobs=-1).fit(Z)
    dist, _ = nn.kneighbors(Z)
    score = dist[:, 1:].mean(axis=1)
    cut = robust_cut(score, n_sigma)
    return DetectionResult(
        key="knn",
        name=f"k 近邻距离 (k={k})",
        score=score,
        flag=score > cut,
        params={"k": k, "n_sigma": n_sigma},
        kind="multivariate",
    )


def detect_lof(X: np.ndarray, k: int = 20, n_sigma: float = 3.5) -> DetectionResult:
    """局部离群因子 LOF：比较样本密度与其邻居密度，适合密度不均的数据。"""
    from sklearn.neighbors import LocalOutlierFactor

    X = _check(X)
    Z = robust_scale(X)
    k = _knn_k(len(Z), k)
    lof = LocalOutlierFactor(n_neighbors=k)
    lof.fit_predict(Z)
    score = -lof.negative_outlier_factor_
    cut = robust_cut(score, n_sigma)
    return DetectionResult(
        key="lof",
        name=f"局部离群因子 LOF (k={k})",
        score=score,
        flag=score > cut,
        params={"k": k, "n_sigma": n_sigma},
        kind="multivariate",
        note="对局部密度差异敏感，适合非均匀分布",
    )


def detect_isolation_forest(
    X: np.ndarray,
    n_estimators: int = 300,
    n_sigma: float = 3.5,
    random_state: int = 0,
) -> DetectionResult:
    """孤立森林：靠随机分割把异常点「孤立」出来，不需要分布假设。

    属于集成方法，对应《统计学习方法》第 8 章提升方法的组合思想。
    """
    from sklearn.ensemble import IsolationForest

    X = _check(X)
    iso = IsolationForest(
        n_estimators=n_estimators,
        random_state=random_state,
        n_jobs=-1,
        bootstrap=False,
    )
    iso.fit(X)
    score = -iso.score_samples(X)
    cut = robust_cut(score, n_sigma)
    return DetectionResult(
        key="iforest",
        name=f"孤立森林 ({n_estimators} 棵树)",
        score=score,
        flag=score > cut,
        params={"n_estimators": n_estimators, "n_sigma": n_sigma, "random_state": random_state},
        kind="multivariate",
        note="不需要分布假设，适合高维",
    )


def detect_dbscan(X: np.ndarray, k: int = 10, min_samples: int | None = None) -> DetectionResult:
    """密度聚类：被 DBSCAN 判为噪声的点即异常点。

    eps 不手拍，用 k-距离曲线的 90% 分位点自动确定。对应聚类方法一章。
    """
    from sklearn.cluster import DBSCAN
    from sklearn.neighbors import NearestNeighbors

    X = _check(X)
    Z = robust_scale(X)
    n, d = Z.shape
    k = _knn_k(n, k)
    nn = NearestNeighbors(n_neighbors=k + 1, n_jobs=-1).fit(Z)
    dist, _ = nn.kneighbors(Z)
    eps = float(np.quantile(dist[:, -1], 0.90))
    ms = int(min_samples) if min_samples else max(4, d + 1)
    labels = DBSCAN(eps=eps, min_samples=ms).fit_predict(Z)
    flag = labels == -1
    score = np.zeros(n)
    core = labels >= 0
    if core.any() and (~core).any():
        nn_core = NearestNeighbors(n_neighbors=1, n_jobs=-1).fit(Z[core])
        dmin, _ = nn_core.kneighbors(Z[~core])
        score[~core] = dmin.ravel()
    return DetectionResult(
        key="dbscan",
        name="DBSCAN 密度聚类噪声点",
        score=score,
        flag=flag,
        params={"k": k, "min_samples": ms, "eps": round(eps, 6)},
        kind="multivariate",
        note=f"eps={eps:.4f} 由 k-距离 90% 分位点自动确定",
    )


def detect_gmm(
    X: np.ndarray,
    max_components: int = 4,
    n_sigma: float = 3.5,
    random_state: int = 0,
) -> DetectionResult:
    """高斯混合模型：用 EM 拟合正常数据的分布，低似然的点判为异常。

    对应《统计学习方法》第 9 章 EM 算法。分量数由 BIC 自动选择。
    """
    from sklearn.mixture import GaussianMixture

    X = _check(X)
    Z = robust_scale(X)
    best_bic, best_k, best_model = np.inf, 1, None
    for c in range(1, int(max_components) + 1):
        gm = GaussianMixture(
            n_components=c,
            covariance_type="full",
            random_state=random_state,
            reg_covar=1e-6,
            max_iter=300,
        )
        try:
            gm.fit(Z)
        except Exception:  # 数据退化时跳过该分量数
            continue
        bic = float(gm.bic(Z))
        if bic < best_bic:
            best_bic, best_k, best_model = bic, c, gm
    if best_model is None:
        raise RuntimeError("高斯混合模型无法拟合当前数据")
    score = -best_model.score_samples(Z)
    cut = robust_cut(score, n_sigma)
    return DetectionResult(
        key="gmm",
        name=f"高斯混合模型 (EM, 分量数={best_k})",
        score=score,
        flag=score > cut,
        params={"max_components": max_components, "n_sigma": n_sigma, "selected_k": best_k},
        kind="multivariate",
        note=f"BIC 选择分量数，BIC={best_bic:.1f}",
    )


# --------------------------------------------------------------------------
# 注册表
# --------------------------------------------------------------------------

DETECTOR_REGISTRY: dict[str, Callable[..., DetectionResult]] = {
    "mad": detect_mad_zscore,
    "iqr": detect_iqr,
    "hampel": detect_hampel,
    "mahalanobis": detect_mahalanobis,
    "pca": detect_pca,
    "knn": detect_knn,
    "lof": detect_lof,
    "iforest": detect_isolation_forest,
    "dbscan": detect_dbscan,
    "gmm": detect_gmm,
}

DEFAULT_PARAMS: dict[str, dict] = {
    "mad": {"threshold": 3.5},
    "iqr": {"k": 1.5},
    "hampel": {"window": 7, "n_sigma": 3.0},
    "mahalanobis": {"support_fraction": 0.75, "chi2_alpha": 0.975},
    "pca": {"var_ratio": 0.95, "n_sigma": 3.5},
    "knn": {"k": 10, "n_sigma": 3.5},
    "lof": {"k": 20, "n_sigma": 3.5},
    "iforest": {"n_estimators": 300, "n_sigma": 3.5},
    "dbscan": {"k": 10},
    "gmm": {"max_components": 4, "n_sigma": 3.5},
}

#: 默认启用的检测器。Hampel 只适用于有序数据，默认关闭。
DEFAULT_METHODS: tuple[str, ...] = (
    "mad",
    "iqr",
    "mahalanobis",
    "pca",
    "knn",
    "lof",
    "iforest",
    "dbscan",
    "gmm",
)
