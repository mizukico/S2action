#!/usr/bin/env python3
"""Prepare Google Drive inputs using the Bayo3-T secret names."""
from __future__ import annotations
import os, shutil, subprocess, sys
from pathlib import Path
from urllib.parse import urlsplit

ALLOWED = {".nsp", ".xci", ".nsz", ".xcz", ".nup"}

def fail(message: str) -> None:
    raise SystemExit("ERROR: " + message)

def download(url: str, target: Path, label: str, required: bool) -> None:
    if not url.strip():
        if required:
            fail(f"Missing {label} URL secret.")
        print(f"No {label} configured; skipping.")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {label}...")
    # gdown supports the Google Drive share URLs used by Bayo3-T.
    cmd = ["gdown", "--fuzzy", "--continue", url, "-O", str(target)]
    for attempt in range(1, 4):
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
            if target.is_file() and target.stat().st_size:
                print(f"Downloaded {label}: {target.stat().st_size / 1024**3:.2f} GiB")
                return
        except subprocess.CalledProcessError:
            pass
        target.unlink(missing_ok=True)
        if attempt < 3:
            print(f"{label} download attempt {attempt} failed; retrying.")
    fail(f"Failed to download {label} after 3 attempts.")

def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: prepare_inputs.py OUTPUT_DIR")
    out = Path(sys.argv[1]).resolve()
    games = out / "games"
    games.mkdir(parents=True, exist_ok=True)
    # These names intentionally match Bayo3-T; no GAME_URLS/PROD_KEYS aliases.
    download(os.environ.get("Game_URL", ""), games / "game.download", "Game_URL", True)
    download(os.environ.get("Keys_URL", ""), out / "prod.keys", "Keys_URL", True)
    download(os.environ.get("Update_URL", ""), games / "update.download", "Update_URL", False)
    download(os.environ.get("DLC_URL", ""), games / "dlc.download", "DLC_URL", False)
    download(os.environ.get("DLC2_URL", ""), games / "dlc2.download", "DLC2_URL", False)
    # Rename downloaded files to meaningful package suffixes where possible;
    # retain the bytes and let the upstream refresh process inspect containers.
    for p in list(games.iterdir()):
        if p.is_file() and p.name.endswith(".download"):
            p.rename(p.with_name(p.name[:-9]))
    if not any(p.is_file() for p in games.iterdir()):
        fail("No game packages were downloaded.")
    if not (out / "prod.keys").is_file() or (out / "prod.keys").stat().st_size == 0:
        fail("The Keys_URL download is empty.")
    (out / "prod.keys").chmod(0o600)
    print("Prepared game, optional update/DLC packages, and prod.keys.")

if __name__ == "__main__":
    main()
