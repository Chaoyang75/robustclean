"""合成数据生成器：带**已知**异常值，用来验证工具到底有没有用。"""

from __future__ import annotations

import numpy as np
import pandas as pd


def make_synthetic(
    n: int = 1000,
    d: int = 5,
    contamination: float = 0.05,
    kind: str = "mixed",
    seed: int = 0,
    corr: float = 0.5,
) -> tuple[pd.DataFrame, np.ndarray]:
    """生成带已知异常值的合成数据。

    参数
    ----
    n, d
        样本数与变量数。
    contamination
        注入的异常值比例。
    kind
        异常值类型：

        ``"univariate"``
            单变量极端值——某个变量上偏出 6–12 个标准差。
        ``"multivariate"``
            多变量组合异常——任一单变量看都不算极端，但联合起来偏离主成分方向
            （这类异常值单变量方法必然漏检，是多方法共识的价值所在）。
        ``"cluster"``
            外来簇——一小撮点整体偏移，模拟混入的其他批次。
        ``"mixed"``
            （默认）以上三种各占三分之一，最接近真实数据。

    返回
    ----
    ``(df, mask)``：``df`` 是数据表，``mask`` 是布尔数组，True 表示确实是我们注入的异常值。
    """
    rng = np.random.default_rng(seed)

    # 相关结构：等相关矩阵。用特征分解而不是 Cholesky，
    # 这样可以在「次特征方向」上构造异常值——单变量看着不极端，联合分布看却很异常。
    R = np.full((d, d), corr)
    np.fill_diagonal(R, 1.0)
    lam, V = np.linalg.eigh(R)
    lam = np.clip(lam, 1e-6, None)

    means = rng.normal(0, 1, size=d) * 5
    stds = np.abs(rng.normal(1, 0.3, size=d)) + 0.5
    Z = rng.normal(size=(n, d))
    X = ((Z * np.sqrt(lam)) @ V.T) * stds + means

    n_out = int(round(n * contamination))
    mask = np.zeros(n, dtype=bool)
    if n_out > 0:
        idx = rng.choice(n, size=n_out, replace=False)
        mask[idx] = True

        if kind == "mixed":
            splits = np.array_split(idx, 3)
            kinds = ["univariate", "multivariate", "cluster"]
        elif kind in {"univariate", "multivariate", "cluster"}:
            splits = [idx]
            kinds = [kind]
        else:
            raise ValueError(f"未知的 kind: {kind}")

        for part, k in zip(splits, kinds):
            if part.size == 0:
                continue
            if k == "univariate":
                for i in part:
                    j = rng.integers(0, d)
                    direction = 1.0 if rng.random() < 0.5 else -1.0
                    X[i, j] += direction * stds[j] * rng.uniform(6, 12)
            elif k == "multivariate":
                # 只沿次特征方向偏移：每个变量上只偏 1.5–2.5 个标准差（单变量方法抓不到），
                # 但马氏距离达到 4.5–6.5（多变量方法能抓到）。这才是多方法共识的价值所在。
                minor = np.argsort(lam)[: max(1, d - 1)]
                for i in part:
                    u = np.zeros(d)
                    pick = rng.choice(minor, size=int(rng.integers(1, len(minor) + 1)), replace=False)
                    u[pick] = rng.normal(size=pick.size)
                    norm = np.linalg.norm(u)
                    if norm == 0:
                        continue
                    u /= norm
                    shift = (u * np.sqrt(lam)) @ V.T
                    X[i] += shift * rng.uniform(4.5, 6.5)
            else:  # cluster
                center = rng.normal(size=d) * stds * rng.uniform(5, 8)
                X[part] += center + rng.normal(size=(part.size, d)) * stds * 0.5

    cols = [f"x{i + 1}" for i in range(d)]
    df = pd.DataFrame(X, columns=cols)
    return df, mask


def make_synthetic_grouped(
    n_per_group: int = 300,
    d: int = 4,
    contamination: float = 0.05,
    n_groups: int = 3,
    seed: int = 1,
) -> tuple[pd.DataFrame, np.ndarray]:
    """生成分组数据：不同组的量纲/均值不同，用来演示「组内检测」的必要性。"""
    frames, masks = [], []
    for g in range(n_groups):
        df, m = make_synthetic(
            n=n_per_group,
            d=d,
            contamination=contamination,
            kind="mixed",
            seed=seed + g,
        )
        # 给每组不同的量纲和偏移
        df = df * (1.0 + g) + g * 20.0
        df["group"] = f"G{g + 1}"
        frames.append(df)
        masks.append(m)
    return pd.concat(frames, ignore_index=True), np.concatenate(masks)
