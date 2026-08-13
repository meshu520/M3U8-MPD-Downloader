# -*- coding: utf-8 -*-
"""
M3U8 解析模块
解析 master.m3u8，提取所有视频清晰度、音频轨道、字幕流。
支持带 Cookie / Headers 的请求。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin

import requests


# ───────────────────── 数据结构 ─────────────────────

@dataclass
class VideoStream:
    """视频流（EXT-X-STREAM-INF）"""
    index: int = 0               # 在 master 中的序号
    bandwidth: int = 0           # 带宽 bps
    resolution: str = ""         # 如 "1920x1080"
    width: int = 0
    height: int = 0
    codecs: str = ""
    frame_rate: float = 0.0
    audio_group: str = ""        # AUDIO 组 ID
    subtitle_group: str = ""     # SUBTITLES 组 ID
    uri: str = ""                # 媒体播放列表地址
    label: str = ""              # 显示标签，如 "1080P"

    def quality_label(self) -> str:
        """根据分辨率生成清晰度标签。"""
        if self.label:
            return self.label
        h = self.height
        if h >= 2160:
            return "4K UHD"
        if h >= 1440:
            return "2K"
        if h >= 1080:
            return "1080P"
        if h >= 720:
            return "720P"
        if h >= 480:
            return "480P"
        if h >= 360:
            return "360P"
        if h > 0:
            return f"{h}P"
        return f"{self.bandwidth // 1000}kbps"


@dataclass
class AudioTrack:
    """音频轨道（EXT-X-MEDIA TYPE=AUDIO）"""
    group_id: str = ""
    name: str = ""
    language: str = ""
    default: bool = False
    autoselect: bool = False
    uri: str = ""
    channels: str = ""

    def display_name(self) -> str:
        lang = self.language or "未知"
        name = self.name or lang
        if self.channels:
            return f"{name} ({lang}, {self.channels})"
        return f"{name} ({lang})"

    def language_category(self) -> str:
        """归类为 中文/英文/日语/原声/其他。"""
        lang = (self.language or "").lower()
        if lang in ("zh", "zh-cn", "zh-hans", "cmn", "mandarin", "chi", "zho"):
            return "中文"
        if lang in ("zh-tw", "zh-hant", "yue", "cantonese"):
            return "中文(繁)"
        if lang in ("en", "eng", "english"):
            return "英文"
        if lang in ("ja", "jpn", "japanese"):
            return "日语"
        if lang in ("ko", "kor", "korean"):
            return "韩语"
        if self.default:
            return "原声"
        return "其他"


@dataclass
class SubtitleStream:
    """字幕流（EXT-X-MEDIA TYPE=SUBTITLES）"""
    group_id: str = ""
    name: str = ""
    language: str = ""
    default: bool = False
    autoselect: bool = False
    forced: bool = False
    uri: str = ""

    def display_name(self) -> str:
        lang = self.language or "未知"
        name = self.name or lang
        return f"{name} ({lang})"

    def language_category(self) -> str:
        lang = (self.language or "").lower()
        if lang in ("zh", "zh-cn", "zh-hans", "cmn", "chi", "zho"):
            return "简体中文"
        if lang in ("zh-tw", "zh-hant", "yue"):
            return "繁体中文"
        if lang in ("en", "eng", "english"):
            return "English"
        if lang in ("ja", "jpn", "japanese"):
            return "日本語"
        return "其他"


@dataclass
class M3U8ParseResult:
    """解析结果汇总"""
    is_master: bool = False
    videos: list[VideoStream] = field(default_factory=list)
    audios: list[AudioTrack] = field(default_factory=list)
    subtitles: list[SubtitleStream] = field(default_factory=list)
    raw_text: str = ""
    base_url: str = ""
    encryption_detected: str = ""   # "AES-128" / "SAMPLE-AES" / "CENC" / ""

    def best_video(self) -> Optional[VideoStream]:
        if not self.videos:
            return None
        return max(self.videos, key=lambda v: (v.height, v.bandwidth))

    def default_audio(self) -> Optional[AudioTrack]:
        if not self.audios:
            return None
        for a in self.audios:
            if a.default:
                return a
        return self.audios[0]

    def default_subtitle(self) -> Optional[SubtitleStream]:
        if not self.subtitles:
            return None
        for s in self.subtitles:
            if s.default:
                return s
        return self.subtitles[0]


# ───────────────────── 解析器 ─────────────────────

class M3U8Parser:
    """M3U8 解析器"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def fetch(self, url: str, cookie: str = "", headers: dict | None = None) -> str:
        """请求 M3U8 内容。"""
        req_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
        }
        if cookie:
            req_headers["Cookie"] = cookie
        if headers:
            req_headers.update(headers)
        resp = requests.get(url, headers=req_headers, timeout=self.timeout, verify=False)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    def parse(self, url: str, cookie: str = "", headers: dict | None = None) -> M3U8ParseResult:
        """解析 M3U8 URL，返回结构化结果。"""
        text = self.fetch(url, cookie, headers)
        return self.parse_text(text, base_url=url)

    def parse_text(self, text: str, base_url: str = "") -> M3U8ParseResult:
        """解析 M3U8 文本内容。"""
        result = M3U8ParseResult(raw_text=text, base_url=base_url)
        lines = text.strip().splitlines()

        if not lines or not lines[0].strip().startswith("#EXTM3U"):
            raise ValueError("不是有效的 M3U8 文件（缺少 #EXTM3U 头）")

        # 检测是否为 master playlist
        result.is_master = any("#EXT-X-STREAM-INF" in l for l in lines)

        # 检测加密方式（扫描媒体播放列表中的 EXT-X-KEY）
        for line in lines:
            if "#EXT-X-KEY" in line:
                if "AES-128" in line:
                    result.encryption_detected = "AES-128"
                elif "SAMPLE-AES" in line:
                    result.encryption_detected = "SAMPLE-AES"
                elif "CENC" in line or "cbcs" in line.lower():
                    result.encryption_detected = "CENC"
                break

        if not result.is_master:
            # 媒体播放列表，没有多码率，构造一个默认视频流
            result.videos.append(VideoStream(
                index=0,
                uri=base_url,
                label="默认",
            ))
            return result

        # ── 解析 EXT-X-MEDIA（音频 / 字幕）──
        audio_map: dict[str, list[AudioTrack]] = {}
        subtitle_map: dict[str, list[SubtitleStream]] = {}

        for line in lines:
            line = line.strip()
            if not line.startswith("#EXT-X-MEDIA:"):
                continue
            attrs = self._parse_attributes(line[len("#EXT-X-MEDIA:"):])
            media_type = attrs.get("TYPE", "").upper()
            group_id = attrs.get("GROUP-ID", "")

            if media_type == "AUDIO":
                track = AudioTrack(
                    group_id=group_id,
                    name=attrs.get("NAME", ""),
                    language=attrs.get("LANGUAGE", ""),
                    default=attrs.get("DEFAULT", "NO").upper() == "YES",
                    autoselect=attrs.get("AUTOSELECT", "NO").upper() == "YES",
                    uri=attrs.get("URI", ""),
                    channels=attrs.get("CHANNELS", ""),
                )
                if track.uri and base_url:
                    track.uri = urljoin(base_url, track.uri)
                audio_map.setdefault(group_id, []).append(track)

            elif media_type == "SUBTITLES":
                sub = SubtitleStream(
                    group_id=group_id,
                    name=attrs.get("NAME", ""),
                    language=attrs.get("LANGUAGE", ""),
                    default=attrs.get("DEFAULT", "NO").upper() == "YES",
                    autoselect=attrs.get("AUTOSELECT", "NO").upper() == "YES",
                    forced=attrs.get("FORCED", "NO").upper() == "YES",
                    uri=attrs.get("URI", ""),
                )
                if sub.uri and base_url:
                    sub.uri = urljoin(base_url, sub.uri)
                subtitle_map.setdefault(group_id, []).append(sub)

        # ── 解析 EXT-X-STREAM-INF（视频流）──
        idx = 0
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("#EXT-X-STREAM-INF:"):
                attrs = self._parse_attributes(line[len("#EXT-X-STREAM-INF:"):])
                uri = ""
                # 下一行非注释行即为 URI
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    if next_line and not next_line.startswith("#"):
                        uri = next_line
                        break
                if uri and base_url:
                    uri = urljoin(base_url, uri)

                resolution = attrs.get("RESOLUTION", "")
                w, h = 0, 0
                if "x" in resolution.lower():
                    parts = re.split(r"[xX]", resolution)
                    try:
                        w, h = int(parts[0]), int(parts[1])
                    except (ValueError, IndexError):
                        pass

                vs = VideoStream(
                    index=idx,
                    bandwidth=int(attrs.get("BANDWIDTH", "0")),
                    resolution=resolution,
                    width=w,
                    height=h,
                    codecs=attrs.get("CODECS", ""),
                    frame_rate=float(attrs.get("FRAME-RATE", "0") or 0),
                    audio_group=attrs.get("AUDIO", ""),
                    subtitle_group=attrs.get("SUBTITLES", ""),
                    uri=uri,
                )
                vs.label = vs.quality_label()
                result.videos.append(vs)
                idx += 1
            i += 1

        # 汇总音频 / 字幕（去重）
        seen_audio = set()
        for group_tracks in audio_map.values():
            for t in group_tracks:
                key = (t.group_id, t.name, t.language, t.uri)
                if key not in seen_audio:
                    seen_audio.add(key)
                    result.audios.append(t)

        seen_sub = set()
        for group_subs in subtitle_map.values():
            for s in group_subs:
                key = (s.group_id, s.name, s.language, s.uri)
                if key not in seen_sub:
                    seen_sub.add(key)
                    result.subtitles.append(s)

        # 按分辨率降序排列视频
        result.videos.sort(key=lambda v: (v.height, v.bandwidth), reverse=True)

        return result

    @staticmethod
    def _parse_attributes(attr_str: str) -> dict[str, str]:
        """解析 M3U8 属性字符串，如 TYPE=AUDIO,GROUP-ID="audio",LANGUAGE="zh"。"""
        attrs: dict[str, str] = {}
        # 用正则匹配 KEY=VALUE 或 KEY="VALUE WITH COMMAS"
        pattern = re.compile(r'([A-Z0-9-]+)\s*=\s*("([^"]*)"|([^,]+))')
        for m in pattern.finditer(attr_str):
            key = m.group(1)
            value = m.group(3) if m.group(3) is not None else m.group(4).strip()
            attrs[key] = value
        return attrs
