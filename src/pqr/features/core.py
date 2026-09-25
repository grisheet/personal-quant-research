"""Transparent non-ML features evaluated against a point-in-time view."""

from typing import Protocol

import pandas as pd

from pqr.configs.models import ResearchConfig
from pqr.data.calendar import sessions
from pqr.data.point_in_time import eligible_bars, eligible_fundamentals, members_at
from pqr.data.schemas import Dataset


class Feature(Protocol):
    def __call__(self, history: pd.Series) -> float: ...


def momentum(history: pd.Series, lookback: int, skip: int) -> float:
    # The current endpoint is history[-1]; exactly lookback sessions before it is -lookback-1.
    if len(history) < lookback + 1 or history.iloc[-lookback - 1 :].isna().any():
        return float("nan")
    return float(history.iloc[-skip - 1] / history.iloc[-lookback - 1] - 1)


def feature_snapshot(
    data: Dataset,
    decision_at: pd.Timestamp,
    config: ResearchConfig,
) -> pd.DataFrame:
    bars = eligible_bars(data.bars, decision_at)
    members = members_at(data.universe, decision_at)
    facts = eligible_fundamentals(data.fundamentals, decision_at, config.max_fact_age_days)
    fact_map = facts.set_index("asset_id")
    if bars.empty:
        return pd.DataFrame()
    # Use the last exchange session before this morning's decision, not an asset's last quote.
    local_day = decision_at.tz_convert("America/New_York").normalize().tz_localize(None)
    history_days = sessions(str(bars["session"].min().date()), str(local_day.date()))
    history_days = history_days[history_days < local_day]
    rows = []
    for member in members.itertuples():
        asset = str(member.asset_id)
        history = bars.loc[bars["asset_id"].eq(asset)].set_index("session").reindex(history_days)
        reason = ""
        mom = momentum(history["tr_close"], config.momentum_lookback, config.momentum_skip)
        quality = float("nan")
        dollar_volume = float(
            (history["close"] * history["volume"]).tail(config.liquidity_window).median()
        )
        last_price = float(history["close"].iloc[-1]) if len(history) else float("nan")
        if asset in fact_map.index:
            fact = fact_map.loc[asset]
            denominator = (float(fact["assets_begin"]) + float(fact["assets_end"])) / 2
            if denominator > 0:
                quality = float(fact["net_income"]) / denominator
        if pd.isna(last_price) or pd.isna(mom):
            reason = "insufficient_or_missing_price_history"
        elif (
            len(history) < config.liquidity_window
            or history["volume"].tail(config.liquidity_window).isna().any()
        ):
            reason = "incomplete_liquidity_history"
        elif last_price < config.min_price:
            reason = "price_filter"
        elif dollar_volume < config.min_dollar_volume:
            reason = "liquidity_filter"
        elif pd.isna(quality):
            reason = "missing_stale_or_invalid_fundamental"
        rows.append(
            {
                "asset_id": asset,
                "decision_at": decision_at,
                "momentum": mom,
                "quality": quality,
                "dollar_volume": dollar_volume,
                "close": last_price,
                "industry": str(member.industry),
                "eligible": not reason,
                "exclusion_reason": reason,
            }
        )
    return pd.DataFrame(rows)
