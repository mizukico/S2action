#!/usr/bin/env python3
"""Download Baidu Netdisk inputs using Bayo3-T-compatible path names."""
from __future__ import annotations
import os, shutil, subprocess, sys
from pathlib import Path

EXTS={".nsp",".xci",".nsz",".xcz",".nup"}

def fail(s): raise SystemExit("ERROR: "+s)
def run_download(binary: str, remote: str, stage: Path, label: str, required: bool, directory: bool=False):
    if not remote.strip():
        if required: fail(f"Missing {label} path.")
        print(f"No {label} path configured; skipping.")
        return []
    stage.mkdir(parents=True, exist_ok=True)
    cmd=[binary,"download",remote,"--saveto",str(stage),"--ow","-p","16","-l","2" if directory else "1","--retry","5"]
    subprocess.run(cmd,check=True)
    files=[p for p in stage.rglob("*") if p.is_file()]
    if not directory and len(files)!=1:
        fail(f"{label} path must point to exactly one file.")
    if required and not files: fail(f"No files downloaded for {label}.")
    return files

def main():
    if len(sys.argv)!=3: fail("usage: prepare_baidu_inputs.py BAIDUPCS_BIN OUTPUT_DIR")
    binary=str(Path(sys.argv[1]).resolve()); out=Path(sys.argv[2]).resolve()
    games=out/"games"; games.mkdir(parents=True,exist_ok=True)
    paths={
      "game_path":os.environ.get("game_path",""),
      "keys_path":os.environ.get("keys_path",""),
      "update_path":os.environ.get("update_path",""),
      "dlc_path":os.environ.get("dlc_path",""),
      "dlc2_path":os.environ.get("dlc2_path",""),
    }
    gamefiles=run_download(binary,paths["game_path"],out/"game-source","game_path",True,True)
    packages=[p for p in gamefiles if p.suffix.lower() in EXTS]
    if not packages: fail("No NSP/XCI/NSZ/XCZ/NUP files found under game_path.")
    for p in packages:
        dest=games/p.name
        if dest.exists(): fail("Duplicate game package filename: "+p.name)
        shutil.move(str(p),str(dest))
    keyfiles=run_download(binary,paths["keys_path"],out/"keys-source","keys_path",True)
    shutil.move(str(keyfiles[0]),str(out/"prod.keys"))
    for name,label in [("update_path","update"),("dlc_path","dlc"),("dlc2_path","dlc2")]:
        files=run_download(binary,paths[name],out/(label+"-source"),name,False)
        if files:
            p=files[0]
            dest=games/(label+p.suffix.lower())
            if dest.exists(): fail("Duplicate optional package target: "+dest.name)
            shutil.move(str(p),str(dest))
    (out/"prod.keys").chmod(0o600)
    print(f"Prepared {len(packages)} game package(s), optional update/DLC files, and prod.keys.")

if __name__=="__main__": main()
