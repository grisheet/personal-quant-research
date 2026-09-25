"""All test data are artificial and must never be presented as market observations."""

import pandas as pd
import pytest

from pqr.data.fixtures import verification_dataset
from pqr.data.schemas import Dataset


@pytest.fixture(scope="session")
def fixture_data() -> Dataset:
    return verification_dataset()


@pytest.fixture()
def small_returns() -> pd.DataFrame:
    return pd.DataFrame(
        {"A": [0.0, 0.1, -0.05, 0.02], "B": [0.0, -0.1, 0.05, 0.01]},
        index=pd.bdate_range("2024-01-02", periods=4),
    )
