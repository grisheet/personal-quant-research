"""Cross-sectional ranks; no fitting and no future normalization."""

import pandas as pd


def ranked_signals(features: pd.DataFrame) -> pd.DataFrame:
    if features.empty:
        return features.copy()
    result = features.loc[features["eligible"]].copy()
    for column in ("momentum", "quality"):
        result[f"{column}_rank"] = result[column].rank(method="average", pct=True)
    result["score"] = (result["momentum_rank"] + result["quality_rank"]) / 2
    # Stable secondary key makes ties reproducible across platforms.
    return result.sort_values(["score", "asset_id"], ascending=[False, True])
