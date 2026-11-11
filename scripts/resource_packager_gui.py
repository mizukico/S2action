#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S2Arm Resource Packager GUI.

Select the S2Arm installation root and a built game directory. The tool reads
Title ID from game.json, finds image/ios/pack, materializes RomFS with the
installed S2Arm Engine/pack/romfs_image.py, then writes <GameName>_pack.zip.
The ZIP root is <TitleID>/ so it can be extracted directly into Documents/games.
Python 3.10+; standard library only.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import queue
import re
import shutil
import struct
import sys
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
        "读取 game.json 的 Title ID，自动拼接 RomFS，并生成可直接解压到 iPhone games 文件夹的 ZIP": "Read the Title ID from game.json, materialize RomFS, and create a ZIP ready for the iPhone games folder.",
        "S2Arm 项目安装目录": "S2Arm installation directory",
        "已构建游戏目录（游戏名这一层）": "Built game directory (game-name folder)",
        "ZIP 输出目录（默认游戏目录）": "ZIP output directory (defaults to game folder)",
        "自动读取的 Title ID": "Detected Title ID",
        "来源：所选游戏目录/game.json → id": "Source: selected game folder/game.json → id",
        "执行日志": "Execution log", "等待选择目录": "Select the directories to begin",
        "开始拼接并生成 ZIP": "Materialize RomFS and create ZIP", "浏览…": "Browse...",
        "选择 S2Arm 项目安装目录（例如 E:\\\\ProjectIOS\\\\S2Arm）": "Select the S2Arm installation directory",
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


