"""Mocked provider contract tests; payloads are deliberately artificial, never live responses."""

from datetime import date
from pathlib import Path

import httpx
import pandas as pd
import pytest
import respx

from pqr.data.providers.http import SnapshotClient
from pqr.data.providers.sec import SecFundamentalsProvider, extract_annual_quality
from pqr.data.providers.tiingo import TiingoPriceProvider
from pqr.data.schemas import DataError


@respx.mock
def test_tiingo_normalization_snapshot_cache_and_secrets(tmp_path: Path) -> None:
    route = respx.get("https://api.tiingo.com/tiingo/daily/TEST/prices").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "date": "2024-01-02T00:00:00Z",
                    "close": 100,
                    "volume": 1000,
                    "adjClose": 50,
                    "splitFactor": 1,
                    "divCash": 0,
                }
            ],
        )
    )
    client = SnapshotClient(tmp_path, requests_per_second=1000)
    provider = TiingoPriceProvider("artificial-test-token", client)
    frame = provider.fetch("TEST", "TEST_ID", date(2024, 1, 2), date(2024, 1, 3))
    cached = provider.fetch("TEST", "TEST_ID", date(2024, 1, 2), date(2024, 1, 3))
    assert route.call_count == 1
    pd.testing.assert_frame_equal(frame, cached)
    assert frame.iloc[0]["available_at"] == pd.Timestamp("2024-01-03T13:00:00Z")
    assert frame.iloc[0]["availability_basis"] == "assumed"
    assert route.calls[0].request.headers["Authorization"] == "Token artificial-test-token"
    for path in tmp_path.iterdir():
        assert "artificial-test-token" not in path.read_text()
    client.close()


@respx.mock
def test_rate_limit_retry_and_invalid_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("pqr.data.providers.http.time.sleep", lambda _: None)
    route = respx.get("https://provider.example/test").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(503),
            httpx.Response(200, json={"artificial": True}),
        ]
    )
    client = SnapshotClient(tmp_path, attempts=3)
    value, _ = client.get_json("https://provider.example/test", license_note="test fixture")
    assert value == {"artificial": True}
    assert route.call_count == 3
    with pytest.raises(DataError, match="Credentials"):
        client.get_json(
            "https://provider.example/test", params={"token": "secret"}, license_note="test"
        )
    client.close()


@respx.mock
def test_cache_tampering_detected(tmp_path: Path) -> None:
    respx.get("https://provider.example/test").mock(return_value=httpx.Response(200, json=[1]))
    client = SnapshotClient(tmp_path)
    client.get_json("https://provider.example/test", license_note="test")
    source = [p for p in tmp_path.glob("*.json") if not p.name.startswith("request-")][0]
    source.write_text("[2]")
    with pytest.raises(DataError, match="checksum"):
        client.get_json("https://provider.example/test", license_note="test")
    client.close()


@pytest.mark.parametrize("status", [401, 403, 404, 500])
@respx.mock
def test_http_error_does_not_become_market_data(tmp_path: Path, status: int) -> None:
    respx.get("https://provider.example/test").mock(return_value=httpx.Response(status))
    client = SnapshotClient(tmp_path, attempts=1)
    with pytest.raises(DataError, match="HTTP"):
        client.get_json("https://provider.example/test", license_note="test")
    client.close()


def artificial_sec_payload() -> dict:
    return {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "val": 10.0,
                                "accn": "ARTIFICIAL-1",
                            }
                        ]
                    }
                },
                "Assets": {
                    "units": {
                        "USD": [
                            {"end": "2022-12-31", "val": 100.0, "accn": "ARTIFICIAL-1"},
                            {"end": "2023-12-31", "val": 120.0, "accn": "ARTIFICIAL-1"},
                        ]
                    }
                },
            }
        }
    }


def artificial_filings() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "accessionNumber": ["ARTIFICIAL-1"],
            "form": ["10-K"],
            "acceptanceDateTime": ["2024-02-01T21:00:00Z"],
        }
    )


def test_sec_annual_context_and_lag() -> None:
    exclusions: list[dict[str, str]] = []
    result = extract_annual_quality(
        artificial_sec_payload(),
        artificial_filings(),
        "TEST",
        pd.Timestamp("2024-03-01T00:00:00Z"),
        exclusions,
    )
    assert len(result) == 1
    assert result.iloc[0]["net_income"] == 10
    assert result.iloc[0]["assets_begin"] == 100
    assert result.iloc[0]["assets_end"] == 120
    assert result.iloc[0]["available_at"] == pd.Timestamp("2024-02-05T14:00:00Z")
    assert not exclusions


