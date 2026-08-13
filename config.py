# -*- coding: utf-8 -*-
"""
配置管理模块 (Beta)
所有用户选项写入 config.json，下次启动自动恢复。
包含: 下载选项 / 解密设置 / 请求头 / 保存路径 / 工具路径
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tool_scanner import get_app_dir


CONFIG_FILENAME = "config.json"


def get_config_path() -> Path:
    return get_app_dir() / CONFIG_FILENAME


@dataclass
class DecryptionConfig:
    encryption_type: str = "auto"       # auto / aes-128 / cenc / sample-aes
    key: str = ""
    kid: str = ""
    key_file: str = ""
    decrypt_tool: str = "auto"          # auto / mp4decrypt


@dataclass
class RequestHeadersConfig:
    user_agent: str = ""
    referer: str = ""
    cookie: str = ""
    authorization: str = ""


@dataclass
class SubtitleConfig:
    download_external: bool = True
    languages: list[str] = field(default_factory=lambda: ["zh-CN", "en"])
    format: str = "srt"                 # srt / vtt / ass


@dataclass
class AppConfig:
    # 基本输入
    m3u8_url: str = ""
    cookie: str = ""
    headers_text: str = ""

    # 视频 / 音频
    video_quality: str = "auto"         # auto / 4k / 1080p / 720p / 480p / 360p
    custom_resolution: str = ""
    audio_track: str = "auto"           # auto / 音轨标识

    # 字幕
    subtitle: SubtitleConfig = field(default_factory=SubtitleConfig)

    # 保存
    save_dir: str = ""
    filename: str = "视频名称.mp4"
    output_format: str = "mp4"          # mp4 / mkv / ts

    # 解密
    decryption: DecryptionConfig = field(default_factory=DecryptionConfig)

    # 请求头
    request_headers: RequestHeadersConfig = field(default_factory=RequestHeadersConfig)

    # 工具路径 (用户手动选择后持久化)
    tool_paths: dict[str, str] = field(default_factory=dict)

    # ── 序列化 ──
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        cfg = cls()
        for key, value in data.items():
            if not hasattr(cfg, key):
                continue
            if key == "subtitle" and isinstance(value, dict):
                cfg.subtitle = SubtitleConfig(**{k: v for k, v in value.items()
                                                   if k in SubtitleConfig.__dataclass_fields__})
            elif key == "decryption" and isinstance(value, dict):
                cfg.decryption = DecryptionConfig(**{k: v for k, v in value.items()
                                                      if k in DecryptionConfig.__dataclass_fields__})
            elif key == "request_headers" and isinstance(value, dict):
                cfg.request_headers = RequestHeadersConfig(**{k: v for k, v in value.items()
                                                               if k in RequestHeadersConfig.__dataclass_fields__})
            else:
                setattr(cfg, key, value)
        return cfg

    # ── 持久化 ──
    def save(self) -> bool:
        try:
            path = get_config_path()
            path.write_text(
                json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return True
        except Exception:
            return False

    @classmethod
    def load(cls) -> "AppConfig":
        path = get_config_path()
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except Exception:
            return cls()

    # ── 请求头辅助 ──
    def build_headers_dict(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        rh = self.request_headers
        if rh.user_agent:
            headers["User-Agent"] = rh.user_agent
        if rh.referer:
            headers["Referer"] = rh.referer
        if rh.authorization:
            headers["Authorization"] = rh.authorization
        if self.headers_text:
            for line in self.headers_text.strip().splitlines():
                line = line.strip()
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip()] = v.strip()
        return headers

    def effective_cookie(self) -> str:
        if self.cookie:
            return self.cookie
        return self.request_headers.cookie