LOG_TRANSLATIONS = {
    "游戏目录": "Game directory",
    "Title ID": "Title ID",
    "来自 game.json": "from game.json",
    "资源包目录": "Resource pack directory",
    "manifest version": "Manifest version",
    "索引文件": "indexed files",
    "已准备索引文件": "Prepared indexed files",
    "缺少 romfs.s2aidx 或 romfs.imgmap": "Missing romfs.s2aidx or romfs.imgmap",
    "imgmap 格式错误": "Invalid imgmap format",
    "imgmap 文件数或长度不匹配": "imgmap file count or length mismatch",
    "imgmap 镜像长度与 index.tsv 不一致": "imgmap image size does not match index.tsv",
    "主程序": "Main program",
    "RomFS：索引": "RomFS: indexed ",
    "项，需拼接": " entries; ",
    "个文件": " files to assemble",
    "调用 S2Arm materialize()": "Calling S2Arm materialize()",
    "提示：正在执行 S2Arm 原生 RomFS 拼接；此阶段无法强制中断。点击取消后，将在原生函数返回或下一次进度回调时停止。": "Note: S2Arm native RomFS assembly is running and cannot be force-stopped. If you click Cancel, cancellation will take effect when the native function returns or the next progress callback is reached.",
    "RomFS 校验通过": "RomFS verification passed",
    "找不到固定资源包目录": "Resource pack directory not found",
    "打包前检查": "Pre-packaging check",
    "打包前文件缺失": "File missing before packaging",
    "打包前文件大小不符": "File size mismatch before packaging",
    "生成 ZIP（不压缩，保留 ZIP64）": "Creating ZIP (stored, ZIP64 enabled)",
    "ZIP 已写入": "ZIP entries written",
    "检查 ZIP 完整性": "Checking ZIP integrity",
    "ZIP 检查": "ZIP check",
    "ZIP 完整性校验": "ZIP integrity verification",
    "ZIP 缺少必要文件": "ZIP is missing required files",
    "ZIP 缺少索引文件": "ZIP is missing indexed file",
    "最终 ZIP 不应包含 romfs.files 分片目录": "Final ZIP must not contain romfs.files fragments",
    "完成": "Completed",
    "个文件；ZIP 大小": " files; ZIP size",
    "已定位资源包目录": "Resource pack directory found",
    "未找到预期资源包目录": "Expected resource pack directory not found",
    "收到取消请求，将在当前处理步骤可中断时停止。": "Cancellation requested. The operation will stop at the next safe checkpoint.",
    "已请求取消，将在当前处理步骤可中断时停止。": "Cancellation requested. The operation will stop at the next safe checkpoint.",
    "========== 开始 ==========": "========== START ==========",
    "========== 全部完成 ==========": "========== COMPLETED ==========",
    "========== 已取消 ==========": "========== CANCELLED ==========",
    "ZIP 文件名": "ZIP filename",
    "ZIP 输出路径": "ZIP output path",
    "错误": "Error",
    "第 ": "line ",
    " 行": "",
    "不是三列格式": "does not contain exactly three columns",
    "文件大小无效": "has an invalid file size",
    "大小或 SHA256 无效": "has an invalid size or SHA256",
    "SHA256 不正确": "SHA256 is incorrect",
    "SHA256 不一致": "SHA256 does not match",
    "镜像长度": "image size",
    "索引": "index",
    "需拼接": "to assemble",
    "校验通过": "verification passed",
    "检查": "Checking",
    "正在": "In progress: ",
    "无法保存路径配置": "Unable to save path configuration",
    "资源包已生成": "Resource pack created",
    "无法保存路径配置": "Unable to save configuration",
    "游戏目录缺少 game.json": "Game folder is missing game.json",
    "game.json 无法解析": "Unable to parse game.json",
    "game.json 顶层 id 字段不是有效的 16 位十六进制 Title ID": "The top-level id field in game.json is not a valid 16-digit hexadecimal Title ID",
    "资源索引包含不安全路径": "Resource index contains an unsafe path",
    "资源索引包含盘符路径": "Resource index contains a drive-letter path",
    "缺少 index.tsv 或 manifest.json": "Missing index.tsv or manifest.json",
    "manifest.json 无法解析": "Unable to parse manifest.json",
    "只支持 manifest version 2，当前为": "Only manifest version 2 is supported; current version:",
    "index.tsv SHA256 与 manifest.json 不一致": "index.tsv SHA256 does not match manifest.json",
    "不是三列格式": "does not contain exactly three columns",
    "文件大小无效": "has an invalid file size",
    "大小或 SHA256 无效": "has an invalid size or SHA256",
    "有重复路径": "contains a duplicate path",
    "不是 UTF-8": "is not UTF-8",
    "找不到 S2Arm 原生脚本或依赖": "S2Arm native scripts or dependencies not found",
    "请选择 S2Arm 项目安装目录": "Select the S2Arm installation directory",
    "其中应有": "It must contain",
    "无法加载原生脚本": "Unable to load native script",
    "缺少 parse_index() 或 materialize()": "Missing parse_index() or materialize()",
    "没有 romfs.img，无法拼接 RomFS": "No romfs.img found in index.tsv; cannot assemble RomFS",
    "资源包缺少索引文件": "Resource pack is missing indexed file",
    "文件大小与 index.tsv 不符": "File size does not match index.tsv",
    "RomFS 分片缺失": "RomFS fragment is missing",
    "拼接后的镜像大小不正确": "Assembled image has an incorrect size",
    "拼接后的镜像 SHA256 不正确": "Assembled image SHA256 is incorrect",
    "用户已取消打包": "Packaging was cancelled by the user",
    "找不到": "Not found",
    "缺少固定目录": "Required directory is missing",
    "缺少": "Missing",
    "无法读取游戏信息": "Unable to read game information",
    "无法读取游戏信息": "Unable to read game information",
}


