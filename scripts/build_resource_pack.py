#!/usr/bin/env python3
"""Run upstream S2Arm's oneclick builder and retain only the verified resource pack."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--keys", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--title-id", default="")
    parser.add_argument("--game-name", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    upstream = args.upstream.resolve()
    game_dir = args.input.resolve()
    keys = args.keys.resolve()
    output = args.output.resolve()
    oneclick = upstream / "pack/oneclick/oneclick.sh"

    if not oneclick.is_file():
        raise SystemExit(f"Upstream oneclick script not found: {oneclick}")
    if not game_dir.is_dir() or not any(game_dir.iterdir()):
        raise SystemExit("Game input directory is empty.")
    if not keys.is_file():
        raise SystemExit("prod.keys file is missing.")

    output.mkdir(parents=True, exist_ok=True)
    events = output / "events.jsonl"
    command = [
        "bash", str(oneclick), str(game_dir),
        "--keys", str(keys),
        "--out", str(output / "build"),
        "--sign", "adhoc",
        "--events", str(events),
    ]
    if args.title_id.strip():
        command.extend(["--title-id", args.title_id.strip()])
    if args.game_name.strip():
        command.extend(["--name", args.game_name.strip()])

    env = os.environ.copy()
    env["S2A_PYTHON"] = sys.executable
    env["S2A_PY"] = sys.executable
    env["S2A_BEAT_S"] = env.get("S2A_BEAT_S", "30")
    env["PYTHONUNBUFFERED"] = "1"

    print("Starting upstream S2Arm oneclick build (iOS pipeline; resource pack is the deliverable).")
    print(f"Upstream commit: {subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()}")
    print(f"Game package files: {sum(1 for p in game_dir.rglob('*') if p.is_file())}")
    print(f"Output directory: {output}")

    result = subprocess.run(command, cwd=upstream, env=env, check=False)
    if result.returncode != 0:
        raise SystemExit(f"Upstream build failed with exit code {result.returncode}.")

    result_event = None
    if events.is_file():
        for line in events.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("ev") == "result":
                result_event = event
    if not result_event or result_event.get("ok") is not True:
        raise SystemExit("Upstream process exited without a successful result event.")

    pack_value = result_event.get("pack")
    if not isinstance(pack_value, str) or not pack_value:
        raise SystemExit("Upstream result event did not contain a resource-pack path.")
    pack_path = Path(pack_value).resolve()
    if not pack_path.is_dir():
        raise SystemExit(f"Upstream resource-pack directory not found: {pack_path}")

    validator = Path(__file__).with_name("verify_resource_pack.py")
    subprocess.run([sys.executable, str(validator), str(pack_path)], cwd=upstream, env=env, check=True)

    # Upstream oneclick also creates an IPA. Keep the pack only; the intermediate
    # IPA, extraction and private build roots can consume many additional GiB.
    build_root = output / "build"
    for name in ("roots", "extract", "ns2_dump"):
        shutil.rmtree(build_root / name, ignore_errors=True)
    for ipa in build_root.rglob("*.ipa"):
        ipa.unlink(missing_ok=True)

    # The hosted runner is ephemeral. Remove downloaded source packages and keys
    # once the resource pack has passed its independent integrity check.
    shutil.rmtree(game_dir.parent, ignore_errors=True)

    output_file = Path(os.environ.get("GITHUB_OUTPUT", output / "build-output.txt"))
    with output_file.open("a", encoding="utf-8") as stream:
        stream.write(f"pack_path={pack_path}\n")
    print(f"Verified resource pack: {pack_path}")
    print("Removed intermediate IPA, extraction data, private roots, downloaded game files, and temporary keys.")


if __name__ == "__main__":
    main()
