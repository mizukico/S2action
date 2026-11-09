#!/usr/bin/env python3
"""Independently validate an S2Arm resource-pack v2 directory."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path, PurePosixPath


def fail(message: str) -> None:
    raise SystemExit(f"RESOURCE PACK INVALID: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: verify_resource_pack.py PACK_DIR")
    root = Path(sys.argv[1]).resolve()
    manifest_path = root / "manifest.json"
    index_path = root / "index.tsv"
    if not root.is_dir() or not manifest_path.is_file() or not index_path.is_file():
        fail("manifest.json or index.tsv is missing.")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"manifest.json cannot be parsed: {exc}")
    if manifest.get("version") != 2:
        fail(f"unsupported manifest version: {manifest.get('version')!r}")

    index_bytes = index_path.read_bytes()
    if hashlib.sha256(index_bytes).hexdigest() != manifest.get("index_sha256"):
        fail("index.tsv SHA-256 does not match manifest.json.")

    entries: dict[str, tuple[int, str]] = {}
    try:
        for raw in index_bytes.decode("utf-8").splitlines():
            if not raw:
                continue
            parts = raw.split("\t")
            if len(parts) != 3:
                fail("an index.tsv row does not have exactly three columns.")
            rel, size_text, digest = parts
            rel_path = PurePosixPath(rel)
            if rel_path.is_absolute() or ".." in rel_path.parts or rel in {"", ".", "manifest.json", "index.tsv"}:
                fail(f"unsafe or reserved path in index.tsv: {rel!r}")
            size = int(size_text)
            if size < 0 or len(digest) != 64:
                fail(f"invalid size or SHA-256 in index.tsv: {rel!r}")
            if rel in entries:
                fail(f"duplicate path in index.tsv: {rel!r}")
            entries[rel] = (size, digest)
    except UnicodeDecodeError:
        fail("index.tsv is not UTF-8.")

    if not entries:
        fail("index.tsv contains no files.")

    actual: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            fail(f"symbolic link found in resource pack: {path.relative_to(root)}")
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if rel not in {"manifest.json", "index.tsv"}:
                actual.add(rel)

    expected = set(entries)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        fail(f"file set mismatch; missing={missing[:5]}, extra={extra[:5]}")

    total = 0
    for number, (rel, (expected_size, expected_hash)) in enumerate(entries.items(), 1):
        path = root.joinpath(*PurePosixPath(rel).parts)
        size = path.stat().st_size
        if size != expected_size:
            fail(f"size mismatch: {rel} ({size} != {expected_size})")
        if sha256(path) != expected_hash:
            fail(f"SHA-256 mismatch: {rel}")
        total += size
        if number % 10000 == 0:
            print(f"Verified {number:,}/{len(entries):,} files")

    print(f"Verified resource pack v2: {len(entries):,} files, {total / (1024 ** 3):.2f} GiB.")


if __name__ == "__main__":
    main()
