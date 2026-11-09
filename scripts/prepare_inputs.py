#!/usr/bin/env python3
"""Download user-owned game packages and materialize prod.keys from Actions secrets.

Required secrets:
  GAME_URLS      One direct HTTP(S) download URL per line. URL paths must end in
                 .nsp, .xci, .nsz, .xcz, or .nup.
  PROD_KEYS_B64  Base64-encoded contents of the user's own prod.keys.
URLs and key contents are never printed.
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ALLOWED = {".nsp", ".xci", ".nsz", ".xcz", ".nup"}


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: prepare_inputs.py OUTPUT_DIR")

    raw_urls = os.environ.get("GAME_URLS", "")
    encoded_keys = os.environ.get("PROD_KEYS_B64", "").strip()
    if not raw_urls.strip():
        fail("Missing Actions secret GAME_URLS (one direct package URL per line).")
    if not encoded_keys:
        fail("Missing Actions secret PROD_KEYS_B64.")

    urls = [line.strip() for line in raw_urls.splitlines() if line.strip()]
    if not urls:
        fail("GAME_URLS contains no URLs.")
    if len(urls) > 32:
        fail("GAME_URLS contains more than 32 entries; split the build into smaller inputs.")

    out = Path(sys.argv[1]).resolve()
    games = out / "games"
    games.mkdir(parents=True, exist_ok=True)
    keys = out / "prod.keys"

    try:
        key_bytes = base64.b64decode(encoded_keys, validate=True)
    except Exception:
        fail("PROD_KEYS_B64 is not valid base64.")
    if len(key_bytes) < 32:
        fail("Decoded prod.keys is unexpectedly small; check the secret value.")
    keys.write_bytes(key_bytes)
    keys.chmod(0o600)
    del key_bytes

    seen: set[str] = set()
    for number, url in enumerate(urls, 1):
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            fail(f"GAME_URLS line {number} is not an HTTP(S) URL.")
        filename = unquote(Path(parsed.path).name)
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED:
            fail(f"GAME_URLS line {number} must point directly to an NSP/XCI/NSZ/XCZ/NUP file.")
        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
        if not safe_name or safe_name in {".", ".."}:
            fail(f"GAME_URLS line {number} has an invalid filename.")
        if safe_name in seen:
            safe_name = f"{number:02d}-{safe_name}"
        seen.add(safe_name)
        destination = games / safe_name

        print(f"Downloading package {number}/{len(urls)}: {safe_name}")
        command = [
            "curl", "--fail", "--location", "--silent", "--show-error",
            "--retry", "3", "--retry-all-errors", "--connect-timeout", "30",
            "--output", str(destination), url,
        ]
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError:
            destination.unlink(missing_ok=True)
            fail(f"Download failed for package {number}; check the URL or its access requirements.")
        if not destination.is_file() or destination.stat().st_size == 0:
            fail(f"Downloaded package {number} is empty.")
        free = shutil.disk_usage(out).free / (1024 ** 3)
        print(f"Downloaded {destination.stat().st_size / (1024 ** 3):.2f} GiB; free space: {free:.1f} GiB")

    print(f"Prepared {len(urls)} game package(s); prod.keys is stored outside the repository.")


if __name__ == "__main__":
    main()