def localize_log(message: str, lang: str) -> str:
    if lang != "en":
        return message

    # Dynamic lines emitted when the user selects a game directory.
    match = re.fullmatch(r"Title ID：([0-9A-Fa-f]{16})（来自 game\\.json）", message)
    if match:
        return f"Title ID: {match.group(1)} (from game.json)"
    match = re.fullmatch(r"已定位资源包目录：(.*)", message)
    if match:
        return f"Resource pack directory found: {match.group(1)}"
    match = re.fullmatch(r"未找到预期资源包目录：(.*)", message)
    if match:
        return f"Expected resource pack directory not found: {match.group(1)}"

    for source, target in sorted(LOG_TRANSLATIONS.items(), key=lambda item: len(item[0]), reverse=True):
        message = message.replace(source, target)
    return message

TITLE_RE = re.compile(r"^[0-9A-Fa-f]{16}$")
CHUNK = 4 * 1024 * 1024
CONFIG_PATH = Path(__file__).resolve().with_name("resource_packager_gui.config.json")


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
    if manifest.get("version") != 2:
        raise PackError(f"只支持 manifest version 2，当前为 {manifest.get('version')!r}")
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
    return rows, manifest


def load_native(install_root: Path):
    engine = install_root / "Engine"
    script = engine / "pack" / "romfs_image.py"
    tools = engine / "tools"
    if not script.is_file() or not (tools / "sha256_fast.py").is_file():
        raise PackError(
            "找不到 S2Arm 原生脚本或依赖。请选择 S2Arm 项目安装目录，"
            "其中应有 Engine/pack/romfs_image.py 和 Engine/tools/sha256_fast.py。"
        )
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    spec = importlib.util.spec_from_file_location("s2arm_romfs_image", script)
    if spec is None or spec.loader is None:
        raise PackError(f"无法加载原生脚本：{script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "parse_index", None)) or not callable(
        getattr(module, "materialize", None)
    ):
        raise PackError("romfs_image.py 缺少 parse_index() 或 materialize()。")
    return module


def link_or_copy(src: Path, dst: Path, cancel_event=None):
    check_cancel(cancel_event)
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        with src.open("rb") as source, dst.open("wb") as target:
            while True:
                check_cancel(cancel_event)
                block = source.read(CHUNK)
                if not block:
                    break
                target.write(block)
        shutil.copystat(src, dst)


def read_imgmap(path: Path, expected_count: int):
    data = path.read_bytes()
    if len(data) < 20 or data[:8] != b"S2ARIM01":
        raise PackError(f"imgmap 格式错误：{path}")
    total, count = struct.unpack_from("<qi", data, 8)
    if count != expected_count or len(data) != 20 + count * 8:
        raise PackError(f"imgmap 文件数或长度不匹配：{path}")
    offsets = struct.unpack_from(f"<{count}q", data, 20)
    return total, offsets


