"""Validated, serializable experiment configuration. All costs are assumptions."""

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PQR_", env_file=".env", extra="ignore")
    tiingo_token: str = ""
    sec_user_agent: str = ""


class ResearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    name: str = "momentum-quality"
    mode: Literal["demonstration", "historical"] = "demonstration"
    start: str = "2020-01-01"
    end: str = "2025-12-31"
    initial_nav: float = Field(default=100_000, gt=0)
    min_price: float = Field(default=5, ge=0)
    min_dollar_volume: float = Field(default=10_000_000, ge=0)
    liquidity_window: int = Field(default=60, ge=2)
    momentum_lookback: int = Field(default=252, ge=3)
    momentum_skip: int = Field(default=21, ge=1)
    max_fact_age_days: int = Field(default=550, ge=1)
    top_fraction: float = Field(default=0.2, gt=0, le=1)
    max_weight: float = Field(default=0.1, gt=0, le=1)
    commission_bps: float = Field(default=1, ge=0, le=1000)
    slippage_bps: float = Field(default=5, ge=0, le=1000)
    periods_per_year: int = Field(default=252, ge=1)
    seed: int = 42

    @model_validator(mode="after")
    def sensible(self) -> "ResearchConfig":
        from datetime import date

        if date.fromisoformat(self.start) >= date.fromisoformat(self.end):
            raise ValueError("start must precede end")
        if self.momentum_skip >= self.momentum_lookback:
            raise ValueError("momentum_skip must be less than momentum_lookback")
        return self


def load_config(path: Path) -> ResearchConfig:
    with path.open("rb") as stream:
        return ResearchConfig.model_validate(tomllib.load(stream))
