"""Content-derived run identity, code/environment provenance and output checksums."""

import json
import platform
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from importlib.metadata import distributions
from pathlib import Path
from typing import Any

import pandas as pd

from pqr.configs.models import ResearchConfig
from pqr.data.schemas import Dataset


def frame_hash(frame: pd.DataFrame) -> str:
    data = frame.sort_values(list(frame.columns)).to_csv(index=False, float_format="%.17g")
    return sha256(data.encode()).hexdigest()


def code_state(root: Path) -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            return subprocess.check_output(
                ["git", "-C", str(root), *args], stderr=subprocess.DEVNULL, text=True
            ).strip()
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None

    lock = root / "uv.lock"
    package_root = Path(__file__).resolve().parents[1]
    sources = sorted(p for p in package_root.rglob("*") if p.suffix in {".py", ".html"})
    source_hash = sha256(
        b"".join(str(p.relative_to(package_root)).encode() + p.read_bytes() for p in sources)
    ).hexdigest()
    return {
        "git_sha": git("rev-parse", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain")),
        "source_sha256": source_hash,
        "lock_sha256": sha256(lock.read_bytes()).hexdigest() if lock.exists() else None,
    }


def make_manifest(data: Dataset, config: ResearchConfig, root: Path) -> dict[str, Any]:
    content = {
        "config": config.model_dump(),
        "dataset": data.metadata.model_dump(),
        "hashes": {
            name: frame_hash(getattr(data, name)) for name in ("bars", "fundamentals", "universe")
        },
        "code": code_state(root),
    }
    stable = json.dumps(content, sort_keys=True).encode()
    return {
        **content,
        "run_id": sha256(stable).hexdigest()[:16],
        "created_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": dict(sorted((d.metadata["Name"], d.version) for d in distributions())),
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n"
    )


def output_hashes(directory: Path) -> dict[str, str]:
    return {
        str(p.relative_to(directory)): sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.rglob("*"))
        if p.is_file() and p.name != "checksums.json"
    }