def prepare_and_materialize(source: Path, stage: Path, rows, native, log, cancel_event=None):
    image_rows = {p: (size, digest) for p, size, digest in rows if p.endswith("romfs.img")}
    if not image_rows:
        raise PackError("index.tsv 中没有 romfs.img，无法拼接 RomFS。")

    shutil.copy2(source / "index.tsv", stage / "index.tsv")
    shutil.copy2(source / "manifest.json", stage / "manifest.json")

    # Copy/link all indexed files except romfs.img, which is generated below.
    for i, (rel, size, _digest) in enumerate(rows, 1):
        check_cancel(cancel_event)
        if rel.endswith("romfs.img"):
            continue
        src = source.joinpath(*PurePosixPath(rel).parts)
        if not src.is_file():
            raise PackError(f"资源包缺少索引文件：{rel}")
        if src.stat().st_size != size:
            raise PackError(f"文件大小与 index.tsv 不符：{rel}")
        link_or_copy(src, stage.joinpath(*PurePosixPath(rel).parts), cancel_event)
        if i % 500 == 0:
            log(f"已准备索引文件：{i}/{len(rows)}")

    # Upstream parse_index() returns (total_size, [(offset, size, relative_path), ...]).
    prefixes = sorted({p[:-len("romfs.img")] for p in image_rows})
    for prefix in prefixes:
        idx = source.joinpath(*PurePosixPath(prefix + "romfs.s2aidx").parts)
        imgmap = source.joinpath(*PurePosixPath(prefix + "romfs.imgmap").parts)
        if not idx.is_file() or not imgmap.is_file():
            raise PackError(f"{prefix}缺少 romfs.s2aidx 或 romfs.imgmap。")
        _index_total, files = native.parse_index(str(idx))
        map_total, offsets = read_imgmap(imgmap, len(files))
        expected_size, _ = image_rows[prefix + "romfs.img"]
        if map_total != expected_size:
            raise PackError(f"{prefix}imgmap 镜像长度与 index.tsv 不一致。")

        needed = [entry[2] for entry, offset in zip(files, offsets) if offset >= 0]
        log(f"{prefix or '主程序'}RomFS：索引 {len(files)} 项，需拼接 {len(needed)} 个文件")
        for rel in needed:
            check_cancel(cancel_event)
            rel = safe_rel(rel)
            fragment = source.joinpath(
                *PurePosixPath(prefix + "romfs.files/" + rel).parts
            )
            if not fragment.is_file():
                raise PackError(f"RomFS 分片缺失：{prefix}romfs.files/{rel}")
            target = stage.joinpath(
                *PurePosixPath(prefix + "romfs.files/" + rel).parts
            )
            link_or_copy(fragment, target, cancel_event)

    # Call the exact upstream Python API: materialize(pack, img_rel, size, sha, say, progress).
    for rel_img, (size, digest) in image_rows.items():
        log(f"调用 S2Arm materialize()：{rel_img}")
        log("提示：正在执行 S2Arm 原生 RomFS 拼接；此阶段无法强制中断。点击取消后，将在原生函数返回或下一次进度回调时停止。")

        def progress(done, name=rel_img, total=size):
            check_cancel(cancel_event)
            log(f"  {name}: {done / (1024 ** 3):.2f} / {total / (1024 ** 3):.2f} GiB")

        native.materialize(str(stage), rel_img, size, digest, say=log, progress=progress)
        image = stage.joinpath(*PurePosixPath(rel_img).parts)
        if not image.is_file() or image.stat().st_size != size:
            raise PackError(f"拼接后的镜像大小不正确：{rel_img}")
        if sha256_file(image, cancel_event) != digest:
            raise PackError(f"拼接后的镜像 SHA256 不正确：{rel_img}")
        log(f"RomFS 校验通过：{rel_img}")


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
    native = load_native(install_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{game_dir.name}_pack.zip"

    with tempfile.TemporaryDirectory(prefix="s2arm_packager_", dir=str(output_dir)) as temp:
        stage = Path(temp) / "资源包"
        stage.mkdir()
        temp_zip = Path(temp) / output.name
        log(f"游戏目录：{game_dir}")
        log(f"Title ID：{title_id}（game.json）")
        log(f"资源包目录：{source}")
        log(f"manifest version：{manifest.get('version')}；索引文件：{len(rows)}")
        prepare_and_materialize(source, stage, rows, native, log, cancel_event)

        for i, (rel, size, _digest) in enumerate(rows, 1):
            check_cancel(cancel_event)
            path = stage.joinpath(*PurePosixPath(rel).parts)
            if not path.is_file():
                raise PackError(f"打包前文件缺失：{rel}")
            if path.stat().st_size != size:
                raise PackError(f"打包前文件大小不符：{rel}")
            if i % 500 == 0:
                log(f"打包前检查：{i}/{len(rows)}")

        root = f"{title_id}/资源包"
        count = 0
        log(f"生成 ZIP（不压缩，保留 ZIP64）：{output}")
        with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
            zf.writestr(f"{title_id}/", b"")
            zf.writestr(root + "/", b"")
            for path in sorted(stage.rglob("*")):
                check_cancel(cancel_event)
                if not path.is_file():
                    continue
                relative = path.relative_to(stage)
                if "romfs.files" in relative.parts:
                    continue
                arcname = f"{root}/{relative.as_posix()}"
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

        check_cancel(cancel_event)
        log("检查 ZIP 完整性……")
        with zipfile.ZipFile(temp_zip, "r") as zf:
            names = zf.namelist()
            for i, _name in enumerate(names, 1):
                check_cancel(cancel_event)
                if i % 500 == 0:
                    log(f"ZIP 检查：{i}/{len(names)}")
            for i, name in enumerate(names, 1):
                check_cancel(cancel_event)
                if name.endswith("/"):
                    continue
                with zf.open(name, "r") as member:
                    while member.read(CHUNK):
                        check_cancel(cancel_event)
                if i % 100 == 0:
                    log(f"ZIP 完整性校验：{i}/{len(names)}")
            name_set = set(names)
            required = {f"{root}/index.tsv", f"{root}/manifest.json"}
            missing = required - name_set
            if missing:
                raise PackError("ZIP 缺少必要文件：" + ", ".join(sorted(missing)))
            for rel, _, _ in rows:
                check_cancel(cancel_event)
                if f"{root}/{rel}" not in name_set:
                    raise PackError(f"ZIP 缺少索引文件：{rel}")
            if any("romfs.files" in PurePosixPath(name).parts for name in name_set):
                raise PackError("最终 ZIP 不应包含 romfs.files 分片目录。")
        check_cancel(cancel_event)
        os.replace(temp_zip, output)
        log(f"完成：{count} 个文件；ZIP 大小 {output.stat().st_size / (1024 ** 3):.2f} GiB")
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
        self._build()
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
            text=self._t("读取 game.json 的 Title ID，自动拼接 RomFS，并生成可直接解压到 iPhone games 文件夹的 ZIP"),
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
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.install_var.set(str(data.get("install_root") or self.install_var.get()))
                saved_lang = data.get("language")
                if saved_lang in ("zh", "en"):
                    self.lang = saved_lang
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    def _save_config(self):
        data = {"install_root": self.install_var.get().strip(), "language": self.lang}
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            temp_path = CONFIG_PATH.with_suffix(".tmp")
            temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp_path, CONFIG_PATH)
        except OSError as exc:
            self._append_log(self._localize_log(f"无法保存路径配置：{exc}"))

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
        try:
            title_id = read_title_id(game_dir)
        except PackError as exc:
            self.title_var.set("")
            self.output_dir_var.set("")
            messagebox.showerror(self._t("无法读取游戏信息"), str(exc))
            return
        self.title_var.set(title_id)
        self.output_dir_var.set(str(game_dir))
        pack_dir = game_dir / "image" / "ios" / "pack"
        self._log(self._localize_log(f"Title ID：{title_id}（来自 game.json）"))
        if pack_dir.is_dir():
            self._log(self._localize_log(f"已定位资源包目录：{pack_dir}"))
        else:
            self._log(self._localize_log(f"未找到预期资源包目录：{pack_dir}"))
            messagebox.showwarning(self._t("未找到资源包"), f"缺少固定目录：\n{pack_dir}")

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
            messagebox.showerror(self._t("资源包目录不存在"), f"找不到：{game_dir / 'image' / 'ios' / 'pack'}")
            return
        try:
            title_id = read_title_id(game_dir)
        except PackError as exc:
            messagebox.showerror(self._t("游戏信息错误"), str(exc))
            return
        self.title_var.set(title_id)
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
            self.cancel_event.set()
            self.cancel_button.configure(state="disabled")
            self.status.set(self._t("正在取消……"))
            self._append_log(self._localize_log("已请求取消，将在当前处理步骤可中断时停止。"))

    def _append_log(self, message):
        # Localize at the UI boundary, including logs emitted by GUI actions.
        message = self._localize_log(str(message))
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\\n")
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
                        messagebox.showinfo(self._t("打包完成"), f"资源包已生成：\n{value}")
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
