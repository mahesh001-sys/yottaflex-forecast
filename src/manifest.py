"""Create and verify manifests for generated CSV datasets.

Run from the repository root:
    python -m src.manifest
    python -m src.manifest --verify
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_DATA_DIR = Path("data/raw")
MANIFEST_NAME = "manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(data_dir: str | Path = DEFAULT_DATA_DIR) -> dict[str, Any]:
    """Return metadata and SHA-256 checksums for each CSV in data_dir."""
    directory = Path(data_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"Data directory does not exist: {directory}")

    entries = []
    for path in sorted(directory.glob("*.csv")):
        with path.open("r", newline="", encoding="utf-8-sig") as file:
            row_count = sum(1 for _ in csv.DictReader(file))

        entries.append({
            "filename": path.name,
            "row_count": row_count,
            "file_size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        })

    return {"files": entries}


def write_manifest(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    manifest_path: str | Path | None = None,
) -> Path:
    """Write a fresh manifest and return its path."""
    directory = Path(data_dir)
    target = Path(manifest_path) if manifest_path else directory / MANIFEST_NAME
    target.parent.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(directory)
    target.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def verify_manifest(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    manifest_path: str | Path | None = None,
) -> bool:
    """Compare current CSV metadata and checksums with the saved manifest."""
    directory = Path(data_dir)
    target = Path(manifest_path) if manifest_path else directory / MANIFEST_NAME

    if not target.is_file():
        raise FileNotFoundError(f"Manifest does not exist: {target}")

    expected = json.loads(target.read_text(encoding="utf-8"))
    actual = build_manifest(directory)

    if expected != actual:
        expected_files = {
            item["filename"]: item for item in expected.get("files", [])
        }
        actual_files = {
            item["filename"]: item for item in actual["files"]
        }

        for filename in sorted(expected_files.keys() | actual_files.keys()):
            if expected_files.get(filename) != actual_files.get(filename):
                print(f"Mismatch: {filename}")
        return False

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or verify a manifest for CSV dataset files."
    )
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify the dataset against its existing manifest.",
    )
    parser.add_argument(
        "--manifest",
        help="Manifest path (defaults to <data-dir>/manifest.json).",
    )
    args = parser.parse_args()

    if args.verify:
        if verify_manifest(args.data_dir, args.manifest):
            print(f"Manifest verified: {args.data_dir}")
            return 0
        print("Manifest verification failed.")
        return 1

    path = write_manifest(args.data_dir, args.manifest)
    print(f"Manifest written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())