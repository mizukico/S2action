#!/usr/bin/env python3
"""Run upstream S2Arm, clean source packages after refresh, and verify its resource pack."""
from __future__ import annotations

import argparse
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


def install_post_refresh_cleanup(oneclick: Path, game_dir: Path, keys: Path) -> None:
    """Inject cleanup immediately after refresh succeeds, before IPA packaging.

    S2Arm still needs the original packages during source-version validation and
    DLC extraction in refresh.sh. Once refresh returns successfully, subsequent
    iOS packaging consumes the seeded/refreshed roots, not the original XCI/NSP.
    """
    source = oneclick.read_text(encoding="utf-8")
    marker = 't "   $(tail -1 "$OUT/logs/refresh.log" | cut -c1-1200)"\nif [ "$TGT" = android ]; then'
    if source.count(marker) != 1:
        raise SystemExit(
            "Cannot safely place input cleanup: upstream oneclick refresh-success "
            "marker was not found exactly once. No source files were deleted."
        )

    cleanup = """t "   $(tail -1 "$OUT/logs/refresh.log" | cut -c1-1200)"
# CI-only disk cleanup: refresh.sh has completed source-version validation and
# DLC extraction; IPA/resource-pack packaging now uses the seeded roots.
if [ "${S2A_CI_CLEAN_INPUTS:-0}" = 1 ]; then
  case "$SRC" in
    "$S2A_CI_INPUT_DIR") ;;
    *) die "Refusing to clean unexpected source directory: $SRC" ;;
  esac
  find "$SRC" -type f \\( -iname '*.xci' -o -iname '*.nsp' -o -iname '*.nsz' -o -iname '*.xcz' -o -iname '*.nup' \\) -delete
  rm -f "$S2A_KEYS"
  rmdir "$SRC" 2>/dev/null || true
  t "   已在刷新及 DLC 提取完成后删除原始游戏包和 prod.keys，释放磁盘空间"
fi
if [ "$TGT" = android ]; then"""
    oneclick.write_text(source.replace(marker, cleanup), encoding="utf-8")


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
    install_post_refresh_cleanup(oneclick, game_dir, keys)
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
    env["S2A_CI_CLEAN_INPUTS"] = "1"
    env["S2A_CI_INPUT_DIR"] = str(game_dir)
    print("Starting upstream S2Arm oneclick build; source cleanup is scheduled after refresh succeeds.")
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
                import json
                event = json.loads(line)
            except Exception:
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

    build_root = output / "build"
    for name in ("roots", "extract", "ns2_dump"):
        shutil.rmtree(build_root / name, ignore_errors=True)
    for ipa in build_root.rglob("*.ipa"):
        ipa.unlink(missing_ok=True)

    # Defensive cleanup for early upstream exits or any files not removed by hook.
    shutil.rmtree(game_dir.parent, ignore_errors=True)

    output_file = Path(os.environ.get("GITHUB_OUTPUT", output / "build-output.txt"))
    with output_file.open("a", encoding="utf-8") as stream:
        stream.write(f"pack_path={pack_path}\n")
    print(f"Verified resource pack: {pack_path}")
    print("Removed intermediate IPA, extraction data, private roots, downloaded game files, and temporary keys.")


if __name__ == "__main__":
    main()
