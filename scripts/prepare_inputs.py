#!/usr/bin/env python3
"""Prepare Google Drive inputs using the Bayo3-T secret names."""
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path
from urllib.parse import urlsplit


ALLOWED = {".nsp", ".xci", ".nsz", ".xcz", ".nup"}


def fail(message: str) -> None:
    raise SystemExit("ERROR: " + message)


def download(url: str, target: Path, label: str, required: bool, package: bool = False) -> None:
    if not url.strip():
        if required:
            fail(f"Missing {label} URL secret.")
        print(f"No {label} configured; skipping.")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {label}...")
    for attempt in range(1, 4):
        try:
            # gdown v6 removed --fuzzy. Current versions automatically
            # extract file IDs from standard Google Drive sharing URLs.
            subprocess.run(
                ["gdown", url, "--continue", "-O", str(target)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            if target.is_file() and target.stat().st_size:
                break
        except Exception as exc:
            print(f"{label} download attempt {attempt} failed: {exc}")
        target.unlink(missing_ok=True)
        if attempt < 3:
            print(f"{label} download attempt {attempt} failed; retrying.")
    else:
        fail(f"Failed to download {label} after 3 attempts.")

    if package:
        suffix = Path(urlsplit(url).path).suffix.lower()
        if suffix not in ALLOWED:
            with target.open("rb") as stream:
                magic = stream.read(4)
                stream.seek(0x100)
                xci_magic = stream.read(4)
            if magic == b"PFS0":
                suffix = ".nsp"
            elif xci_magic == b"HEAD":
                suffix = ".xci"
            else:
                fail(f"{label} is not a recognizable NSP/XCI container; use a direct package URL.")
        final = target.with_suffix(suffix)
        target.rename(final)
        target = final

    print(f"Downloaded {label}: {target.stat().st_size / 1024**3:.2f} GiB")


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: prepare_inputs.py OUTPUT_DIR")
    out = Path(sys.argv[1]).resolve()
    games = out / "games"
    games.mkdir(parents=True, exist_ok=True)
    # Exact Bayo3-T names; no GAME_URLS/PROD_KEYS aliases.
    download(os.environ.get("Game_URL", ""), games / "game.download", "Game_URL", True, True)
    download(os.environ.get("Keys_URL", ""), out / "prod.keys", "Keys_URL", True)
    download(os.environ.get("Update_URL", ""), games / "update.download", "Update_URL", False, True)
    download(os.environ.get("DLC_URL", ""), games / "dlc.download", "DLC_URL", False, True)
    download(os.environ.get("DLC2_URL", ""), games / "dlc2.download", "DLC2_URL", False, True)
    if not any(p.is_file() for p in games.iterdir()):
        fail("No game packages were downloaded.")
    if not (out / "prod.keys").is_file() or (out / "prod.keys").stat().st_size == 0:
        fail("The Keys_URL download is empty.")
    (out / "prod.keys").chmod(0o600)
    print("Prepared game, optional update/DLC packages, and prod.keys.")


if __name__ == "__main__":
    main()
