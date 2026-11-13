#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S2Arm Resource Packager GUI.

Select the S2Arm installation root and a built game directory. The tool reads
Title ID from game.json, finds image/ios/pack, verifies the prebuilt game.img from S2Arm v0.3.3, then writes <GameName>_pack.zip.
The ZIP contains <TitleID>/资源包/ and can be extracted into the corresponding game folder.
Python 3.10+; standard library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import struct
import tempfile
import threading
import time
import zipfile
from pathlib import Path, PurePosixPath
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "S2Arm Resource Packager"

TEXT = {
    "zh": {},
    "en": {
        "读取 game.json 的 Title ID，校验 S2Arm 已生成的 game.img，并生成可直接解压到 iPhone games 文件夹的 ZIP": "Read the Title ID from game.json, verify the prebuilt game.img, and create a ZIP ready for the iPhone games folder.",
        "S2Arm 项目安装目录": "S2Arm installation directory",
        "已构建游戏目录（游戏名这一层）": "Built game directory (game-name folder)",
        "ZIP 输出目录（默认游戏目录）": "ZIP output directory (defaults to game folder)",
        "自动读取的 Title ID": "Detected Title ID",
        "来源：所选游戏目录/game.json → id": "Source: selected game folder/game.json → id",
        "执行日志": "Execution log", "等待选择目录": "Select the directories to begin",
        "校验资源包并生成 ZIP": "Verify pack and create ZIP", "浏览…": "Browse...",
        "选择 S2Arm 项目安装目录（例如 E:\\\\ProjectIOS\\\\S2Arm）": "Select the S2Arm project directory (not required for packaging)",
        "选择游戏名目录（例如 E:\\\\nisshell\\\\S2\\\\games\\\\the 1st）": "Select the built game folder",
        "选择 ZIP 输出目录（默认是游戏目录）": "Select ZIP output directory",
        "无法读取游戏信息": "Unable to read game information", "未找到资源包": "Resource pack not found",
        "目录不完整": "Missing directories", "请选择 S2Arm 项目目录、游戏名目录和 ZIP 输出目录。": "Select the S2Arm installation, game, and ZIP output directories.",
        "资源包目录不存在": "Resource pack directory not found", "游戏信息错误": "Invalid game information",
        "覆盖现有 ZIP？": "Overwrite existing ZIP?", "是否覆盖已有文件？": "Overwrite the existing file?",
        "正在处理……": "Processing...", "正在取消……": "Cancelling...", "取消打包": "Cancel packaging", "已取消": "Cancelled", "完成": "Completed", "失败": "Failed",
        "打包完成": "Packaging complete", "资源包已生成：": "Resource pack created:", "打包失败": "Packaging failed"
    }
}

def tr(value: str, lang: str = "zh") -> str:
    return TEXT.get(lang, {}).get(value, value)


# Explicit translations for stable messages. Dynamic paths, values and exception
# details are handled by the patterns below; unknown upstream text is preserved.
LOG_TRANSLATIONS = {
    "游戏目录": "Game directory",
    "Title ID": "Title ID",
    "资源包目录": "Resource pack directory",
    "manifest version": "Manifest version",
    "索引文件": "indexed files",
    "已准备索引文件": "Prepared indexed files",
    "主程序": "Main program",
    "RomFS 校验通过": "RomFS verification passed",
    "完成": "Completed",
    "错误": "Error",
}

