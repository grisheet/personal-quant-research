"""Bounded retries, polite throttling and content-addressed raw response snapshots."""

import json
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx

from pqr.data.schemas import DataError


class SnapshotClient:
    def __init__(
        self,
        directory: Path,
        *,
        client: httpx.Client | None = None,
        requests_per_second: float = 2.0,
        attempts: int = 4,
        refresh: bool = False,
    ) -> None:
        if requests_per_second <= 0 or attempts < 1:
            raise ValueError("Invalid HTTP limits")
        self.directory = directory
        self.refresh = refresh
        self.client = client or httpx.Client(timeout=30, follow_redirects=False)
        self._owns_client = client is None
        self.interval = 1 / requests_per_second
        self.attempts = attempts
        self.last_request = 0.0

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        license_note: str,
    ) -> tuple[Any, datetime]:
        # Tokens belong in headers, never query parameters, logs, filenames or manifests.
        public_params = params or {}
        if any(key.lower() in {"token", "apikey", "api_key", "key"} for key in public_params):
            raise DataError("Credentials must not appear in query parameters")
        request_key = sha256(
            json.dumps({"url": url, "params": public_params}, sort_keys=True).encode()
        ).hexdigest()
        pointer = self.directory / f"request-{request_key}.json"
        if not self.refresh and pointer.exists():
            cached = json.loads(pointer.read_text())
            body = (self.directory / f"{cached['sha256']}.json").read_bytes()
            if sha256(body).hexdigest() != cached["sha256"]:
                raise DataError("Cached snapshot checksum mismatch")
            return json.loads(body), datetime.fromisoformat(cached["retrieved_at"])
        for attempt in range(self.attempts):
            time.sleep(max(0.0, self.interval - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                response = self.client.get(url, headers=headers, params=public_params)
            except httpx.TransportError as exc:
                if attempt + 1 == self.attempts:
                    raise DataError("Provider transport failed after bounded retries") from exc
                time.sleep(2**attempt)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 < self.attempts:
                    retry_after = response.headers.get("Retry-After", "")
                    delay = min(float(retry_after), 30) if retry_after.isdigit() else 2**attempt
                    time.sleep(delay)
                    continue
            if response.is_error:
                raise DataError(f"Provider request failed: HTTP {response.status_code}")
            try:
                payload = response.json()
            except ValueError as exc:
                raise DataError("Provider returned invalid JSON") from exc
            retrieved = datetime.now(UTC)
            body = response.content
            digest = sha256(body).hexdigest()
            self.directory.mkdir(parents=True, exist_ok=True)
            destination = self.directory / f"{digest}.json"
            if not destination.exists():
                destination.write_bytes(body)
            metadata = {
                "url": url,
                "params": public_params,
                "retrieved_at": retrieved.isoformat(),
                "sha256": digest,
                "license": license_note,
                "status_code": response.status_code,
            }
            # An append-only retrieval manifest preserves observations of identical bytes.
            with (self.directory / "retrievals.jsonl").open("a") as stream:
                stream.write(json.dumps(metadata, sort_keys=True) + "\n")
            pointer.write_text(json.dumps(metadata, sort_keys=True) + "\n")
            return payload, retrieved
        raise DataError("Provider exhausted retries")