def test_sec_ambiguous_context_and_missing_tags_rejected() -> None:
    payload = artificial_sec_payload()
    payload["facts"]["us-gaap"]["Assets"]["units"]["USD"].append(
        {"end": "2022-12-31", "val": 101.0, "accn": "ARTIFICIAL-1"}
    )
    exclusions: list[dict[str, str]] = []
    assert extract_annual_quality(
        payload, artificial_filings(), "TEST", pd.Timestamp("2024-03-01T00:00:00Z"), exclusions
    ).empty
    assert "ambiguous" in exclusions[0]["reason"]
    assert extract_annual_quality(
        {}, artificial_filings(), "TEST", pd.Timestamp("2024-03-01T00:00:00Z"), []
    ).empty


@respx.mock
def test_sec_paginated_filing_metadata(tmp_path: Path) -> None:
    filings = artificial_filings().to_dict("list")
    respx.get("https://data.sec.gov/submissions/CIK0000000001.json").mock(
        return_value=httpx.Response(
            200,
            json={"filings": {"recent": {k: [] for k in filings}, "files": [{"name": "old.json"}]}},
        )
    )
    archive = respx.get("https://data.sec.gov/submissions/old.json").mock(
        return_value=httpx.Response(200, json=filings)
    )
    respx.get("https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json").mock(
        return_value=httpx.Response(200, json=artificial_sec_payload())
    )
    client = SnapshotClient(tmp_path, requests_per_second=1000)
    provider = SecFundamentalsProvider("Fixture test@example.com", client)
    frame = provider.fetch("1", "TEST")
    assert len(frame) == 1
    assert archive.called
    with pytest.raises(DataError, match="CIK"):
        provider.fetch("not-a-cik", "TEST")
    client.close()


def test_credentials_required(tmp_path: Path) -> None:
    client = SnapshotClient(tmp_path)
    with pytest.raises(DataError, match="TOKEN"):
        TiingoPriceProvider("", client)
    with pytest.raises(DataError, match="contact email"):
        SecFundamentalsProvider("", client)
    client.close()


def test_file_providers(tmp_path: Path) -> None:
    from pqr.data.providers.files import FilePriceProvider, FileUniverseProvider

    frame = pd.DataFrame(
        {
            "asset_id": ["TEST", "TEST", "OTHER"],
            "session": ["2024-01-02", "2024-01-03", "2024-01-02"],
            "close": [1.0, 2.0, 3.0],
        }
    )
    path = tmp_path / "bars.csv"
    frame.to_csv(path, index=False)
    provider = FilePriceProvider(path)
    assert provider.fetch("TEST", "TEST", date(2024, 1, 2), date(2024, 1, 2))[
        "close"
    ].to_list() == [1.0]
    assert len(FileUniverseProvider(path).fetch()) == 3
    parquet = tmp_path / "bars.parquet"
    frame.to_parquet(parquet)
    assert (
        len(FilePriceProvider(parquet).fetch("TEST", "TEST", date(2024, 1, 2), date(2024, 1, 3)))
        == 2
    )


@respx.mock
def test_cli_ingest_with_artificial_responses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from pqr.cli import app
    from pqr.data.schemas import load_dataset

    monkeypatch.setenv("PQR_TIINGO_TOKEN", "artificial-token")
    monkeypatch.setenv("PQR_SEC_USER_AGENT", "Fixture test@example.com")
    monkeypatch.setattr("pqr.data.providers.http.time.sleep", lambda _: None)
    mapping = tmp_path / "mapping.csv"
    mapping.write_text(
        "asset_id,symbol,cik,member_from,member_to,available_at,industry,is_benchmark\n"
        "TEST,TEST,1,2020-01-01,,2019-01-01T00:00:00Z,Test,false\n"
        "BENCH,BENCH,,2020-01-01,,2019-01-01T00:00:00Z,Test,true\n"
    )
    prices = [
        {
            "date": "2024-01-02T00:00:00Z",
            "close": 50,
            "adjClose": 50,
            "volume": 1000,
            "splitFactor": 1,
            "divCash": 0,
        }
    ]
    for symbol in ("TEST", "BENCH"):
        respx.get(f"https://api.tiingo.com/tiingo/daily/{symbol}/prices").mock(
            return_value=httpx.Response(200, json=prices)
        )
    respx.get("https://data.sec.gov/submissions/CIK0000000001.json").mock(
        return_value=httpx.Response(
            200, json={"filings": {"recent": artificial_filings().to_dict("list"), "files": []}}
        )
    )
    respx.get("https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json").mock(
        return_value=httpx.Response(200, json=artificial_sec_payload())
    )
    output = tmp_path / "dataset"
    result = CliRunner().invoke(
        app,
        [
            "ingest",
            "--mapping",
            str(mapping),
            "--start",
            "2024-01-01",
            "--end",
            "2024-03-01",
            "--output",
            str(output),
            "--snapshots",
            str(tmp_path / "raw"),
        ],
    )
    assert result.exit_code == 0, result.output
    data = load_dataset(output)
    assert data.metadata.kind == "retrospective"
    assert len(data.bars) == 2 and len(data.fundamentals) == 1
