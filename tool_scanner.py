# -*- coding: utf-8 -*-
"""
工具扫描模块 (Beta)
三级优先级:
  1. 程序目录 (exe 所在目录)
  2. 程序目录下的 tools/ 子目录
  3. 系统 PATH 环境变量
支持通配符 N_m3u8DL-RE*.exe
禁止写死路径。
"""
from __future__ import annotations

import glob
import os
import shutil
import sys
from pathlib import Path


def get_app_dir() -> Path:
    """获取程序运行目录（PyInstaller 打包后为 exe 所在目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _scan_dir(directory: Path, patterns: list[str]) -> str | None:
    """在指定目录中按通配符模式查找，返回第一个存在的绝对路径。"""
    if not directory or not directory.is_dir():
        return None
    for pat in patterns:
        matches = glob.glob(str(directory / pat))
        if matches:
            return str(Path(matches[0]).resolve())
    return None


def _scan_path(patterns: list[str]) -> str | None:
    """在系统 PATH 中查找。"""
    for pat in patterns:
        # shutil.which 不支持通配符，先尝试精确名
        for name in [pat.replace("*", "")] if "*" in pat else [pat]:
            found = shutil.which(name)
            if found:
                return found
        # PATH 目录中通配符匹配
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)
        for d in path_dirs:
            matches = glob.glob(os.path.join(d, pat))
            if matches:
                return str(Path(matches[0]).resolve())
    return None


def _find_tool(patterns: list[str], config_path: str | None = None) -> str | None:
    """
    三级查找:
      0. config.json 中用户手动指定的路径 (最高优先级)
      1. 程序目录
      2. tools/ 子目录
      3. 系统 PATH
    """
    app_dir = get_app_dir()

    # 0. 配置中指定的路径
    if config_path and Path(config_path).is_file():
        return config_path

    # 1. 程序目录
    result = _scan_dir(app_dir, patterns)
    if result:
        return result

    # 2. tools 子目录
    result = _scan_dir(app_dir / "tools", patterns)
    if result:
        return result

    # 3. 系统 PATH
    result = _scan_path(patterns)
    if result:
        return result

    return None


def scan_n_m3u8dl(config_path: str | None = None) -> str | None:
    """扫描 N_m3u8DL-RE，支持通配符。"""
    patterns = [
        "N_m3u8DL-RE(6).exe",
        "N_m3u8DL-RE*.exe",
        "N_m3u8DL-RE.exe",
        "n_m3u8dl-re*.exe",
        "N_m3u8DL-RE(6)",
        "N_m3u8DL-RE",
    ]
    return _find_tool(patterns, config_path)


def scan_mp4decrypt(config_path: str | None = None) -> str | None:
    """扫描 mp4decrypt。"""
    patterns = ["mp4decrypt.exe", "mp4decrypt"]
    return _find_tool(patterns, config_path)


def scan_ffmpeg(config_path: str | None = None) -> str | None:
    """扫描 ffmpeg。"""
    patterns = ["ffmpeg.exe", "ffmpeg"]
    return _find_tool(patterns, config_path)


def scan_all(config_paths: dict[str, str] | None = None) -> dict[str, str | None]:
    """
    一次性扫描所有工具。
    config_paths: {'n_m3u8dl': '路径', 'mp4decrypt': '路径', 'ffmpeg': '路径'}
    """
    cp = config_paths or {}
    return {
        "n_m3u8dl": scan_n_m3u8dl(cp.get("n_m3u8dl")),
        "mp4decrypt": scan_mp4decrypt(cp.get("mp4decrypt")),
        "ffmpeg": scan_ffmpeg(cp.get("ffmpeg")),
    }