def localize_log(message: str, lang: str) -> str:
    if lang != "en":
        return message

    # Exact/dynamic messages emitted by this application.
    patterns = (
        (r"Title ID：[0-9A-Fa-f]{16}（来自 game\.json）",
         lambda m: "Title ID: " + re.search(r"[0-9A-Fa-f]{16}", m.group(0)).group(0) + " (from game.json)"),
        (r"Title ID：([0-9A-Fa-f]{16})", lambda m: f"Title ID: {m.group(1)}"),
        (r"已定位资源包目录：(.*)", lambda m: f"Resource pack directory found: {m.group(1)}"),
        (r"未找到预期资源包目录：(.*)", lambda m: f"Expected resource pack directory not found: {m.group(1)}"),
        (r"游戏目录：(.*)", lambda m: f"Game directory: {m.group(1)}"),
        (r"资源包目录：(.*)", lambda m: f"Resource pack directory: {m.group(1)}"),
        (r"找不到固定资源包目录：(.*)", lambda m: f"Required resource pack directory not found: {m.group(1)}"),
        (r"资源包目录不存在：(.*)", lambda m: f"Resource pack directory does not exist: {m.group(1)}"),
        (r"游戏目录缺少 game\.json：(.*)", lambda m: f"Game directory is missing game.json: {m.group(1)}"),
        (r"game\.json 无法解析：(.*)", lambda m: f"Unable to parse game.json: {m.group(1)}"),
        (r"index\.tsv 第 (\d+) 行不是三列格式。", lambda m: f"index.tsv line {m.group(1)} does not contain exactly three columns."),
        (r"index\.tsv 第 (\d+) 行文件大小无效。", lambda m: f"Invalid file size on index.tsv line {m.group(1)}."),
        (r"index\.tsv 第 (\d+) 行大小或 SHA256 无效：(.*)", lambda m: f"Invalid size or SHA256 on index.tsv line {m.group(1)}: {m.group(2)}"),
        (r"资源索引包含不安全路径：(.*)", lambda m: f"Resource index contains an unsafe path: {m.group(1)}"),
        (r"资源索引包含盘符路径：(.*)", lambda m: f"Resource index contains a drive-letter path: {m.group(1)}"),
        (r"资源包缺少索引文件：(.*)", lambda m: f"Indexed resource file is missing from the pack: {m.group(1)}"),
        (r"文件大小与 index\.tsv 不符：(.*)", lambda m: f"File size does not match index.tsv: {m.group(1)}"),
        (r"RomFS 分片缺失：(.*)", lambda m: f"RomFS fragment is missing: {m.group(1)}"),
        (r"拼接后的镜像大小不正确：(.*)", lambda m: f"Assembled image has an incorrect size: {m.group(1)}"),
        (r"拼接后的镜像 SHA256 不正确：(.*)", lambda m: f"Assembled image SHA256 is incorrect: {m.group(1)}"),
        (r"找不到 S2Arm 原生脚本或依赖。请选择 S2Arm 项目安装目录，其中应有 pack/romfs_image\.py 和 tools/sha256_fast\.py。",
         lambda m: "S2Arm native scripts or dependencies were not found. Select the S2Arm project directory (kept for compatibility; not needed to package) containing pack/romfs_image.py and tools/sha256_fast.py."),
        (r"无法加载原生脚本：(.*)", lambda m: f"Unable to load the native script: {m.group(1)}"),
        (r"无法保存路径配置：(.*)", lambda m: f"Unable to save path configuration: {m.group(1)}"),
        (r"找不到：(.*)", lambda m: f"Not found: {m.group(1)}"),
        (r"缺少固定目录：\s*(.*)", lambda m: f"Required directory is missing:\n{m.group(1)}"),
        (r"imgmap 格式错误：(.*)", lambda m: f"Invalid imgmap format: {m.group(1)}"),
        (r"imgmap 文件数或长度不匹配：(.*)", lambda m: f"imgmap file count or length mismatch: {m.group(1)}"),
        (r"只支持 manifest version 2，当前为 (.*)", lambda m: f"Only manifest version 2 is supported; current version: {m.group(1)}"),
        (r"index\.tsv 有重复路径：(.*)", lambda m: f"index.tsv contains a duplicate path: {m.group(1)}"),
        (r"index\.tsv 不是 UTF-8：(.*)", lambda m: f"index.tsv is not UTF-8: {m.group(1)}"),
        (r"资源包缺少索引文件：(.*)", lambda m: f"Resource pack is missing indexed file: {m.group(1)}"),
        (r"文件大小与 index\.tsv 不符：(.*)", lambda m: f"File size does not match index.tsv: {m.group(1)}"),
        (r"文件大小无效", lambda m: "Invalid file size"),
        (r"大小或 SHA256 无效：(.*)", lambda m: f"Invalid size or SHA256: {m.group(1)}"),
        (r"找不到 S2Arm 原生脚本或依赖.*", lambda m: "S2Arm native scripts or dependencies were not found. Select the S2Arm installation directory containing pack/romfs_image.py and tools/sha256_fast.py."),
        (r"game\.json 顶层 id 字段不是有效的 16 位十六进制 Title ID。", lambda m: "The top-level id field in game.json is not a valid 16-digit hexadecimal Title ID."),
        (r"image/ios/pack 缺少 index\.tsv 或 manifest\.json。", lambda m: "image/ios/pack is missing index.tsv or manifest.json."),
        (r"index\.tsv 中没有 romfs\.img，无法拼接 RomFS。", lambda m: "No romfs.img entry was found in index.tsv; cannot assemble RomFS."),
        (r"romfs_image\.py 缺少 parse_index\(\) 或 materialize\(\)。", lambda m: "romfs_image.py is missing parse_index() or materialize()."),
        (r"manifest\.json 无法解析：(.*)", lambda m: f"Unable to parse manifest.json: {m.group(1)}"),
        (r"index\.tsv SHA256 与 manifest\.json 不一致。", lambda m: "index.tsv SHA256 does not match manifest.json."),
        (r"打包前文件缺失：(.*)", lambda m: f"File is missing before packaging: {m.group(1)}"),
        (r"打包前文件大小不符：(.*)", lambda m: f"File size mismatch before packaging: {m.group(1)}"),
        (r"ZIP 缺少必要文件：(.*)", lambda m: f"ZIP is missing required files: {m.group(1)}"),
        (r"ZIP 缺少索引文件：(.*)", lambda m: f"ZIP is missing indexed file: {m.group(1)}"),
        (r"RomFS 校验通过：(.*)", lambda m: f"RomFS verification passed: {m.group(1)}"),
        (r"错误：", lambda m: "Error:"),
    )
    for pattern, render in patterns:
        match = re.fullmatch(pattern, message, flags=re.DOTALL)
        if match:
            return render(match)

    exact = {
        "========== 开始 ==========": "========== START ==========",
        "========== 全部完成 ==========": "========== COMPLETED ==========",
        "========== 已取消 ==========": "========== CANCELLED ==========",
        "提示：S2Arm v0.3.3 已在 pack/game.img 中完成资源拼接；本工具只校验并打包，不会再次拼接。":
            "Note: S2Arm v0.3.3 already assembles resources into pack/game.img. This tool only verifies and packages it.",
        "收到取消请求，将在当前处理步骤可中断时停止。": "Cancellation requested. The operation will stop at the next safe checkpoint.",
        "已请求取消，将在当前处理步骤可中断时停止。": "Cancellation requested. The operation will stop at the next safe checkpoint.",
        "用户已取消打包。": "Packaging was cancelled by the user.",
        "无法读取游戏信息": "Unable to read game information",
        "未找到资源包": "Resource pack not found",
        "目录不完整": "Missing directories",
        "请选择 S2Arm 项目目录、游戏名目录和 ZIP 输出目录。": "Select the S2Arm installation, game, and ZIP output directories.",
        "资源包目录不存在": "Resource pack directory not found",
        "游戏信息错误": "Invalid game information",
        "覆盖现有 ZIP？": "Overwrite existing ZIP?",
        "是否覆盖已有文件？": "Overwrite the existing file?",
        "ZIP 检查": "ZIP check",
        "检查 ZIP 完整性……": "Checking ZIP integrity...",
        "生成 ZIP（不压缩，保留 ZIP64）": "Creating ZIP (stored, ZIP64 enabled)",
        "校验 S2Arm 已生成的 game.img": "Verifying the game.img generated by S2Arm",
        "RomFS 校验通过": "RomFS verification passed",
        "打包前检查": "Pre-packaging check",
        "打包前文件缺失": "File missing before packaging",
        "打包前文件大小不符": "File size mismatch before packaging",
        "ZIP 已写入": "ZIP entries written",
        "ZIP 完整性校验": "ZIP integrity verification",
        "ZIP 缺少必要文件": "ZIP is missing required files",
        "ZIP 缺少索引文件": "ZIP is missing an indexed file",
        "最终 ZIP 不应包含 旧版 romfs.files 分片目录。": "The ZIP packages the v3 game.img directly; legacy romfs.files fragments are not part of this format.",
        "不是 UTF-8": "is not UTF-8",
        "有重复路径": "contains a duplicate path",
        "SHA256 不一致": "SHA256 does not match",
        "SHA256 不正确": "SHA256 is incorrect",
        "index.tsv SHA256 与 manifest.json 不一致": "index.tsv SHA256 does not match manifest.json.",
        "manifest.json 无法解析": "Unable to parse manifest.json",
        "imgmap 格式错误": "Invalid imgmap format",
        "imgmap 文件数或长度不匹配": "imgmap file count or length mismatch",
        "没有 romfs.img，无法拼接 RomFS": "No romfs.img found in index.tsv; cannot assemble RomFS.",
        "只支持 manifest version 2": "Only manifest version 2 is supported",
        "缺少 index.tsv 或 manifest.json": "Missing index.tsv or manifest.json",
        "缺少 parse_index() 或 materialize()": "Missing parse_index() or materialize()",
    }
    if message in exact:
        return exact[message]

    match = re.fullmatch(r"调用 S2Arm materialize\(\)：(.*)", message)
    if match:
        return f"Calling S2Arm materialize(): {match.group(1)}"
    match = re.fullmatch(r"(.*)缺少 romfs\.s2aidx 或 romfs\.imgmap。", message)
    if match:
        prefix = "Main program " if match.group(1) == "" else match.group(1)
        return f"{prefix}is missing romfs.s2aidx or romfs.imgmap."
    match = re.fullmatch(r"(.*)imgmap 镜像长度与 index\.tsv 不一致。", message)
    if match:
        prefix = "Main program " if match.group(1) == "" else match.group(1)
        return f"{prefix}imgmap image size does not match index.tsv."

    # Structured progress lines produced by this script.
    match = re.fullmatch(r"(.*)RomFS：索引 (\d+) 项，需拼接 (\d+) 个文件", message)
    if match:
        prefix = match.group(1)
        prefix = "Main program " if prefix == "主程序" else prefix
        return f"{prefix}RomFS: {match.group(2)} indexed entries; {match.group(3)} files to assemble"
    match = re.fullmatch(r"已准备索引文件：(\d+)/(\d+)", message)
    if match:
        return f"Prepared indexed files: {match.group(1)}/{match.group(2)}"
    match = re.fullmatch(r"打包前检查：(\d+)/(\d+)", message)
    if match:
        return f"Pre-packaging check: {match.group(1)}/{match.group(2)}"
    match = re.fullmatch(r"ZIP 已写入 (\d+) 个文件", message)
    if match:
        return f"ZIP entries written: {match.group(1)} files"
    match = re.fullmatch(r"ZIP 检查：(\d+)/(\d+)", message)
    if match:
        return f"ZIP check: {match.group(1)}/{match.group(2)}"
    match = re.fullmatch(r"ZIP 完整性校验：(\d+)/(\d+)", message)
    if match:
        return f"ZIP integrity verification: {match.group(1)}/{match.group(2)}"
    match = re.fullmatch(r"生成 ZIP（不压缩，保留 ZIP64）：(.*)", message)
    if match:
        return f"Creating ZIP (stored, ZIP64 enabled): {match.group(1)}"
    match = re.fullmatch(r"ZIP 文件名：(.*)", message)
    if match:
        return f"ZIP filename: {match.group(1)}"
    match = re.fullmatch(r"ZIP 输出路径：(.*)", message)
    if match:
        return f"ZIP output path: {match.group(1)}"
    match = re.fullmatch(r"完成：(\d+) 个文件；ZIP 大小 (.*)", message)
    if match:
        return f"Completed: {match.group(1)} files; ZIP size {match.group(2)}"

    match = re.fullmatch(r"manifest version：([^；]+)；索引文件：(\d+)", message)
    if match:
        return f"Manifest version: {match.group(1)}; indexed files: {match.group(2)}"
    match = re.fullmatch(r"资源包已生成：\s*(.*)", message, flags=re.DOTALL)
    if match:
        return f"Resource pack created:\n{match.group(1)}"

    # Native S2Arm logs: translate only recognized, stable phrases. Do not
    # perform broad substring replacement that can corrupt paths or values.
    native_exact = {
        "正在拼接 RomFS": "Assembling RomFS",
        "RomFS 拼接完成": "RomFS assembly completed",
        "开始拼接 RomFS": "Starting RomFS assembly",
        "校验通过": "Verification passed",
        "正在校验": "Verifying",
        "正在处理": "Processing",
        "已完成": "Completed",
    }
    return native_exact.get(message, message)


