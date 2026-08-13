# -*- coding: utf-8 -*-
"""
下载工作线程 (Beta)
流水线: N_m3u8DL-RE → mp4decrypt(可选) → ffmpeg封装
- Windows 下 CREATE_NO_WINDOW 禁止黑窗
- 统一日志分类: SUCCESS / WARNING / ERROR / INFO
- 进度解析: 百分比 / 速度 / 已下载大小 / ETA
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from config import AppConfig
from m3u8_parser import M3U8ParseResult, VideoStream, AudioTrack, SubtitleStream


# ───────────────────── 平台兼容 ─────────────────────

def _get_creation_flags() -> int:
    """Windows 下返回 CREATE_NO_WINDOW，Linux 下返回 0。"""
    if sys.platform == "win32":
        return 0x08000000  # CREATE_NO_WINDOW
    return 0


def _get_startupinfo():
    """Windows 下隐藏窗口，Linux 返回 None。"""
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        return si
    return None


# ───────────────────── 日志级别 ─────────────────────

LOG_INFO = "INFO"
LOG_SUCCESS = "SUCCESS"
LOG_WARNING = "WARNING"
LOG_ERROR = "ERROR"


# ══════════════════════════════════════════════════════
# 下载线程
# ══════════════════════════════════════════════════════

class DownloadThread(QThread):
    """下载工作线程"""

    # 日志信号: (级别, 消息)
    log = Signal(str, str)
    # 进度信号: 百分比 0-100
    progress = Signal(int)
    # 速度信号: 字符串如 "1.2 MB/s"
    speed = Signal(str)
    # 已下载大小信号: 字符串如 "12.5 MB / 100 MB"
    size = Signal(str)
    # 剩余时间信号: 字符串如 "00:01:23"
    eta = Signal(str)
    # 完成信号
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, config: AppConfig, parse_result: M3U8ParseResult,
                 selected_video: VideoStream | None,
                 selected_audio: AudioTrack | None,
                 selected_subtitles: list[SubtitleStream]):
        super().__init__()
        self.config = config
        self.parse_result = parse_result
        self.selected_video = selected_video
        self.selected_audio = selected_audio
        self.selected_subtitles = selected_subtitles
        self._stop_flag = False
        self._process: subprocess.Popen | None = None
        self._creation_flags = _get_creation_flags()
        self._startupinfo = _get_startupinfo()
        self._ffmpeg_duration = 0.0  # ffmpeg输入文件总时长(秒)，用于进度计算

    def stop(self):
        self._stop_flag = True
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception:
                pass

    # ══════════════════════════════════════════════
    # 主流程
    # ══════════════════════════════════════════════

    def run(self):
        try:
            self._emit_log(LOG_INFO, "=" * 50)
            self._emit_log(LOG_INFO, "开始下载任务")
            self._emit_log(LOG_INFO, "=" * 50)

            tools = self.config.tool_paths
            n_m3u8dl = tools.get("n_m3u8dl")
            mp4decrypt = tools.get("mp4decrypt")
            ffmpeg = tools.get("ffmpeg")

            if not n_m3u8dl:
                self._emit_log(LOG_ERROR, "未找到 N_m3u8DL-RE，请将工具放在程序目录")
                self.failed.emit("未找到 N_m3u8DL-RE")
                return

            # 输出目录
            save_dir = Path(self.config.save_dir) if self.config.save_dir else Path.cwd()
            save_dir.mkdir(parents=True, exist_ok=True)

            # 输出格式 & 文件名
            output_format = (self.config.output_format or "mp4").lower()
            ext_map = {"mp4": ".mp4", "mkv": ".mkv", "ts": ".ts"}
            target_ext = ext_map.get(output_format, ".mp4")
            filename = self.config.filename or f"output{target_ext}"
            # 确保文件后缀与选择的输出格式一致
            stem = Path(filename).stem
            filename = stem + target_ext
            final_output = str(save_dir / filename)
            self._emit_log(LOG_INFO, f"输出格式: {output_format.upper()} → {filename}")

            # 解密工具选择
            dt = self.config.decryption.decrypt_tool
            dt_label = {"auto": "自动(mp4decrypt)", "builtin": "N_m3u8DL-RE内置", "none": "不解密"}.get(dt, dt)
            self._emit_log(LOG_INFO, f"解密工具: {dt_label}")

            # 临时目录
            work_dir = Path(tempfile.mkdtemp(prefix="m3u8_dl_"))
            self._emit_log(LOG_INFO, f"临时目录: {work_dir}")

            try:
                # ── 步骤1: N_m3u8DL-RE ──
                self.progress.emit(2)
                self._emit_log(LOG_INFO, "[步骤1/3] 调用 N_m3u8DL-RE 下载...")
                raw_video = self._step_n_m3u8dl(n_m3u8dl, work_dir)
                if self._stop_flag:
                    self._emit_log(LOG_WARNING, "任务已取消")
                    return
                if not raw_video:
                    self._emit_log(LOG_ERROR, "N_m3u8DL-RE 下载失败")
                    self.failed.emit("N_m3u8DL-RE 下载失败")
                    return
                self._emit_log(LOG_SUCCESS, "N_m3u8DL-RE 下载完成")

                # ── 步骤2: mp4decrypt ──
                decrypted_video = raw_video
                need_decrypt = self._need_decryption()
                if self.config.decryption.decrypt_tool == "builtin":
                    self._emit_log(LOG_INFO, "[步骤2/3] 使用 N_m3u8DL-RE 内置解密，跳过 mp4decrypt")
                elif need_decrypt and mp4decrypt:
                    self.progress.emit(62)
                    self._emit_log(LOG_INFO, "[步骤2/3] 调用 mp4decrypt 解密...")
                    decrypted_video = self._step_mp4decrypt(mp4decrypt, raw_video, work_dir)
                    if not decrypted_video:
                        self._emit_log(LOG_ERROR, "mp4decrypt 解密失败")
                        self.failed.emit("mp4decrypt 解密失败")
                        return
                    self._emit_log(LOG_SUCCESS, "mp4decrypt 解密完成")
                elif need_decrypt and not mp4decrypt:
                    self._emit_log(LOG_WARNING, "检测到加密但未找到 mp4decrypt，跳过解密")
                else:
                    self._emit_log(LOG_INFO, "[步骤2/3] 无需解密，跳过")

                # ── 步骤3: ffmpeg ──
                self.progress.emit(82)
                self._emit_log(LOG_INFO, "[步骤3/3] 调用 ffmpeg 封装...")
                subtitle_files = self._collect_subtitles(work_dir)
                ok = self._step_ffmpeg(ffmpeg, decrypted_video, subtitle_files, final_output, output_format)
                if not ok:
                    self._emit_log(LOG_WARNING, "ffmpeg 封装失败，尝试直接复制下载结果")
                    try:
                        shutil.copy2(decrypted_video, final_output)
                        self._emit_log(LOG_SUCCESS, f"已复制到: {final_output}")
                    except Exception as e:
                        self._emit_log(LOG_ERROR, f"最终文件生成失败: {e}")
                        self.failed.emit(f"最终文件生成失败: {e}")
                        return

                self.progress.emit(100)
                self.speed.emit("0 B/s")
                self.eta.emit("00:00:00")
                self._emit_log(LOG_INFO, "=" * 50)
                self._emit_log(LOG_SUCCESS, f"下载完成: {final_output}")
                self._emit_log(LOG_INFO, "=" * 50)
                self.finished_ok.emit(final_output)

            finally:
                try:
                    shutil.rmtree(work_dir, ignore_errors=True)
                except Exception:
                    pass

        except Exception as e:
            self._emit_log(LOG_ERROR, f"下载异常: {e}")
            self.failed.emit(f"下载异常: {e}")

    # ══════════════════════════════════════════════
    # 步骤1: N_m3u8DL-RE
    # ══════════════════════════════════════════════

    def _step_n_m3u8dl(self, exe: str, work_dir: Path) -> str | None:
        cmd: list[str] = [exe, self.config.m3u8_url]

        # Cookie
        cookie = self.config.effective_cookie()
        if cookie:
            cmd.extend(["--header", f"Cookie: {cookie}"])

        # Headers
        headers = self.config.build_headers_dict()
        for k, v in headers.items():
            if k.lower() == "cookie":
                continue
            cmd.extend(["--header", f"{k}: {v}"])

        # 视频清晰度
        if self.selected_video and self.selected_video.resolution:
            cmd.extend(["--select-video", f"res={self.selected_video.resolution}"])
        elif self.selected_video:
            cmd.extend(["--select-video", f"id={self.selected_video.index}"])
        else:
            cmd.extend(["--select-video", "best"])

        # 音频
        if self.selected_audio:
            an = self.selected_audio.name or self.selected_audio.language
            if an:
                cmd.extend(["--select-audio", f"name={an}"])

        # 字幕
        if self.config.subtitle.download_external and self.selected_subtitles:
            fmt = self.config.subtitle.format.lower()
            cmd.extend(["--sub-format", fmt])
            for sub in self.selected_subtitles:
                sn = sub.name or sub.language
                if sn:
                    cmd.extend(["--select-subtitle", f"name={sn}"])

        # 输出
        base_name = Path(self.config.filename or "output").stem
        cmd.extend([
            "--save-dir", str(work_dir),
            "--save-name", base_name,
            "-M", "format=mp4",
            "--no-date-info",
        ])

        # 内置解密 key (AES-128)
        dec = self.config.decryption
        if dec.key and dec.encryption_type in ("aes-128", "auto"):
            cmd.extend(["--key", dec.key])

        self._emit_log(LOG_INFO, f"命令: {' '.join(cmd)}")
        self._emit_log(LOG_INFO, "-" * 40)

        ret = self._run_process(cmd, work_dir, tool_name="N_m3u8DL-RE")
        if ret != 0:
            self._emit_log(LOG_ERROR, f"N_m3u8DL-RE 退出码: {ret}")
            return None

        # 查找结果
        video_files = list(work_dir.glob(f"{base_name}*.mp4"))
        if not video_files:
            video_files = [f for f in work_dir.glob(f"{base_name}*")
                           if f.suffix.lower() in (".mp4", ".m4v", ".ts", ".mkv")]
        if video_files:
            result = str(video_files[0])
            self._emit_log(LOG_SUCCESS, f"下载文件: {result}")
            return result

        self._emit_log(LOG_ERROR, "未找到下载结果文件")
        return None

    # ══════════════════════════════════════════════
    # 步骤2: mp4decrypt
    # ══════════════════════════════════════════════

    def _step_mp4decrypt(self, exe: str, input_file: str, work_dir: Path) -> str | None:
        dec = self.config.decryption
        output_file = str(work_dir / (Path(input_file).stem + "_decrypted.mp4"))
        cmd: list[str] = [exe]

        if dec.key_file and Path(dec.key_file).is_file():
            cmd.extend(["--keys", dec.key_file])
            self._emit_log(LOG_INFO, f"使用密钥文件: {dec.key_file}")
        elif dec.key:
            if dec.kid:
                cmd.extend(["--key", f"{dec.kid}:{dec.key}"])
            else:
                cmd.extend(["--key", dec.key])
            self._emit_log(LOG_INFO, f"使用密钥 KID={'***' if dec.kid else 'N/A'} KEY=***")
        else:
            self._emit_log(LOG_WARNING, "未配置密钥，跳过解密")
            return input_file

        cmd.extend([input_file, output_file])
        self._emit_log(LOG_INFO, f"命令: {' '.join(cmd)}")

        ret = self._run_process(cmd, work_dir, tool_name="mp4decrypt")
        if ret != 0:
            self._emit_log(LOG_ERROR, f"mp4decrypt 退出码: {ret}")
            return None
        if Path(output_file).is_file():
            self._emit_log(LOG_SUCCESS, f"解密文件: {output_file}")
            return output_file
        self._emit_log(LOG_ERROR, "未找到解密结果")
        return None

    # ══════════════════════════════════════════════
    # 步骤3: ffmpeg
    # ══════════════════════════════════════════════

    def _step_ffmpeg(self, ffmpeg: str | None, video_file: str,
                     subtitle_files: list[str], output_file: str,
                     output_format: str = "mp4") -> bool:
        if not ffmpeg:
            self._emit_log(LOG_WARNING, "未找到 ffmpeg，直接复制下载结果")
            try:
                shutil.copy2(video_file, output_file)
                return True
            except Exception as e:
                self._emit_log(LOG_ERROR, f"复制失败: {e}")
                return False

        self._ffmpeg_duration = 0.0
        cmd: list[str] = [ffmpeg, "-y", "-i", video_file]
        for sf in subtitle_files:
            cmd.extend(["-i", sf])
        cmd.extend(["-c", "copy"])
        # 字幕编码: MP4用mov_text，MKV自动，TS不支持内嵌字幕
        if subtitle_files and output_format == "mp4":
            cmd.extend(["-c:s", "mov_text"])
        elif subtitle_files and output_format == "mkv":
            cmd.extend(["-c:s", "srt"])
        # 封装格式
        if output_format == "mkv":
            cmd.extend(["-f", "matroska"])
        elif output_format == "ts":
            cmd.extend(["-f", "mpegts"])
        cmd.append(output_file)

        self._emit_log(LOG_INFO, f"命令: {' '.join(cmd)}")
        ret = self._run_process(cmd, Path(video_file).parent, tool_name="ffmpeg")
        if ret != 0:
            self._emit_log(LOG_ERROR, f"ffmpeg 退出码: {ret}")
            return False
        if Path(output_file).is_file():
            self._emit_log(LOG_SUCCESS, f"封装完成: {output_file}")
            return True
        return False

    # ══════════════════════════════════════════════
    # 子进程运行（核心）
    # ══════════════════════════════════════════════

    def _run_process(self, cmd: list[str], cwd: Path, tool_name: str = "") -> int:
        try:
            self._process = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=self._creation_flags,
                startupinfo=self._startupinfo,
            )
        except FileNotFoundError as e:
            self._emit_log(LOG_ERROR, f"无法启动程序: {e}")
            return -1
        except Exception as e:
            self._emit_log(LOG_ERROR, f"启动进程失败: {e}")
            return -1

        assert self._process.stdout is not None
        for line in self._process.stdout:
            if self._stop_flag:
                self._process.terminate()
                break
            line = line.rstrip()
            if not line:
                continue

            # 自动分类日志级别
            level = self._classify_line(line, tool_name)
            self._emit_log(level, line)

            # 进度解析
            if tool_name == "N_m3u8DL-RE":
                self._parse_progress(line)
            elif tool_name == "ffmpeg":
                self._parse_ffmpeg_progress(line)

        self._process.wait()
        return self._process.returncode or 0

    # ══════════════════════════════════════════════
    # 日志分类
    # ══════════════════════════════════════════════

    @staticmethod
    def _classify_line(line: str, tool_name: str) -> str:
        """根据内容自动判断日志级别。使用严格关键词，避免误判。"""
        low = line.lower()
        # 严格错误关键词（全词匹配或明确的错误标识）
        error_patterns = (
            r'\berror\b', r'\bfailed\b', r'\bexception\b', r'\btraceback\b',
            r'失败', r'错误', r'permission denied', r'invalid argument',
            r'no such file or directory', r'could not', r'unable to',
        )
        for pat in error_patterns:
            if re.search(pat, low):
                return LOG_ERROR
        # 警告
        if any(kw in low for kw in ("warning", "warn", "警告", "skip", "跳过",
                                     "deprecated", "fallback", "not found")):
            return LOG_WARNING
        # 成功
        if any(kw in low for kw in ("success", "succeed", "完成", "成功",
                                     "done", "finished", "downloaded",
                                     "completed", "muxing completed", "已完成")):
            return LOG_SUCCESS
        return LOG_INFO

    # ══════════════════════════════════════════════
    # 进度解析
    # ══════════════════════════════════════════════

    def _parse_progress(self, line: str):
        """从 N_m3u8DL-RE 输出中提取进度信息。"""
        # 百分比: 12.3% 或 12%
        pct = None
        m = re.search(r'(\d+(?:\.\d+)?)\s*%', line)
        if m:
            try:
                pct = float(m.group(1))
                # 映射到 2%-60% 下载区间
                mapped = 2 + int(pct * 0.58)
                self.progress.emit(min(mapped, 60))
            except ValueError:
                pass

        # 速度: 1.2 MB/s 或 500 KB/s 或 1.5GB/s
        m = re.search(r'(\d+(?:\.\d+)?)\s*(KB|MB|GB|TB)/s', line, re.IGNORECASE)
        if m:
            self.speed.emit(f"{m.group(1)} {m.group(2).upper()}/s")

        # 已下载大小: 12.5 MB / 100 MB 或 12.5MB of 100MB
        m = re.search(r'(\d+(?:\.\d+)?)\s*(KB|MB|GB|TB)\s*(?:/|of)\s*(\d+(?:\.\d+)?)\s*(KB|MB|GB|TB)',
                      line, re.IGNORECASE)
        if m:
            self.size.emit(f"{m.group(1)} {m.group(2).upper()} / {m.group(3)} {m.group(4).upper()}")
        else:
            # 单一大小时也更新
            m2 = re.search(r'(\d+(?:\.\d+)?)\s*(KB|MB|GB|TB)\b', line, re.IGNORECASE)
            if m2 and pct:
                self.size.emit(f"{m2.group(1)} {m2.group(2).upper()}")

        # ETA: 00:01:23 或 1m23s 或 83s remaining
        m = re.search(r'(\d{1,2}):(\d{2}):(\d{2})', line)
        if m:
            self.eta.emit(f"{int(m.group(1)):02d}:{m.group(2)}:{m.group(3)}")
        else:
            m = re.search(r'(?:eta|remaining|剩余)\s*[:：]?\s*(\d+)\s*m\s*(\d+)\s*s', line, re.IGNORECASE)
            if m:
                self.eta.emit(f"00:{int(m.group(1)):02d}:{int(m.group(2)):02d}")
            else:
                m = re.search(r'(?:eta|remaining|剩余)\s*[:：]?\s*(\d+)\s*s', line, re.IGNORECASE)
                if m:
                    secs = int(m.group(1))
                    self.eta.emit(f"00:{secs // 60:02d}:{secs % 60:02d}")

    # ══════════════════════════════════════════════
    # ffmpeg 进度解析
    # ══════════════════════════════════════════════

    def _parse_ffmpeg_progress(self, line: str):
        """从 ffmpeg 输出中提取转码进度和速度。"""
        low = line.lower()
        # 解析总时长: Duration: 00:05:30.50
        if "duration:" in low:
            m = re.search(r'duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', low)
            if m:
                self._ffmpeg_duration = (
                    int(m.group(1)) * 3600
                    + int(m.group(2)) * 60
                    + float(m.group(3))
                )
            return
        # 解析进度行: frame= 123 fps= 30 q=-1.0 size= 1024kB time=00:00:05.00 bitrate=... speed=1.5x
        if "time=" in low and "speed=" in low:
            # 当前时间
            m = re.search(r'time=(\d+):(\d+):(\d+(?:\.\d+)?)', low)
            if m and self._ffmpeg_duration > 0:
                cur = (int(m.group(1)) * 3600
                       + int(m.group(2)) * 60
                       + float(m.group(3)))
                pct = min(cur / self._ffmpeg_duration, 1.0)
                # 映射到 82%-100% 区间
                mapped = 82 + int(pct * 18)
                self.progress.emit(min(mapped, 99))
                # 剩余时间
                if pct > 0.01:
                    remaining = (self._ffmpeg_duration - cur) / max(pct, 0.01) * (1 - pct)
                    remaining = max(0, remaining)
                    self.eta.emit(f"{int(remaining // 3600):02d}:{int(remaining % 3600 // 60):02d}:{int(remaining % 60):02d}")
            # 速度: speed=1.5x
            m = re.search(r'speed=\s*(\d+(?:\.\d+)?)\s*x', low)
            if m:
                self.speed.emit(f"x{m.group(1)}")
            # frame / fps
            m = re.search(r'frame=\s*(\d+)', low)
            if m:
                frame = m.group(1)
                m2 = re.search(r'fps=\s*(\d+(?:\.\d+)?)', low)
                fps = m2.group(1) if m2 else "?"
                self.size.emit(f"帧:{frame} ({fps}fps)")

    # ══════════════════════════════════════════════
    # 辅助
    # ══════════════════════════════════════════════

    def _need_decryption(self) -> bool:
        dec = self.config.decryption
        # 用户选择"不解密"
        if dec.decrypt_tool == "none":
            return False
        # 用户选择"N_m3u8DL-RE内置" → 由N_m3u8DL-RE的--key处理，不走mp4decrypt
        if dec.decrypt_tool == "builtin":
            return False
        # auto: 自动检测
        if dec.encryption_type == "auto":
            return bool(self.parse_result.encryption_detected) and bool(dec.key or dec.key_file)
        if dec.encryption_type in ("cenc", "sample-aes"):
            return bool(dec.key or dec.key_file)
        return False

    def _collect_subtitles(self, work_dir: Path) -> list[str]:
        subs: list[str] = []
        for ext in ("*.srt", "*.vtt", "*.ass"):
            subs.extend(str(f) for f in work_dir.glob(ext))
        return subs

    def _emit_log(self, level: str, msg: str):
        self.log.emit(level, msg)
