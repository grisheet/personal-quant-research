"""Exchange sessions and explicit UTC decision/availability times."""

from functools import lru_cache

import exchange_calendars as xcals
import pandas as pd
from exchange_calendars.exchange_calendar import ExchangeCalendar


@lru_cache(maxsize=8)
def calendar(start: str, end: str) -> ExchangeCalendar:
    return xcals.get_calendar(
        "XNYS",
        start=str((pd.Timestamp(start) - pd.Timedelta(days=30)).date()),
        end=str((pd.Timestamp(end) + pd.Timedelta(days=30)).date()),
    )


def sessions(start: str, end: str) -> pd.DatetimeIndex:
    cal = calendar(start, end)
    return pd.DatetimeIndex(cal.sessions_in_range(start, end)).tz_localize(None)


def at_new_york(day: pd.Timestamp, hour: int) -> pd.Timestamp:
    return (
        pd.Timestamp(day.date())
        .tz_localize("America/New_York")
        .replace(hour=hour)
        .tz_convert("UTC")
    )


def next_session(day: pd.Timestamp) -> pd.Timestamp:
    dates = sessions(str(day.date()), str((day + pd.Timedelta(days=14)).date()))
    future = dates[dates > day.normalize().tz_localize(None)]
    return pd.Timestamp(future[0])


def bar_availability(day: pd.Timestamp) -> pd.Timestamp:
    """Assumed backfill latency: next exchange session at 08:00 America/New_York."""
    return at_new_york(next_session(day), 8)


def filing_availability(accepted: pd.Timestamp) -> pd.Timestamp:
    """Wait one complete subsequent trading session, then use next 09:00 decision."""
    if accepted.tzinfo is None:
        raise ValueError("Filing acceptance timestamp must include a timezone")
    local_day = accepted.tz_convert("America/New_York").normalize().tz_localize(None)
    full_processing_day = next_session(local_day)
    return at_new_york(next_session(full_processing_day), 9)


def monthly_execution_sessions(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """First exchange session of each calendar month, including a partial first month."""
    return index[~index.to_period("M").duplicated()]