TITLE_RE = re.compile(r"^[0-9A-Fa-f]{16}$")
CHUNK = 4 * 1024 * 1024
# Keep the config beside the script when possible (easy to locate), and
# fall back to the per-user application-data directory when that location is read-only.
CONFIG_PATH = Path(__file__).resolve().with_name("resource_packager_gui.config.json")
if os.environ.get("LOCALAPPDATA"):
    FALLBACK_CONFIG_PATH = Path(os.environ["LOCALAPPDATA"]) / "S2Arm" / "resource_packager_gui.config.json"
else:
    FALLBACK_CONFIG_PATH = Path.home() / ".config" / "S2Arm" / "resource_packager_gui.config.json"


class PackError(Exception):
    pass


def read_title_id(game_dir: Path) -> str:
    path = game_dir / "game.json"
    if not path.is_file():
        raise PackError(f"游戏目录缺少 game.json：{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise PackError(f"game.json 无法解析：{exc}")
    value = data.get("id") if isinstance(data, dict) else None
    if not isinstance(value, str) or not TITLE_RE.fullmatch(value.strip()):
        raise PackError("game.json 顶层 id 字段不是有效的 16 位十六进制 Title ID。")
    return value.strip().upper()


def safe_rel(value: str) -> str:
    value = value.replace("\\", "/")
    p = PurePosixPath(value)
    if not value or p.is_absolute() or any(x in ("", ".", "..") for x in p.parts):
        raise PackError(f"资源索引包含不安全路径：{value!r}")
    if ":" in p.parts[0]:
        raise PackError(f"资源索引包含盘符路径：{value!r}")
    return p.as_posix()


def sha256_file(path: Path, cancel_event=None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            check_cancel(cancel_event)
            block = f.read(CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def read_index(pack: Path):
    index_path, manifest_path = pack / "index.tsv", pack / "manifest.json"
    if not index_path.is_file() or not manifest_path.is_file():
        raise PackError("image/ios/pack 缺少 index.tsv 或 manifest.json。")
    raw = index_path.read_bytes()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise PackError(f"manifest.json 无法解析：{exc}")
    if manifest.get("version") != 3 or manifest.get("format") != "img" or manifest.get("imgFile") != "game.img":
        raise PackError(
            f"当前资源包不是 S2Arm v0.3.0+ 单一 IMG 格式（要求 manifest version=3、format=img、imgFile=game.img；"
            f"实际 version={manifest.get('version')!r}、format={manifest.get('format')!r}、imgFile={manifest.get('imgFile')!r}）。"
        )
    if hashlib.sha256(raw).hexdigest() != manifest.get("index_sha256"):
        raise PackError("index.tsv SHA256 与 manifest.json 不一致。")
    rows, seen = [], set()
    try:
        for line_no, line in enumerate(raw.decode("utf-8").splitlines(), 1):
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) != 3:
                raise PackError(f"index.tsv 第 {line_no} 行不是三列格式。")
            rel, size_text, digest = safe_rel(cols[0]), cols[1], cols[2].strip().lower()
            try:
                size = int(size_text)
            except ValueError:
                raise PackError(f"index.tsv 第 {line_no} 行文件大小无效。")
            if size < 0 or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise PackError(f"index.tsv 第 {line_no} 行大小或 SHA256 无效：{rel}")
            if rel in seen:
                raise PackError(f"index.tsv 有重复路径：{rel}")
            seen.add(rel)
            rows.append((rel, size, digest))
    except UnicodeDecodeError as exc:
        raise PackError(f"index.tsv 不是 UTF-8：{exc}")
    if not any(rel == "game.img" for rel, _, _ in rows):
        raise PackError("v3 资源包的 index.tsv 中没有 game.img。")
    return rows, manifest


def verify_source_pack(source: Path, rows, title_id: str, log, cancel_event=None):
    """v3 单一 IMG：S2Arm 出包阶段已把 RomFS 与其余原始资源拼进 game.img。
    此处只校验交付件，不再调用 romfs_image.materialize，也不复制/重建镜像。"""
    img_row = next((r for r in rows if r[0] == "game.img"), None)
    if img_row is None:
        raise PackError("v3 资源包缺少 game.img。")
    _rel, expected_size, pack_id = img_row
    image = source / "game.img"
    if not image.is_file():
        raise PackError("资源包缺少索引文件：game.img")
    if image.stat().st_size != expected_size:
        raise PackError("文件大小与 index.tsv 不符：game.img")
    with image.open("rb") as f:
        header = f.read(136)
    if len(header) != 136:
        raise PackError("game.img 文件头不完整。")
    try:
        magic, fmt, _reserved, gid, pid, _ro, _rl, _to, _tl, total = struct.unpack("<8sII16s64s5Q", header)
        image_gid = gid.decode("ascii")
        image_pack_id = pid.rstrip(b"\0").decode("ascii")
    except (struct.error, UnicodeDecodeError) as exc:
        raise PackError(f"game.img 文件头无法解析：{exc}")
    if magic != b"S2AIMG01" or fmt != 1:
        raise PackError("game.img 魔数或格式号不正确。")
    if image_gid.upper() != title_id.upper():
        raise PackError(f"game.img 游戏号不匹配：文件头 {image_gid}，game.json {title_id}")
    if image_pack_id != pack_id:
        raise PackError("game.img 资源包号与 index.tsv 不一致。")
    if total != expected_size or total != image.stat().st_size:
        raise PackError("game.img 文件头记录的总长度不正确。")
    log(f"单一 IMG 已由 S2Arm 生成：{expected_size / (1024 ** 3):.2f} GiB；不再执行 RomFS 拼接")

    for i, (rel, size, digest) in enumerate(rows, 1):
        check_cancel(cancel_event)
        path = source.joinpath(*PurePosixPath(rel).parts)
        if not path.is_file():
            raise PackError(f"资源包缺少索引文件：{rel}")
        if path.stat().st_size != size:
            raise PackError(f"文件大小与 index.tsv 不符：{rel}")
        # game.img 第三列是 pack_id（由 IMG 头同步校验），不是文件 SHA256。
        if rel != "game.img":
            actual = sha256_file(path, cancel_event)
            if actual != digest:
                raise PackError(f"文件 SHA256 与 index.tsv 不符：{rel}")
        if i % 100 == 0:
            log(f"打包前检查：{i}/{len(rows)}")
    log("资源包文件校验通过")

class CancelledPackError(Exception):
    pass


def check_cancel(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledPackError("用户已取消打包。")


def build_zip(game_dir: Path, install_root: Path, output_dir: Path, log, cancel_event=None):
    check_cancel(cancel_event)
    title_id = read_title_id(game_dir)
    source = game_dir / "image" / "ios" / "pack"
    if not source.is_dir():
        raise PackError(f"找不到固定资源包目录：{source}")
    rows, manifest = read_index(source)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{game_dir.name}_pack.zip"

    with tempfile.TemporaryDirectory(prefix="s2arm_packager_", dir=str(output_dir)) as temp:
        temp_zip = Path(temp) / output.name
        log(f"游戏目录：{game_dir}")
        log(f"Title ID：{title_id}（来自 game.json）")
        log(f"资源包目录：{source}")
        log(f"manifest version：{manifest.get('version')}；格式：{manifest.get('format')}；索引文件：{len(rows)}")
        verify_source_pack(source, rows, title_id, log, cancel_event)

        root = f"{title_id}/资源包"
        count = 0
        log(f"生成 ZIP（不压缩，保留 ZIP64）：{output}")
        with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
            zf.writestr(f"{title_id}/", b"")
            zf.writestr(root + "/", b"")
            for rel, _size, _digest in rows:
                check_cancel(cancel_event)
                path = source.joinpath(*PurePosixPath(rel).parts)
                arcname = f"{root}/{rel}"
                with path.open("rb") as src, zf.open(arcname, "w", force_zip64=True) as dst:
                    while True:
                        check_cancel(cancel_event)
                        block = src.read(CHUNK)
                        if not block:
                            break
                        dst.write(block)
                count += 1
                if count % 100 == 0:
                    log(f"ZIP 已写入 {count} 个文件")

            # 索引和清单是资源包交付必需文件，不属于 index.tsv 自身的索引项。
            for name in ("index.tsv", "manifest.json"):
                check_cancel(cancel_event)
                with (source / name).open("rb") as src, zf.open(f"{root}/{name}", "w") as dst:
                    shutil.copyfileobj(src, dst, length=CHUNK)

        check_cancel(cancel_event)
        log("检查 ZIP 完整性……")
        with zipfile.ZipFile(temp_zip, "r") as zf:
            names = zf.namelist()
            name_set = set(names)
            required = {f"{root}/index.tsv", f"{root}/manifest.json", f"{root}/game.img"}
            missing = required - name_set
            if missing:
                raise PackError("ZIP 缺少必要文件：" + ", ".join(sorted(missing)))
            for rel, _, _ in rows:
                check_cancel(cancel_event)
                if f"{root}/{rel}" not in name_set:
                    raise PackError(f"ZIP 缺少索引文件：{rel}")
            for i, name in enumerate(names, 1):
                check_cancel(cancel_event)
                if name.endswith("/"):
                    continue
                with zf.open(name, "r") as member:
                    while member.read(CHUNK):
                        check_cancel(cancel_event)
                if i % 100 == 0:
                    log(f"ZIP 完整性校验：{i}/{len(names)}")

        check_cancel(cancel_event)
        os.replace(temp_zip, output)
        log(f"完成：{count + 2} 个文件；ZIP 大小 {output.stat().st_size / (1024 ** 3):.2f} GiB")
    return output

class App:
    def __init__(self, root):
        self.root = root
        self.lang = "en"
        self.root.title(APP_TITLE)
        self.root.geometry("900x680")
        self.root.minsize(760, 580)
        self.events = queue.Queue()
        self.running = False
        self.install_var = tk.StringVar(value=r"E:\ProjectIOS\S2Arm")
        self.game_var = tk.StringVar()
        self._load_config()
        self.output_dir_var = tk.StringVar()
        self.title_var = tk.StringVar()
        # Restore the last selected built-game directory and its derived fields.
        saved_game_dir = Path(self.game_var.get().strip()) if self.game_var.get().strip() else None
        if saved_game_dir and saved_game_dir.is_dir():
            self.output_dir_var.set(str(saved_game_dir))
            try:
                self.title_var.set(read_title_id(saved_game_dir))
            except PackError:
                pass
        self._build()
        # Persist initial defaults too, including first-launch English.
        self._save_config()
        self.root.after(150, self._poll)

    def _t(self, value):
        return tr(value, self.lang)

    def _localize_log(self, message):
        return localize_log(str(message), self.lang)

    def _switch_language(self, _event=None):
        self.lang = "en" if self.lang_combo.get() == "English" else "zh"
        self._save_config()
        for child in self.root.winfo_children():
            child.destroy()
        self._build()

    def _build(self):
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)
        top = ttk.Frame(outer)
        top.pack(fill="x")
        ttk.Label(top, text=APP_TITLE, font=("Microsoft YaHei UI", 18, "bold")).pack(side="left", anchor="w")
        self.lang_combo = ttk.Combobox(top, state="readonly", width=16, values=("简体中文", "English"))
        self.lang_combo.set("简体中文" if self.lang == "zh" else "English")
        self.lang_combo.pack(side="right")
        self.lang_combo.bind("<<ComboboxSelected>>", self._switch_language)
        ttk.Label(
            outer,
            text=self._t("读取 game.json 的 Title ID，校验已生成的 game.img，并生成可直接解压到 iPhone games 文件夹的 ZIP"),
            foreground="#666",
        ).pack(anchor="w", pady=(2, 14))

        form = ttk.Frame(outer)
        form.pack(fill="x")
        self._path_row(form, 0, "S2Arm 项目安装目录", self.install_var, self._browse_install, persist=True)
        self._path_row(form, 1, "已构建游戏目录（游戏名这一层）", self.game_var, self._browse_game)
        self._path_row(form, 2, "ZIP 输出目录（默认游戏目录）", self.output_dir_var, self._browse_output)
        ttk.Label(form, text=self._t("自动读取的 Title ID")).grid(row=3, column=0, sticky="w", pady=7)
        ttk.Entry(form, textvariable=self.title_var, state="readonly").grid(
            row=3, column=1, sticky="ew", padx=8, pady=7
        )
        ttk.Label(form, text=self._t("来源：所选游戏目录/game.json → id"), foreground="#777").grid(
            row=3, column=2, sticky="w", pady=7
        )
        form.columnconfigure(1, weight=1)

        ttk.Separator(outer).pack(fill="x", pady=12)
        ttk.Label(outer, text=self._t("执行日志"), font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        self.log_text = tk.Text(outer, height=19, wrap="word", font=("Consolas", 9), state="disabled")
        self.log_text.pack(fill="both", expand=True, pady=(6, 10))
        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.pack(fill="x")
        bottom = ttk.Frame(outer)
        bottom.pack(fill="x", pady=(10, 0))
        self.status = tk.StringVar(value=self._t("等待选择目录"))
        ttk.Label(bottom, textvariable=self.status).pack(side="left")
        self.cancel_button = ttk.Button(bottom, text=self._t("取消打包"), command=self._cancel, state="disabled")
        self.cancel_button.pack(side="right", padx=(8, 0))
        self.run_button = ttk.Button(bottom, text=self._t("开始拼接并生成 ZIP"), command=self._start)
        self.run_button.pack(side="right")

    def _path_row(self, parent, row, label, variable, callback, persist=False):
        ttk.Label(parent, text=self._t(label)).grid(row=row, column=0, sticky="w", pady=7)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", padx=8, pady=7)
        if persist:
            entry.bind("<FocusOut>", lambda _event: self._save_config())
        ttk.Button(parent, text=self._t("浏览…"), command=callback).grid(row=row, column=2, pady=7)

    def _load_config(self):
        for config_path in (CONFIG_PATH, FALLBACK_CONFIG_PATH):
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.install_var.set(str(data.get("install_root") or self.install_var.get()))
                    self.game_var.set(str(data.get("game_dir") or ""))
                    saved_lang = data.get("language")
                    if saved_lang in ("zh", "en"):
                        self.lang = saved_lang
                    return
            except (OSError, json.JSONDecodeError, TypeError):
                continue

    def _save_config(self):
        data = {
            "install_root": self.install_var.get().strip(),
            "game_dir": self.game_var.get().strip(),
            "language": self.lang,
        }
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        errors = []
        for config_path in (CONFIG_PATH, FALLBACK_CONFIG_PATH):
            temp_path = config_path.with_suffix(".tmp")
            try:
                config_path.parent.mkdir(parents=True, exist_ok=True)
                temp_path.write_text(payload, encoding="utf-8")
                os.replace(temp_path, config_path)
                return
            except OSError as exc:
                errors.append(f"{config_path}: {exc}")
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
        self._append_log(self._localize_log("无法保存路径配置：" + "；".join(errors)))

    def _browse_install(self):
        current = self.install_var.get().strip()
        path = filedialog.askdirectory(title=self._t("选择 S2Arm 项目安装目录（例如 E:\\ProjectIOS\\S2Arm）"),
            initialdir=current if current and Path(current).is_dir() else None)
        if path:
            self.install_var.set(path)
            self._save_config()

    def _browse_game(self):
        current = self.game_var.get().strip()
        path = filedialog.askdirectory(title=self._t("选择游戏名目录（例如 E:\\nisshell\\S2\\games\\the 1st）"),
            initialdir=current if current and Path(current).is_dir() else None)
        if not path:
            return
        game_dir = Path(path)
        self.game_var.set(str(game_dir))
        self._save_config()
        try:
            title_id = read_title_id(game_dir)
        except PackError as exc:
            self.title_var.set("")
            self.output_dir_var.set("")
            messagebox.showerror(self._t("无法读取游戏信息"), self._localize_log(str(exc)))
            return
        self.title_var.set(title_id)
        self.output_dir_var.set(str(game_dir))
        pack_dir = game_dir / "image" / "ios" / "pack"
        self._log(self._localize_log(f"Title ID：{title_id}（来自 game.json）"))
        if pack_dir.is_dir():
            self._log(self._localize_log(f"已定位资源包目录：{pack_dir}"))
        else:
            self._log(self._localize_log(f"未找到预期资源包目录：{pack_dir}"))
            messagebox.showwarning(self._t("未找到资源包"), self._localize_log(f"缺少固定目录：\n{pack_dir}"))

    def _browse_output(self):
        current = self.output_dir_var.get().strip()
        path = filedialog.askdirectory(
            title=self._t("选择 ZIP 输出目录（默认是游戏目录）"),
            initialdir=current if current and Path(current).is_dir() else None,
        )
        if path:
            self.output_dir_var.set(path)

    def _log(self, message):
        self.events.put(("log", str(message)))

    def _start(self):
        if self.running:
            return
        install_root = Path(self.install_var.get().strip())
        game_text = self.game_var.get().strip()
        output_text = self.output_dir_var.get().strip()
        if not install_root.is_dir() or not game_text or not Path(game_text).is_dir() or not output_text:
            messagebox.showwarning(self._t("目录不完整"), self._t("请选择 S2Arm 项目目录、游戏名目录和 ZIP 输出目录。"))
            return
        game_dir = Path(game_text)
        output_dir = Path(output_text)
        if not (game_dir / "image" / "ios" / "pack").is_dir():
            messagebox.showerror(self._t("资源包目录不存在"), self._localize_log(f"找不到：{game_dir / 'image' / 'ios' / 'pack'}"))
            return
        try:
            title_id = read_title_id(game_dir)
        except PackError as exc:
            messagebox.showerror(self._t("游戏信息错误"), self._localize_log(str(exc)))
            return
        self.title_var.set(title_id)
        self._save_config()
        output = output_dir / f"{game_dir.name}_pack.zip"
        if output.exists() and not messagebox.askyesno(self._t("覆盖现有 ZIP？"), f"是否覆盖已有文件？\n{output}"):
            return

        self.running = True
        self.cancel_event = threading.Event()
        self.run_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress.start(12)
        self.status.set(self._t("正在处理……"))
        self._append_log(self._localize_log("========== 开始 =========="))
        self._append_log(self._localize_log(f"ZIP 文件名：{output.name}"))
        self._append_log(self._localize_log(f"ZIP 输出路径：{output}"))
        self._append_log(self._localize_log(f"Title ID：{title_id}"))

        def worker():
            try:
                result = build_zip(game_dir, install_root, output_dir, lambda msg: self._log(self._localize_log(msg)), self.cancel_event)
                self.events.put(("done", str(result)))
            except CancelledPackError as exc:
                self.events.put(("cancelled", self._localize_log(str(exc))))
            except Exception as exc:
                self.events.put(("error", self._localize_log(str(exc))))

        threading.Thread(target=worker, daemon=True).start()

    def _cancel(self):
        if self.running and self.cancel_event:
            self._save_config()
            self.cancel_event.set()
            self.cancel_button.configure(state="disabled")
            self.status.set(self._t("正在取消……"))
            self._append_log(self._localize_log("已请求取消，将在当前处理步骤可中断时停止。"))

    def _append_log(self, message):
        # Normalize line endings before rendering. Render every embedded line
        # separately so multiline messages cannot merge with adjacent log entries.
        message = self._localize_log(str(message))
        message = message.replace("\r\n", "\n").replace("\r", "\n")
        self.log_text.configure(state="normal")
        stamp = time.strftime("%H:%M:%S")
        for line in message.split("\n"):
            self.log_text.insert("end", f"[{stamp}] {line}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self._append_log(value)
                elif kind in ("done", "error", "cancelled"):
                    self.running = False
                    self.progress.stop()
                    self.run_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    if kind == "done":
                        self.status.set(self._t("完成"))
                        self._append_log(self._localize_log("========== 全部完成 =========="))
                        messagebox.showinfo(self._t("打包完成"), self._localize_log(f"资源包已生成：\n{value}"))
                    elif kind == "cancelled":
                        self.status.set(self._t("已取消"))
                        self._append_log(self._localize_log("========== 已取消 =========="))
                        messagebox.showinfo(self._t("已取消"), value)
                    else:
                        self.status.set(self._t("失败"))
                        self._append_log(self._localize_log("错误：") + value)
                        messagebox.showerror(self._t("打包失败"), value)
        except queue.Empty:
            pass
        self.root.after(150, self._poll)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
