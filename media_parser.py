# -*- coding: utf-8 -*-
"""
媒体统一解析模块
支持 HLS (M3U8) 和 DASH (MPD) 两种格式。
自动识别格式，返回统一的解析结果结构。
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin

import requests

# 复用 M3U8 解析器的数据结构
from m3u8_parser import (
    VideoStream,
    AudioTrack,
    SubtitleStream,
    M3U8ParseResult,
    M3U8Parser,
)

# 兼容别名：MediaParseResult 即 M3U8ParseResult
MediaParseResult = M3U8ParseResult

# DASH MPD 命名空间
DASH_NS = "urn:mpeg:dash:schema:mpd:2011"
NS = {"dash": DASH_NS}


def detect_format(url_or_text: str) -> str:
    """
    自动识别媒体格式。
    返回: "hls" / "dash" / "unknown"
    识别规则:
      - URL 以 .m3u8 结尾 → HLS
      - URL 以 .mpd 结尾 → DASH
      - 内容包含 #EXTM3U → HLS
      - 内容包含 <MPD 或 MPD 标签 → DASH
    """
    s = url_or_text.strip()
    lower = s.lower()

    # URL 后缀识别
    if ".m3u8" in lower:
        return "hls"
    if ".mpd" in lower:
        return "dash"

    # 内容识别
    if "#extm3u" in lower:
        return "hls"
    if "<mpd" in lower or "mpd" in lower[:200] and "adaptationset" in lower:
        return "dash"

    return "unknown"


def format_label(fmt: str) -> str:
    """格式显示名称。"""
    return {
        "hls": "HLS M3U8",
        "dash": "DASH MPD",
        "unknown": "未知格式",
    }.get(fmt, fmt.upper())


def _fetch(url: str, cookie: str = "", headers: dict | None = None,
           timeout: int = 30) -> str:
    """带 Cookie/Headers 的 HTTP GET，返回文本内容。"""
    h = {"User-Agent": "Mozilla/5.0"}
    if headers:
        h.update(headers)
    if cookie:
        h["Cookie"] = cookie
    resp = requests.get(url, headers=h, timeout=timeout, verify=False)
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def parse_m3u8(url: str, cookie: str = "",
               headers: dict | None = None) -> M3U8ParseResult:
    """解析 HLS M3U8（委托给现有 M3U8Parser）。"""
    parser = M3U8Parser()
    return parser.parse(url, cookie=cookie, headers=headers or {})


def parse_mpd(url: str, cookie: str = "",
              headers: dict | None = None) -> M3U8ParseResult:
    """
    解析 DASH MPD。
    读取 MPD → Period → AdaptationSet → Representation，
    提取视频清晰度/分辨率/码率、音轨、字幕。
    """
    text = _fetch(url, cookie, headers)
    result = M3U8ParseResult()
    result.raw_text = text
    result.base_url = url
    result.is_master = True

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return result

    # 处理命名空间：标签可能是 {urn:...}AdaptationSet 或纯 AdaptationSet
    def _localname(elem: ET.Element) -> str:
        tag = elem.tag
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    def _findall(parent: ET.Element, name: str) -> list[ET.Element]:
        """同时查找带命名空间和不带命名空间的标签。"""
        found = parent.findall(f"{{{DASH_NS}}}{name}")
        if not found:
            found = parent.findall(name)
        return found

    def _get(elem: ET.Element, attr: str) -> str:
        """获取属性，兼容带/不带命名空间。"""
        val = elem.get(attr)
        if val is not None:
            return val
        # 尝试带命名空间的属性（少见）
        for k, v in elem.attrib.items():
            if k.split("}", 1)[-1] == attr:
                return v
        return ""

    periods = _findall(root, "Period")
    if not periods:
        periods = [root]  # 有些 MPD 直接在根下放 AdaptationSet

    video_idx = 0
    for period in periods:
        for ad_set in _findall(period, "AdaptationSet"):
            content_type = _get(ad_set, "contentType").lower()
            mime_type = _get(ad_set, "mimeType").lower()
            lang = _get(ad_set, "lang")

            # 判断类型
            is_video = content_type == "video" or mime_type.startswith("video/")
            is_audio = content_type == "audio" or mime_type.startswith("audio/")
            is_text = (content_type in ("text", "subtitle", "caption")
                       or mime_type.startswith("text/")
                       or "vtt" in mime_type or "ttml" in mime_type)

            reps = _findall(ad_set, "Representation")

            if is_video:
                for rep in reps:
                    width = int(_get(rep, "width") or 0)
                    height = int(_get(rep, "height") or 0)
                    bandwidth = int(_get(rep, "bandwidth") or 0)
                    codecs = _get(rep, "codecs") or _get(ad_set, "codecs")
                    frame_rate = _get(rep, "frameRate") or _get(ad_set, "frameRate")
                    try:
                        fr = float(frame_rate) if frame_rate else 0.0
                    except ValueError:
                        fr = 0.0
                    rep_id = _get(rep, "id")

                    vs = VideoStream(
                        index=video_idx,
                        bandwidth=bandwidth,
                        resolution=f"{width}x{height}" if width and height else "",
                        width=width,
                        height=height,
                        codecs=codecs,
                        frame_rate=fr,
                        uri=url,  # DASH 用 MPD 地址即可，N_m3u8DL-RE 直接处理
                        label="",
                    )
                    vs.label = vs.quality_label()
                    result.videos.append(vs)
                    video_idx += 1

            elif is_audio:
                for rep in reps:
                    bandwidth = int(_get(rep, "bandwidth") or 0)
                    codecs = _get(rep, "codecs") or _get(ad_set, "codecs")
                    sample_rate = _get(rep, "audioSamplingRate") or _get(ad_set, "audioSamplingRate")
                    channels_elem = _findall(rep, "AudioChannelConfiguration")
                    channels = ""
                    if channels_elem:
                        channels = _get(channels_elem[0], "value")
                    rep_id = _get(rep, "id")

                    # 音频编码显示名
                    codec_label = codecs.upper() if codecs else "AAC"
                    at = AudioTrack(
                        group_id=rep_id or f"audio_{bandwidth}",
                        name=f"{codec_label} {channels or ''}".strip(),
                        language=lang,
                        default=(_get(ad_set, "default") == "true"),
                        autoselect=(_get(ad_set, "autoSelect") == "true"),
                        uri=url,
                        channels=channels,
                    )
                    result.audios.append(at)

            elif is_text:
                for rep in reps:
                    rep_id = _get(rep, "id")
                    ss = SubtitleStream(
                        group_id=rep_id or f"sub_{lang}",
                        name=lang or "字幕",
                        language=lang,
                        default=(_get(ad_set, "default") == "true"),
                        autoselect=(_get(ad_set, "autoSelect") == "true"),
                        uri=url,
                    )
                    result.subtitles.append(ss)

            # 检测加密 (ContentProtection)
            if _findall(ad_set, "ContentProtection"):
                result.encryption_detected = "CENC"

    # 视频按分辨率降序
    result.videos.sort(key=lambda v: (v.height, v.bandwidth), reverse=True)
    return result


def parse_media(url: str, cookie: str = "",
                headers: dict | None = None) -> tuple[str, M3U8ParseResult]:
    """
    统一解析入口：自动识别格式并解析。
    返回: (format_type, parse_result)
    format_type: "hls" / "dash"
    """
    fmt = detect_format(url)
    if fmt == "dash":
        return "dash", parse_mpd(url, cookie, headers)
    # 默认按 HLS 处理（包含 unknown 情况，交给 M3U8Parser 尝试）
    return "hls", parse_m3u8(url, cookie, headers)


def parse_file(filepath: str, cookie: str = "",
               headers: dict | None = None) -> tuple[str, M3U8ParseResult]:
    """
    从本地文件解析（读取内容后判断格式）。
    支持 .m3u8 / .mpd / .txt（txt 内含 URL）。
    返回: (format_type, parse_result)
    """
    from pathlib import Path
    p = Path(filepath)
    text = p.read_text(encoding="utf-8", errors="replace")
    fmt = detect_format(text)

    if fmt == "hls":
        # 本地 m3u8 文件：用 file:// 或直接路径
        parser = M3U8Parser()
        result = parser.parse_text(text, base_url=str(p.parent) + "/")
        result.base_url = str(p)
        return "hls", result
    if fmt == "dash":
        # 本地 mpd 文件
        result = M3U8ParseResult()
        result.raw_text = text
        result.base_url = str(p)
        result.is_master = True
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return "dash", result
        # 复用 parse_mpd 的解析逻辑（通过临时包装）
        return "dash", _parse_mpd_root(root, result)
    # txt 文件：尝试提取第一行 URL
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("http"):
            return parse_media(line, cookie, headers)
    return "unknown", M3U8ParseResult()


def _parse_mpd_root(root: ET.Element, result: M3U8ParseResult) -> M3U8ParseResult:
    """从已解析的 XML 根元素填充 MPD 结果（供本地文件使用）。"""
    def _localname(elem):
        tag = elem.tag
        return tag.split("}", 1)[1] if "}" in tag else tag

    def _findall(parent, name):
        found = parent.findall(f"{{{DASH_NS}}}{name}")
        return found if found else parent.findall(name)

    def _get(elem, attr):
        val = elem.get(attr)
        if val is not None:
            return val
        for k, v in elem.attrib.items():
            if k.split("}", 1)[-1] == attr:
                return v
        return ""

    periods = _findall(root, "Period") or [root]
    video_idx = 0
    for period in periods:
        for ad_set in _findall(period, "AdaptationSet"):
            content_type = _get(ad_set, "contentType").lower()
            mime_type = _get(ad_set, "mimeType").lower()
            lang = _get(ad_set, "lang")
            is_video = content_type == "video" or mime_type.startswith("video/")
            is_audio = content_type == "audio" or mime_type.startswith("audio/")
            is_text = (content_type in ("text", "subtitle")
                       or mime_type.startswith("text/") or "vtt" in mime_type)
            reps = _findall(ad_set, "Representation")
            if is_video:
                for rep in reps:
                    w = int(_get(rep, "width") or 0)
                    h = int(_get(rep, "height") or 0)
                    bw = int(_get(rep, "bandwidth") or 0)
                    codecs = _get(rep, "codecs") or _get(ad_set, "codecs")
                    vs = VideoStream(index=video_idx, bandwidth=bw,
                                     resolution=f"{w}x{h}" if w and h else "",
                                     width=w, height=h, codecs=codecs, uri=result.base_url)
                    vs.label = vs.quality_label()
                    result.videos.append(vs)
                    video_idx += 1
            elif is_audio:
                for rep in reps:
                    bw = int(_get(rep, "bandwidth") or 0)
                    codecs = _get(rep, "codecs") or _get(ad_set, "codecs")
                    at = AudioTrack(group_id=_get(rep, "id") or f"audio_{bw}",
                                    name=(codecs or "AAC").upper(), language=lang, uri=result.base_url)
                    result.audios.append(at)
            elif is_text:
                for rep in reps:
                    ss = SubtitleStream(group_id=_get(rep, "id") or f"sub_{lang}",
                                        name=lang or "字幕", language=lang, uri=result.base_url)
                    result.subtitles.append(ss)
            if _findall(ad_set, "ContentProtection"):
                result.encryption_detected = "CENC"
    result.videos.sort(key=lambda v: (v.height, v.bandwidth), reverse=True)
    return result
