# -*- coding: utf-8 -*-
"""
M3U8/MPD视频下载助手 v1.0.0
主窗口 - PySide6 深色专业风格
- 支持 HLS M3U8 / DASH MPD 双格式
- 拖拽文件 / URL 自动加入任务列表
- 多任务批量下载调度
- QTextEdit 彩色日志 (SUCCESS绿 / WARNING黄 / ERROR红 / INFO蓝)
- 日志控制: 清空 / 复制 / 保存(logs/YYYY-MM-DD.log)
- 工具缺失自动弹窗选择
- 实时状态: 速度 / 已下载 / 百分比 / ETA
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor, QFont, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QComboBox, QRadioButton, QCheckBox,
    QButtonGroup, QGroupBox, QProgressBar, QFrame, QFileDialog, QMessageBox,
    QListWidget, QListWidgetItem, QScrollArea, QStatusBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)

from config import AppConfig
from tool_scanner import scan_all, get_app_dir
from m3u8_parser import M3U8Parser, M3U8ParseResult, VideoStream, AudioTrack, SubtitleStream
from media_parser import detect_format, format_label, parse_media, parse_file
from download_thread import DownloadThread, LOG_INFO, LOG_SUCCESS, LOG_WARNING, LOG_ERROR
from styles import DARK_QSS


APP_NAME = "M3U8/MPD视频下载助手"
APP_VERSION = "1.0.0"

# 日志颜色
LOG_COLORS = {
    LOG_INFO: "#4a9eff",      # 蓝色 - 执行
    LOG_SUCCESS: "#22c55e",   # 绿色 - 成功
    LOG_WARNING: "#eab308",   # 黄色 - 警告
    LOG_ERROR: "#ef4444",     # 红色 - 错误
}


# ══════════════════════════════════════════════════════
# 工具版本检测
# ══════════════════════════════════════════════════════

def _run_quiet(cmd: list[str], timeout: int = 5) -> str:
    """静默运行子进程(无黑窗)，返回输出。"""
    creationflags = 0x08000000 if sys.platform == "win32" else 0
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            creationflags=creationflags, startupinfo=startupinfo,
        )
        return (result.stdout or "") + (result.stderr or "")
    except Exception:
        return ""


def detect_n_m3u8dl_version(exe: str) -> str:
    out = _run_quiet([exe, "--version"])
    m = re.search(r'(\d+\.\d+\.\d+)', out)
    return f"v{m.group(1)}" if m else "未知版本"


def detect_mp4decrypt_version(exe: str) -> str:
    out = _run_quiet([exe])
    m = re.search(r'(\d+\.\d+\.\d+)', out)
    return f"v{m.group(1)}" if m else "未知版本"


def detect_ffmpeg_version(exe: str) -> str:
    out = _run_quiet([exe, "-version"])
    m = re.search(r'ffmpeg version (\S+)', out)
    return f"ffmpeg-{m.group(1)}" if m else "未知版本"


# ══════════════════════════════════════════════════════
# 工具卡片
# ══════════════════════════════════════════════════════

class ToolCard(QFrame):
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("toolCard")
        self._ok = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        self.icon_label = QLabel("●")
        self.icon_label.setFixedSize(20, 20)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("font-size: 16px; color: #555566;")
        layout.addWidget(self.icon_label)

        info = QVBoxLayout()
        info.setSpacing(2)
        self.name_label = QLabel(name)
        self.name_label.setObjectName("toolCardName")
        self.version_label = QLabel("版本: 未检测")
        self.version_label.setObjectName("toolCardVersion")
        self.status_label = QLabel("状态: 未找到")
        self.status_label.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold;")
        info.addWidget(self.name_label)
        info.addWidget(self.version_label)
        info.addWidget(self.status_label)
        layout.addLayout(info, 1)

    def set_found(self, version: str = ""):
        self._ok = True
        self.icon_label.setStyleSheet("font-size: 16px; color: #22c55e;")
        self.icon_label.setText("✓")
        self.version_label.setText(f"版本: {version}" if version else "版本: 已检测")
        self.status_label.setText("状态: 正常")
        self.status_label.setStyleSheet("color: #22c55e; font-size: 11px; font-weight: bold;")

    def set_not_found(self):
        self._ok = False
        self.icon_label.setStyleSheet("font-size: 16px; color: #ef4444;")
        self.icon_label.setText("✗")
        self.version_label.setText("版本: 未检测")
        self.status_label.setText("状态: 未找到")
        self.status_label.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold;")

    @property
    def is_ok(self) -> bool:
        return self._ok


# ══════════════════════════════════════════════════════
# 支持拖拽的输入框
# ══════════════════════════════════════════════════════

class DropLineEdit(QLineEdit):
    """支持拖拽文件和URL文本的输入框。"""
    files_dropped = Signal(list)  # 拖入文件路径列表
    text_dropped = Signal(str)    # 拖入纯文本

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        md = event.mimeData()
        if md.hasUrls():
            files = [u.toLocalFile() for u in md.urls() if u.toLocalFile()]
            if files:
                self.files_dropped.emit(files)
                # 第一个文件填入输入框
                self.setText(files[0])
                event.acceptProposedAction()
                return
        if md.hasText():
            text = md.text().strip()
            if text:
                self.text_dropped.emit(text)
                self.setText(text)
                event.acceptProposedAction()
                return
        event.ignore()


# ══════════════════════════════════════════════════════
# 主窗口
# ══════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = AppConfig.load()
        self.parse_result: M3U8ParseResult | None = None
        self._current_format: str = "hls"
        self.download_thread: DownloadThread | None = None
        # 多任务调度
        self._task_queue: list[int] = []       # 待下载任务索引队列
        self._current_task_idx: int | None = None  # 当前正在下载的任务索引
        self._batch_mode: bool = False         # 是否批量下载模式

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1280, 820)
        self.setMinimumSize(1024, 680)

        self._build_ui()
        self._log(LOG_INFO, "=" * 20)
        self._log(LOG_INFO, f"{APP_NAME}")
        self._log(LOG_INFO, f"Version {APP_VERSION}")
        self._log(LOG_INFO, "=" * 20)
        self._log(LOG_INFO, "工具检测开始...")
        self._scan_tools()
        self._load_config_to_ui()

    # ══════════════════════════════════════════════
    # 构建 UI
    # ══════════════════════════════════════════════

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._build_sidebar())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sw = QWidget()
        self._main_layout = QVBoxLayout(sw)
        self._main_layout.setContentsMargins(16, 12, 16, 12)
        self._main_layout.setSpacing(0)

        self._build_task_list()
        self._build_basic_settings()
        self._build_video_options()
        self._build_save_settings()
        self._build_advanced_settings()
        self._build_log_output()

        self._main_layout.addStretch(1)
        scroll.setWidget(sw)
        main_layout.addWidget(scroll, 1)

        self._build_statusbar()

    # ── 左侧栏 ──

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._section_title("工具检测"))
        self.tool_n_m3u8dl = ToolCard("N_m3u8DL-RE(6).exe")
        self.tool_mp4decrypt = ToolCard("mp4decrypt.exe")
        self.tool_ffmpeg = ToolCard("ffmpeg.exe")
        layout.addWidget(self.tool_n_m3u8dl)
        layout.addWidget(self.tool_mp4decrypt)
        layout.addWidget(self.tool_ffmpeg)
        layout.addSpacing(12)

        layout.addWidget(self._section_title("任务控制"))
        tw = QWidget()
        tl = QVBoxLayout(tw)
        tl.setContentsMargins(16, 4, 16, 4)
        tl.setSpacing(6)

        def info_row(label_text: str) -> tuple[QHBoxLayout, QLabel]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label_text))
            val = QLabel("0 B/s" if "速度" in label_text else
                         "0 B / 0 B" if "已下载" in label_text else
                         "0.00%" if "进度" in label_text else
                         "--:--:--" if "剩余" in label_text else "空闲中")
            val.setObjectName("taskInfoValue")
            row.addWidget(val, 1)
            return row, val

        row, self.lbl_task_status = info_row("任务状态:")
        self.lbl_task_status.setObjectName("taskStatusIdle")
        self.lbl_task_status.setStyleSheet("color: #22c55e; font-size: 13px; font-weight: bold;")
        tl.addLayout(row)

        row, self.lbl_speed = info_row("当前速度:")
        tl.addLayout(row)

        row, self.lbl_downloaded = info_row("已下载:")
        tl.addLayout(row)

        row, self.lbl_progress = info_row("进度:")
        tl.addLayout(row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        tl.addWidget(self.progress_bar)

        row, self.lbl_remaining = info_row("剩余时间:")
        tl.addLayout(row)

        layout.addWidget(tw)
        layout.addSpacing(8)

        # 操作按钮
        bw = QWidget()
        bl = QVBoxLayout(bw)
        bl.setContentsMargins(12, 0, 12, 0)
        bl.setSpacing(6)
        self.btn_start = QPushButton("▶  开始下载")
        self.btn_start.setObjectName("btnStart")
        self.btn_start.clicked.connect(self._on_start)
        bl.addWidget(self.btn_start)
        self.btn_stop = QPushButton("■  停止任务")
        self.btn_stop.setObjectName("btnStop")
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.setEnabled(False)
        bl.addWidget(self.btn_stop)
        layout.addWidget(bw)
        layout.addSpacing(6)

        dw = QWidget()
        dl = QVBoxLayout(dw)
        dl.setContentsMargins(12, 0, 12, 0)
        dl.setSpacing(6)
        self.btn_open_save = QPushButton("📂  打开保存目录")
        self.btn_open_save.clicked.connect(self._on_open_save_dir)
        dl.addWidget(self.btn_open_save)
        self.btn_open_temp = QPushButton("📂  打开临时目录")
        self.btn_open_temp.clicked.connect(self._on_open_temp_dir)
        dl.addWidget(self.btn_open_temp)
        layout.addWidget(dw)
        layout.addStretch(1)

        # 底部导航
        nw = QWidget()
        nl = QHBoxLayout(nw)
        nl.setContentsMargins(12, 8, 12, 12)
        nl.setSpacing(4)
        for text, handler in [("⚙ 设置", self._on_save_config),
                              ("📋 日志", lambda: None),
                              ("ℹ 关于", self._on_about)]:
            btn = QPushButton(text)
            btn.setObjectName("btnNav")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(handler)
            nl.addWidget(btn)
        layout.addWidget(nw)
        return sidebar

    @staticmethod
    def _section_title(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sidebarTitle")
        return lbl

    # ── 任务列表 ──

    # 状态颜色映射
    STATUS_COLORS = {
        "待解析": "#eab308",   # 黄色
        "解析中": "#3b82f6",   # 蓝色
        "就绪": "#94a3b8",     # 灰色
        "等待": "#eab308",     # 黄色
        "下载中": "#3b82f6",   # 蓝色
        "已暂停": "#f59e0b",   # 橙色
        "已完成": "#22c55e",   # 绿色
        "解析失败": "#ef4444", # 红色
        "失败": "#ef4444",     # 红色
    }

    def _build_task_list(self):
        group = QGroupBox("下载任务列表（拖入 .m3u8 / .mpd / .txt 自动加入）")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 20, 12, 8)
        layout.setSpacing(6)

        self.task_table = QTableWidget(0, 8)
        self.task_table.setHorizontalHeaderLabels(
            ["文件名", "类型", "清晰度", "音轨", "字幕", "状态", "进度", "操作"])
        hdr = self.task_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)        # 文件名
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # 类型
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # 清晰度
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # 音轨
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # 字幕
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # 状态
        hdr.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # 进度
        hdr.setSectionResizeMode(7, QHeaderView.ResizeToContents)  # 操作
        self.task_table.verticalHeader().setVisible(False)
        self.task_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.task_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.task_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.task_table.setFixedHeight(160)
        self.task_table.cellDoubleClicked.connect(self._on_task_double_clicked)
        layout.addWidget(self.task_table)

        # 批量操作按钮
        btn_row = QHBoxLayout()
        self.btn_start_all = QPushButton("开始全部任务")
        self.btn_start_all.setFixedWidth(100)
        self.btn_start_all.setStyleSheet("background:#3b82f6;color:white;font-weight:bold;")
        self.btn_start_all.clicked.connect(self._on_start_all)
        self.btn_start_sel = QPushButton("开始选中任务")
        self.btn_start_sel.setFixedWidth(100)
        self.btn_start_sel.clicked.connect(self._on_start_selected)
        self.btn_pause_all = QPushButton("暂停全部")
        self.btn_pause_all.setFixedWidth(80)
        self.btn_pause_all.setStyleSheet("background:#f59e0b;color:white;")
        self.btn_pause_all.clicked.connect(self._on_pause_all)
        self.btn_del_sel = QPushButton("删除选中")
        self.btn_del_sel.setFixedWidth(80)
        self.btn_del_sel.setStyleSheet("color:#ef4444;")
        self.btn_del_sel.clicked.connect(self._on_remove_task)
        self.btn_clear_done = QPushButton("清除完成任务")
        self.btn_clear_done.setFixedWidth(100)
        self.btn_clear_done.clicked.connect(self._on_clear_completed)
        btn_row.addWidget(self.btn_start_all)
        btn_row.addWidget(self.btn_start_sel)
        btn_row.addWidget(self.btn_pause_all)
        btn_row.addWidget(self.btn_del_sel)
        btn_row.addWidget(self.btn_clear_done)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self._main_layout.addWidget(group)
        self._tasks: list[dict] = []

    def _make_task_op_widget(self, row: int) -> QWidget:
        """创建任务行操作按钮（删除/暂停/重试）。"""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 0, 2, 0)
        h.setSpacing(2)

        btn_del = QPushButton("删除")
        btn_del.setFixedWidth(40)
        btn_del.setStyleSheet("color:#ef4444;font-size:11px;")
        btn_del.clicked.connect(lambda _=False, r=row: self._on_delete_task(r))

        btn_pause = QPushButton("暂停")
        btn_pause.setFixedWidth(40)
        btn_pause.setStyleSheet("color:#f59e0b;font-size:11px;")
        btn_pause.clicked.connect(lambda _=False, r=row: self._on_pause_task(r))

        btn_retry = QPushButton("重试")
        btn_retry.setFixedWidth(40)
        btn_retry.setStyleSheet("color:#3b82f6;font-size:11px;")
        btn_retry.clicked.connect(lambda _=False, r=row: self._on_retry_task(r))

        h.addWidget(btn_del)
        h.addWidget(btn_pause)
        h.addWidget(btn_retry)
        return w

    def _on_files_dropped(self, files: list[str]):
        """拖入文件：逐个解析并加入任务列表（支持批量）。"""
        self._log(LOG_INFO, f"拖入 {len(files)} 个文件，开始批量解析...")
        for fpath in files:
            self._add_task_from_file(fpath)

    def _on_text_dropped(self, text: str):
        """拖入URL文本：解析并加入任务列表。"""
        if text.startswith("http"):
            self._add_task_from_url(text)
        else:
            if Path(text).is_file():
                self._add_task_from_file(text)

    def _add_task_from_file(self, filepath: str):
        """从本地文件添加任务。"""
        p = Path(filepath)
        ext = p.suffix.lower()
        if ext not in (".m3u8", ".mpd", ".txt"):
            self._log(LOG_WARNING, f"不支持的文件类型: {p.name}")
            return
        fmt = detect_format(p.name)
        if fmt == "unknown" and ext == ".txt":
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                fmt = detect_format(content)
            except Exception:
                fmt = "unknown"
        task = {
            "url": filepath,
            "format": fmt,
            "filename": p.name,
            "status": "待解析",
            "progress": 0,
            "parse_result": None,
            "quality": "-",
            "audio": "-",
            "subtitle": "-",
        }
        self._tasks.append(task)
        self._refresh_task_table()
        self._log(LOG_INFO, f"已加入任务: {p.name} ({format_label(fmt)})")
        self._parse_task(task)

    def _add_task_from_url(self, url: str):
        """从URL添加任务。"""
        fmt = detect_format(url)
        name = url.split("/")[-1].split("?")[0] or url
        task = {
            "url": url,
            "format": fmt,
            "filename": name,
            "status": "待解析",
            "progress": 0,
            "parse_result": None,
            "quality": "-",
            "audio": "-",
            "subtitle": "-",
        }
        self._tasks.append(task)
        self._refresh_task_table()
        self._log(LOG_INFO, f"已加入任务: {name} ({format_label(fmt)})")
        self._parse_task(task)

    def _parse_task(self, task: dict):
        """解析单个任务，填充清晰度/音轨/字幕信息并显示日志。"""
        try:
            task["status"] = "解析中"
            self._refresh_task_table()
            cookie = self.input_cookie.toPlainText().strip()
            headers = {}
            if Path(task["url"]).is_file():
                fmt, result = parse_file(task["url"], cookie=cookie, headers=headers)
            else:
                fmt, result = parse_media(task["url"], cookie=cookie, headers=headers)
            task["format"] = fmt
            task["parse_result"] = result
            task["status"] = "就绪"

            # 填充摘要列
            if result.videos:
                best = result.best_video()
                task["quality"] = best.quality_label() if best else "-"
            else:
                task["quality"] = "无"
            if result.audios:
                task["audio"] = ", ".join(
                    (a.language_category() if hasattr(a, 'language_category') else (a.name or a.language or "?"))
                    for a in result.audios[:2]
                )
            else:
                task["audio"] = "无"
            task["subtitle"] = f"{len(result.subtitles)}条" if result.subtitles else "无"

            # 日志
            vinfo = ", ".join(f"{v.width}x{v.height}" for v in result.videos[:3])
            ainfo = ", ".join((a.name or a.language or "?") for a in result.audios[:3])
            sinfo = f"{len(result.subtitles)}条字幕" if result.subtitles else "无字幕"
            self._log(LOG_INFO, f"[{task['filename']}] 检测类型: {format_label(fmt)}")
            self._log(LOG_INFO, f"[{task['filename']}] 解析: 视频:{vinfo or '无'} 音频:{ainfo or '无'} 字幕:{sinfo}")
        except Exception as e:
            task["status"] = "解析失败"
            task["quality"] = "-"
            task["audio"] = "-"
            task["subtitle"] = "-"
            self._log(LOG_ERROR, f"[{task['filename']}] 解析失败: {e}")
        self._refresh_task_table()

    def _refresh_task_table(self):
        """刷新任务列表显示（含状态颜色和操作按钮）。"""
        self.task_table.setRowCount(len(self._tasks))
        for i, task in enumerate(self._tasks):
            # 文件名
            self.task_table.setItem(i, 0, QTableWidgetItem(task["filename"]))
            # 类型
            self.task_table.setItem(i, 1, QTableWidgetItem(format_label(task["format"])))
            # 清晰度
            self.task_table.setItem(i, 2, QTableWidgetItem(str(task.get("quality", "-"))))
            # 音轨
            self.task_table.setItem(i, 3, QTableWidgetItem(str(task.get("audio", "-"))))
            # 字幕
            self.task_table.setItem(i, 4, QTableWidgetItem(str(task.get("subtitle", "-"))))
            # 状态（带颜色）
            status_item = QTableWidgetItem(task["status"])
            color = self.STATUS_COLORS.get(task["status"], "#e0e0e8")
            status_item.setForeground(QColor(color))
            self.task_table.setItem(i, 5, status_item)
            # 进度
            prog = task.get("progress", 0)
            self.task_table.setItem(i, 6, QTableWidgetItem(f"{prog}%"))
            # 操作按钮
            self.task_table.setCellWidget(i, 7, self._make_task_op_widget(i))

    def _on_task_double_clicked(self, row: int, col: int):
        """双击任务：加载到主界面。"""
        if 0 <= row < len(self._tasks):
            task = self._tasks[row]
            self.input_url.setText(task["url"])
            self._log(LOG_INFO, f"已加载任务: {task['filename']}")
            if task["parse_result"]:
                self._populate_video_tracks(task["parse_result"])
                self._populate_audio_tracks(task["parse_result"])

    def _on_delete_task(self, row: int):
        """删除指定任务。"""
        if 0 <= row < len(self._tasks):
            # 如果是当前下载任务，先停止
            if self._current_task_idx == row:
                if self.download_thread and self.download_thread.isRunning():
                    self.download_thread.stop()
                self._current_task_idx = None
            removed = self._tasks.pop(row)
            # 调整队列中的索引
            self._task_queue = [
                (idx if idx < row else idx - 1) for idx in self._task_queue if idx != row
            ]
            self._refresh_task_table()
            self._log(LOG_INFO, f"已删除任务: {removed['filename']}")

    def _on_pause_task(self, row: int):
        """暂停指定任务。"""
        if 0 <= row < len(self._tasks):
            task = self._tasks[row]
            if self._current_task_idx == row and self.download_thread and self.download_thread.isRunning():
                self.download_thread.stop()
                task["status"] = "已暂停"
                self._log(LOG_WARNING, f"已暂停任务: {task['filename']}")
            elif task["status"] == "等待":
                # 从队列中移除
                self._task_queue = [idx for idx in self._task_queue if idx != row]
                task["status"] = "就绪"
                self._log(LOG_INFO, f"已取消等待: {task['filename']}")
            self._refresh_task_table()

    def _on_retry_task(self, row: int):
        """重试失败/已暂停的任务。"""
        if 0 <= row < len(self._tasks):
            task = self._tasks[row]
            if task["status"] in ("失败", "解析失败", "已暂停", "就绪"):
                task["status"] = "等待"
                task["progress"] = 0
                self._task_queue.append(row)
                self._refresh_task_table()
                self._log(LOG_INFO, f"已加入重试队列: {task['filename']}")
                if not self.download_thread or not self.download_thread.isRunning():
                    self._start_next_task()

    def _on_remove_task(self):
        """移除选中任务（兼容旧按钮）。"""
        row = self.task_table.currentRow()
        if row >= 0:
            self._on_delete_task(row)

    def _on_clear_tasks(self):
        """清空列表（兼容旧按钮）。"""
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.stop()
        self._tasks.clear()
        self._task_queue.clear()
        self._current_task_idx = None
        self._refresh_task_table()
        self._log(LOG_INFO, "已清空任务列表")

    def _on_clear_completed(self):
        """清除所有已完成任务。"""
        before = len(self._tasks)
        self._tasks = [t for t in self._tasks if t["status"] != "已完成"]
        # 重建队列索引（因为删除会改变索引）
        self._task_queue = []
        self._refresh_task_table()
        self._log(LOG_INFO, f"已清除 {before - len(self._tasks)} 个已完成任务")

    # ── 多任务调度 ──

    def _on_start_all(self):
        """开始全部就绪任务。"""
        ready = [i for i, t in enumerate(self._tasks)
                 if t["status"] in ("就绪", "已暂停", "失败", "解析失败")]
        if not ready:
            QMessageBox.information(self, "提示", "没有可开始的任务")
            return
        if self.download_thread and self.download_thread.isRunning():
            QMessageBox.information(self, "提示", "已有任务正在下载，请先暂停")
            return
        self._batch_mode = True
        self._task_queue = list(ready)
        for idx in ready:
            self._tasks[idx]["status"] = "等待"
            self._tasks[idx]["progress"] = 0
        self._refresh_task_table()
        self._log(LOG_INFO, f"开始批量下载，共 {len(ready)} 个任务")
        self._start_next_task()

    def _on_start_selected(self):
        """开始当前选中的任务。"""
        row = self.task_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一个任务")
            return
        task = self._tasks[row]
        if task["status"] not in ("就绪", "已暂停", "失败", "解析失败"):
            QMessageBox.information(self, "提示", f"当前任务状态为「{task['status']}」，无法开始")
            return
        if self.download_thread and self.download_thread.isRunning():
            QMessageBox.information(self, "提示", "已有任务正在下载，请先暂停")
            return
        self._batch_mode = False
        self._task_queue = [row]
        task["status"] = "等待"
        task["progress"] = 0
        self._refresh_task_table()
        self._log(LOG_INFO, f"开始选中任务: {task['filename']}")
        self._start_next_task()

    def _on_pause_all(self):
        """暂停全部任务。"""
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.stop()
            self._log(LOG_WARNING, "正在停止当前任务...")
        # 清空等待队列
        for idx in self._task_queue:
            if 0 <= idx < len(self._tasks):
                self._tasks[idx]["status"] = "就绪"
        self._task_queue.clear()
        self._batch_mode = False
        self._refresh_task_table()
        self._log(LOG_INFO, "已暂停全部任务")

    def _start_next_task(self):
        """从队列中取出下一个任务并开始下载。"""
        if not self._task_queue:
            self._batch_mode = False
            self._log(LOG_INFO, "所有任务已处理完毕")
            return
        idx = self._task_queue.pop(0)
        if idx >= len(self._tasks):
            self._start_next_task()
            return
        task = self._tasks[idx]
        self._current_task_idx = idx
        task["status"] = "下载中"
        self._refresh_task_table()

        # 加载任务URL到输入框（用于config收集）
        self.input_url.setText(task["url"])
        self.config = self._collect_config_from_ui()

        # 校验
        if not self.config.tool_paths.get("n_m3u8dl"):
            task["status"] = "失败"
            self._log(LOG_ERROR, f"[{task['filename']}] 未找到 N_m3u8DL-RE")
            self._refresh_task_table()
            self._start_next_task()
            return
        if not self.config.save_dir:
            task["status"] = "失败"
            self._log(LOG_ERROR, f"[{task['filename']}] 未设置保存目录")
            self._refresh_task_table()
            self._start_next_task()
            return

        Path(self.config.save_dir).mkdir(parents=True, exist_ok=True)

        # 解析（使用缓存或重新解析）
        result = task.get("parse_result")
        if result is None:
            try:
                if Path(task["url"]).is_file():
                    _, result = parse_file(task["url"], cookie=self.config.effective_cookie(),
                                           headers=self.config.build_headers_dict())
                else:
                    _, result = parse_media(task["url"], cookie=self.config.effective_cookie(),
                                            headers=self.config.build_headers_dict())
                task["parse_result"] = result
            except Exception as e:
                task["status"] = "解析失败"
                self._log(LOG_ERROR, f"[{task['filename']}] 解析失败: {e}")
                self._refresh_task_table()
                self._start_next_task()
                return

        # 选择视频/音频/字幕（使用自动最佳）
        selected_video = result.best_video()
        selected_audio = result.default_audio()
        selected_subs = [result.default_subtitle()] if result.default_subtitle() else []

        self._log(LOG_INFO, f"[{task['filename']}] 开始下载...")
        if selected_video:
            self._log(LOG_INFO, f"  视频: {selected_video.quality_label()}")
        if selected_audio:
            self._log(LOG_INFO, f"  音频: {selected_audio.display_name()}")

        # 如果文件名未设置，用任务名
        if not self.config.filename:
            self.config.filename = Path(task["filename"]).stem + ".mp4"

        self.config.save()

        self.download_thread = DownloadThread(
            config=self.config,
            parse_result=result,
            selected_video=selected_video,
            selected_audio=selected_audio,
            selected_subtitles=selected_subs,
        )
        self.download_thread.log.connect(self._on_log)
        self.download_thread.progress.connect(lambda p, i=idx: self._on_task_progress(i, p))
        self.download_thread.speed.connect(self._on_speed)
        self.download_thread.size.connect(self._on_size)
        self.download_thread.eta.connect(self._on_eta)
        self.download_thread.finished_ok.connect(
            lambda path, i=idx: self._on_task_finished_ok(i, path))
        self.download_thread.failed.connect(
            lambda err, i=idx: self._on_task_failed(i, err))

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._set_task_status("下载中", "#3b82f6")
        self.lbl_threads.setText(f"{len(self._task_queue) + 1}/{len(self._task_queue) + 1}")
        self.download_thread.start()

    def _on_task_progress(self, idx: int, pct: int):
        """任务进度更新（同步到任务列表和全局进度条）。"""
        if 0 <= idx < len(self._tasks):
            self._tasks[idx]["progress"] = pct
            self._refresh_task_table()
        self.progress_bar.setValue(pct)
        self.status_progress.setValue(pct)
        self.lbl_progress.setText(f"{pct:.2f}%")
        self.lbl_total_progress.setText(f"{pct:.2f}%")

    def _on_task_finished_ok(self, idx: int, output_path: str):
        """单个任务下载完成。"""
        if 0 <= idx < len(self._tasks):
            self._tasks[idx]["status"] = "已完成"
            self._tasks[idx]["progress"] = 100
            self._refresh_task_table()
        self._log(LOG_SUCCESS, f"[{self._tasks[idx]['filename'] if 0 <= idx < len(self._tasks) else '任务'}] 下载完成: {output_path}")
        self._current_task_idx = None

        if self.chk_open_after.isChecked():
            self._open_in_explorer(output_path)

        # 继续下一个
        if self._task_queue:
            self._start_next_task()
        else:
            self._batch_mode = False
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)
            self._set_task_status("已完成", "#22c55e")
            self.lbl_threads.setText("0/0")
            self.progress_bar.setValue(100)
            self.status_progress.setValue(100)
            self.lbl_status_left.setText("完成")
            self._log(LOG_SUCCESS, "全部任务下载完成!")

    def _on_task_failed(self, idx: int, error: str):
        """单个任务下载失败。"""
        if 0 <= idx < len(self._tasks):
            self._tasks[idx]["status"] = "失败"
            self._refresh_task_table()
        self._log(LOG_ERROR, f"[{self._tasks[idx]['filename'] if 0 <= idx < len(self._tasks) else '任务'}] 下载失败: {error}")
        self._current_task_idx = None

        # 继续下一个
        if self._task_queue:
            self._start_next_task()
        else:
            self._batch_mode = False
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)
            self._set_task_status("失败", "#ef4444")
            self.lbl_threads.setText("0/0")
            self.lbl_status_left.setText("失败")

    # ── 基础设置 ──

    def _build_basic_settings(self):
        group = QGroupBox("基础设置")
        layout = QGridLayout(group)
        layout.setContentsMargins(12, 20, 12, 12)
        layout.setSpacing(8)

        layout.addWidget(QLabel("视频地址(M3U8/MPD):"), 0, 0)
        self.input_url = DropLineEdit()
        self.input_url.setPlaceholderText("拖入 .m3u8 / .mpd / .txt 文件或粘贴URL...")
        self.input_url.files_dropped.connect(self._on_files_dropped)
        self.input_url.text_dropped.connect(self._on_text_dropped)
        layout.addWidget(self.input_url, 0, 1)
        self.btn_paste = QPushButton("粘贴")
        self.btn_paste.setFixedWidth(60)
        self.btn_paste.clicked.connect(self._on_paste_url)
        layout.addWidget(self.btn_paste, 0, 2)

        layout.addWidget(QLabel("Cookie:"), 1, 0)
        self.input_cookie = QTextEdit()
        self.input_cookie.setPlaceholderText("可选，支持多行")
        self.input_cookie.setFixedHeight(48)
        layout.addWidget(self.input_cookie, 1, 1, 1, 2)

        layout.addWidget(QLabel("Headers:"), 2, 0)
        self.input_headers = QTextEdit()
        self.input_headers.setPlaceholderText("可选，格式: Key: Value，每行一个")
        self.input_headers.setFixedHeight(48)
        layout.addWidget(self.input_headers, 2, 1)
        self.btn_edit_headers = QPushButton("编辑")
        self.btn_edit_headers.setFixedWidth(60)
        self.btn_edit_headers.clicked.connect(lambda: self.input_headers.setFocus())
        layout.addWidget(self.btn_edit_headers, 2, 2)

        layout.setColumnStretch(1, 1)
        self._main_layout.addWidget(group)

    # ── 视频选项 ──

    def _build_video_options(self):
        group = QGroupBox("视频选项")
        layout = QHBoxLayout(group)
        layout.setContentsMargins(12, 20, 12, 12)
        layout.setSpacing(10)

        # 清晰度
        qc = QVBoxLayout()
        qc.setSpacing(6)
        qc.addWidget(QLabel("清晰度选择"))
        self.combo_quality = QComboBox()
        self.combo_quality.addItems(["自动最佳", "4K (2160P)", "1080P", "720P", "480P", "360P"])
        qc.addWidget(self.combo_quality)
        self.list_quality = QListWidget()
        self.list_quality.addItems(["自动最佳", "4K (2160P)", "1080P", "720P", "480P", "360P"])
        self.list_quality.setCurrentRow(0)
        self.list_quality.setFixedHeight(160)
        self.list_quality.currentRowChanged.connect(self._on_quality_selected)
        qc.addWidget(self.list_quality)
        layout.addLayout(qc, 1)

        # 视频轨道
        vc = QVBoxLayout()
        vc.setSpacing(6)
        vc.addWidget(QLabel("视频轨道"))
        self.combo_video_track = QComboBox()
        self.combo_video_track.addItem("自动选择")
        vc.addWidget(self.combo_video_track)
        self.list_video_track = QListWidget()
        self.list_video_track.addItem("自动选择")
        self.list_video_track.setCurrentRow(0)
        self.list_video_track.setFixedHeight(160)
        vc.addWidget(self.list_video_track)
        # 同步下拉框和列表选择
        self.combo_video_track.currentIndexChanged.connect(
            lambda i: self.list_video_track.setCurrentRow(i) if i < self.list_video_track.count() else None)
        self.list_video_track.currentRowChanged.connect(
            lambda r: self.combo_video_track.setCurrentIndex(r) if 0 <= r < self.combo_video_track.count() else None)
        layout.addLayout(vc, 1)

        # 音频轨道
        ac = QVBoxLayout()
        ac.setSpacing(6)
        ac.addWidget(QLabel("音频轨道"))
        self.list_audio = QListWidget()
        self.list_audio.setSelectionMode(QListWidget.NoSelection)
        self.list_audio.setFixedHeight(160)
        self._add_audio_item("音频轨道", True)
        self._add_audio_item("自动最佳", True)
        ac.addWidget(self.list_audio)
        layout.addLayout(ac, 1)

        # 字幕
        sc = QVBoxLayout()
        sc.setSpacing(6)
        self.chk_download_sub = QCheckBox("下载外挂字幕")
        self.chk_download_sub.setChecked(True)
        sc.addWidget(self.chk_download_sub)
        sc.addWidget(QLabel("字幕语言"))
        self.chk_sub_zh = QCheckBox("简体中文")
        self.chk_sub_zh.setChecked(True)
        self.chk_sub_zht = QCheckBox("繁体中文")
        self.chk_sub_en = QCheckBox("English")
        self.chk_sub_ja = QCheckBox("日本語")
        self.chk_sub_other = QCheckBox("其他语言")
        for cb in [self.chk_sub_zh, self.chk_sub_zht, self.chk_sub_en,
                   self.chk_sub_ja, self.chk_sub_other]:
            sc.addWidget(cb)
        sc.addWidget(QLabel("字幕格式"))
        sf = QHBoxLayout()
        self.radio_srt = QRadioButton("SRT")
        self.radio_vtt = QRadioButton("VTT")
        self.radio_ass = QRadioButton("ASS")
        self.radio_srt.setChecked(True)
        self.sub_fmt_group = QButtonGroup(self)
        self.sub_fmt_group.addButton(self.radio_srt)
        self.sub_fmt_group.addButton(self.radio_vtt)
        self.sub_fmt_group.addButton(self.radio_ass)
        sf.addWidget(self.radio_srt)
        sf.addWidget(self.radio_vtt)
        sf.addWidget(self.radio_ass)
        sf.addStretch(1)
        sc.addLayout(sf)
        sc.addStretch(1)
        layout.addLayout(sc, 1)

        self._main_layout.addWidget(group)

    # ── 保存设置 ──

    def _build_save_settings(self):
        group = QGroupBox("保存设置")
        layout = QGridLayout(group)
        layout.setContentsMargins(12, 20, 12, 12)
        layout.setSpacing(8)

        layout.addWidget(QLabel("保存目录:"), 0, 0)
        self.input_save_dir = QLineEdit()
        self.input_save_dir.setPlaceholderText("选择保存目录")
        layout.addWidget(self.input_save_dir, 0, 1)
        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.setFixedWidth(80)
        self.btn_browse.clicked.connect(self._on_browse_dir)
        layout.addWidget(self.btn_browse, 0, 2)
        self.btn_save_as = QPushButton("另存为...")
        self.btn_save_as.setFixedWidth(80)
        self.btn_save_as.clicked.connect(self._on_save_as)
        layout.addWidget(self.btn_save_as, 0, 3)

        layout.addWidget(QLabel("文件名:"), 1, 0)
        self.input_filename = QLineEdit()
        self.input_filename.setPlaceholderText("输入文件名(支持中文)")
        layout.addWidget(self.input_filename, 1, 1)
        layout.addWidget(QLabel("输出格式:"), 1, 2)
        self.combo_output_format = QComboBox()
        self.combo_output_format.addItems(["MP4", "MKV", "TS"])
        self.combo_output_format.setFixedWidth(80)
        layout.addWidget(self.combo_output_format, 1, 3)

        self.chk_open_after = QCheckBox("任务完成后打开目录")
        layout.addWidget(self.chk_open_after, 2, 1)

        layout.setColumnStretch(1, 1)
        self._main_layout.addWidget(group)

    # ── 高级设置 ──

    def _build_advanced_settings(self):
        group = QGroupBox("高级设置（可选）")
        layout = QHBoxLayout(group)
        layout.setContentsMargins(12, 20, 12, 12)
        layout.setSpacing(16)

        # 加密
        ec = QVBoxLayout()
        ec.setSpacing(8)
        ec.addWidget(QLabel("加密设置"))
        ef = QGridLayout()
        ef.setSpacing(6)
        ef.addWidget(QLabel("加密类型:"), 0, 0)
        self.combo_enc_type = QComboBox()
        self.combo_enc_type.addItems(["自动检测", "AES-128", "CENC", "SAMPLE-AES"])
        ef.addWidget(self.combo_enc_type, 0, 1)
        ef.addWidget(QLabel("Key (KID:KEY):"), 1, 0)
        self.input_key = QLineEdit()
        self.input_key.setPlaceholderText("可直接输入KID:KEY")
        ef.addWidget(self.input_key, 1, 1)
        ef.addWidget(QLabel("Key文件:"), 2, 0)
        self.input_key_file = QLineEdit()
        self.input_key_file.setPlaceholderText("选择key.txt文件")
        ef.addWidget(self.input_key_file, 2, 1)
        self.btn_key_file = QPushButton("选择文件")
        self.btn_key_file.setFixedWidth(70)
        self.btn_key_file.clicked.connect(self._on_select_key_file)
        ef.addWidget(self.btn_key_file, 2, 2)
        ef.addWidget(QLabel("解密工具:"), 3, 0)
        self.combo_decrypt_tool = QComboBox()
        self.combo_decrypt_tool.addItems(["mp4decrypt.exe (自动)", "N_m3u8DL-RE 内置", "不解密"])
        ef.addWidget(self.combo_decrypt_tool, 3, 1)
        ef.setColumnStretch(1, 1)
        ec.addLayout(ef)
        ec.addStretch(1)
        layout.addLayout(ec, 1)

        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setStyleSheet("color: #2a2a3a;")
        layout.addWidget(line)

        # 请求头
        rc = QVBoxLayout()
        rc.setSpacing(8)
        rc.addWidget(QLabel("请求头设置"))
        rf = QGridLayout()
        rf.setSpacing(6)
        rf.addWidget(QLabel("User-Agent:"), 0, 0)
        self.input_ua = QLineEdit()
        self.input_ua.setPlaceholderText("Mozilla/5.0 ...")
        rf.addWidget(self.input_ua, 0, 1)
        rf.addWidget(QLabel("Referer:"), 1, 0)
        self.input_referer = QLineEdit()
        self.input_referer.setPlaceholderText("https://example.com/")
        rf.addWidget(self.input_referer, 1, 1)
        rf.addWidget(QLabel("Cookie:"), 2, 0)
        self.input_cookie_adv = QTextEdit()
        self.input_cookie_adv.setPlaceholderText("可选，支持多行")
        self.input_cookie_adv.setFixedHeight(40)
        rf.addWidget(self.input_cookie_adv, 2, 1)
        rf.addWidget(QLabel("其他Headers:"), 3, 0)
        self.input_headers_adv = QTextEdit()
        self.input_headers_adv.setPlaceholderText("可选，格式: Key: Value，每行一个")
        self.input_headers_adv.setFixedHeight(40)
        rf.addWidget(self.input_headers_adv, 3, 1)
        self.btn_edit_headers_adv = QPushButton("编辑")
        self.btn_edit_headers_adv.setFixedWidth(60)
        self.btn_edit_headers_adv.clicked.connect(lambda: self.input_headers_adv.setFocus())
        rf.addWidget(self.btn_edit_headers_adv, 3, 2)
        rf.setColumnStretch(1, 1)
        rc.addLayout(rf)

        br = QHBoxLayout()
        br.addStretch(1)
        self.btn_save_config = QPushButton("💾 保存配置")
        self.btn_save_config.clicked.connect(self._on_save_config)
        br.addWidget(self.btn_save_config)
        rc.addLayout(br)

        layout.addLayout(rc, 1)
        self._main_layout.addWidget(group)

    # ── 日志输出 (QTextEdit 彩色) ──

    def _build_log_output(self):
        group = QGroupBox("日志输出")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 20, 12, 12)
        layout.setSpacing(6)

        # 日志控制按钮
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(6)
        self.btn_clear_log = QPushButton("🗑 清空日志")
        self.btn_clear_log.setFixedWidth(100)
        self.btn_clear_log.clicked.connect(self._on_clear_log)
        btn_bar.addWidget(self.btn_clear_log)

        self.btn_copy_log = QPushButton("📋 复制日志")
        self.btn_copy_log.setFixedWidth(100)
        self.btn_copy_log.clicked.connect(self._on_copy_log)
        btn_bar.addWidget(self.btn_copy_log)

        self.btn_save_log = QPushButton("💾 保存日志")
        self.btn_save_log.setFixedWidth(100)
        self.btn_save_log.clicked.connect(self._on_save_log)
        btn_bar.addWidget(self.btn_save_log)

        btn_bar.addStretch(1)

        # 图例
        legend = QLabel()
        legend.setText(
            '<span style="color:#22c55e;">●成功</span> &nbsp; '
            '<span style="color:#eab308;">●警告</span> &nbsp; '
            '<span style="color:#ef4444;">●错误</span> &nbsp; '
            '<span style="color:#4a9eff;">●执行</span>'
        )
        legend.setStyleSheet("font-size: 11px;")
        btn_bar.addWidget(legend)

        layout.addLayout(btn_bar)

        # 彩色日志窗口
        self.log_output = QTextEdit()
        self.log_output.setObjectName("logOutput")
        self.log_output.setReadOnly(True)
        self.log_output.setFixedHeight(200)
        self.log_output.setFont(QFont("Consolas", 10))
        layout.addWidget(self.log_output)

        self._main_layout.addWidget(group)

    # ── 状态栏 ──

    def _build_statusbar(self):
        bar = QStatusBar()
        self.setStatusBar(bar)
        self.lbl_status_left = QLabel("就绪")
        bar.addWidget(self.lbl_status_left, 1)
        bar.addWidget(QLabel("当前线程:"))
        self.lbl_threads = QLabel("0/0")
        bar.addWidget(self.lbl_threads)
        bar.addWidget(QLabel("总进度:"))
        self.lbl_total_progress = QLabel("0.00%")
        bar.addWidget(self.lbl_total_progress)
        self.status_progress = QProgressBar()
        self.status_progress.setFixedWidth(150)
        self.status_progress.setFixedHeight(16)
        self.status_progress.setRange(0, 100)
        self.status_progress.setValue(0)
        bar.addWidget(self.status_progress)

    # ══════════════════════════════════════════════
    # 工具扫描
    # ══════════════════════════════════════════════

    def _scan_tools(self):
        self._log(LOG_INFO, "正在检测工具...")
        config_paths = self.config.tool_paths or {}
        tools = scan_all(config_paths)
        self.config.tool_paths = {k: v for k, v in tools.items() if v}

        missing = []

        if tools["n_m3u8dl"]:
            ver = detect_n_m3u8dl_version(tools["n_m3u8dl"])
            self.tool_n_m3u8dl.set_found(ver)
            self._log(LOG_SUCCESS, f"✓ N_m3u8DL-RE(6).exe 检测成功 ({ver})")
        else:
            self.tool_n_m3u8dl.set_not_found()
            self._log(LOG_ERROR, "✗ N_m3u8DL-RE(6).exe 未找到")
            missing.append(("n_m3u8dl", "N_m3u8DL-RE(6).exe", "N_m3u8DL-RE*.exe"))

        if tools["mp4decrypt"]:
            ver = detect_mp4decrypt_version(tools["mp4decrypt"])
            self.tool_mp4decrypt.set_found(ver)
            self._log(LOG_SUCCESS, f"✓ mp4decrypt.exe 检测成功 ({ver})")
        else:
            self.tool_mp4decrypt.set_not_found()
            self._log(LOG_WARNING, "✗ mp4decrypt.exe 未找到 (解密功能不可用)")
            missing.append(("mp4decrypt", "mp4decrypt.exe", "mp4decrypt.exe"))

        if tools["ffmpeg"]:
            ver = detect_ffmpeg_version(tools["ffmpeg"])
            self.tool_ffmpeg.set_found(ver)
            self._log(LOG_SUCCESS, f"✓ ffmpeg.exe 检测成功 ({ver})")
        else:
            self.tool_ffmpeg.set_not_found()
            self._log(LOG_WARNING, "✗ ffmpeg.exe 未找到 (封装功能不可用)")
            missing.append(("ffmpeg", "ffmpeg.exe", "ffmpeg.exe"))

        # 缺失工具弹窗
        if missing:
            for key, display_name, filter_name in missing:
                path = self._prompt_select_tool(display_name, filter_name)
                if path:
                    self.config.tool_paths[key] = path
                    self._log(LOG_SUCCESS, f"已手动指定 {display_name}: {path}")
                    # 重新检测状态
                    if key == "n_m3u8dl":
                        self.tool_n_m3u8dl.set_found(detect_n_m3u8dl_version(path))
                    elif key == "mp4decrypt":
                        self.tool_mp4decrypt.set_found(detect_mp4decrypt_version(path))
                    elif key == "ffmpeg":
                        self.tool_ffmpeg.set_found(detect_ffmpeg_version(path))
            self.config.save()

    def _prompt_select_tool(self, display_name: str, filter_name: str) -> str | None:
        """弹窗让用户选择缺失的工具文件。"""
        reply = QMessageBox.question(
            self, "工具未找到",
            f"未找到 {display_name}\n\n是否手动选择文件？\n(也可将文件放入程序目录后重启)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return None
        filepath, _ = QFileDialog.getOpenFileName(
            self, f"选择 {display_name}", "",
            f"可执行文件 ({filter_name});;所有文件 (*.*)"
        )
        return filepath if filepath else None

    # ══════════════════════════════════════════════
    # 配置读写
    # ══════════════════════════════════════════════

    def _load_config_to_ui(self):
        cfg = self.config
        self.input_url.setText(cfg.m3u8_url)
        self.input_cookie.setPlainText(cfg.cookie)
        self.input_headers.setPlainText(cfg.headers_text)

        qmap = {"auto": 0, "4k": 1, "1080p": 2, "720p": 3, "480p": 4, "360p": 5}
        idx = qmap.get(cfg.video_quality, 0)
        self.combo_quality.setCurrentIndex(idx)
        self.list_quality.setCurrentRow(idx)

        self.chk_download_sub.setChecked(cfg.subtitle.download_external)
        langs = cfg.subtitle.languages
        self.chk_sub_zh.setChecked("zh-CN" in langs or "zh" in langs)
        self.chk_sub_zht.setChecked("zh-TW" in langs)
        self.chk_sub_en.setChecked("en" in langs)
        self.chk_sub_ja.setChecked("ja" in langs)
        fmap = {"srt": self.radio_srt, "vtt": self.radio_vtt, "ass": self.radio_ass}
        fmap.get(cfg.subtitle.format, self.radio_srt).setChecked(True)

        self.input_save_dir.setText(cfg.save_dir)
        self.input_filename.setText(cfg.filename)
        ofmap = {"mp4": 0, "mkv": 1, "ts": 2}
        self.combo_output_format.setCurrentIndex(ofmap.get(cfg.output_format, 0))

        emap = {"auto": 0, "aes-128": 1, "cenc": 2, "sample-aes": 3}
        self.combo_enc_type.setCurrentIndex(emap.get(cfg.decryption.encryption_type, 0))
        self.input_key.setText(cfg.decryption.key)
        self.input_key_file.setText(cfg.decryption.key_file)
        dtmap = {"auto": 0, "builtin": 1, "none": 2}
        self.combo_decrypt_tool.setCurrentIndex(dtmap.get(cfg.decryption.decrypt_tool, 0))

        self.input_ua.setText(cfg.request_headers.user_agent)
        self.input_referer.setText(cfg.request_headers.referer)
        self.input_cookie_adv.setPlainText(cfg.request_headers.cookie)

    def _collect_config_from_ui(self) -> AppConfig:
        cfg = self.config
        cfg.m3u8_url = self.input_url.text().strip()

        # Cookie: 基础优先
        bc = self.input_cookie.toPlainText().strip()
        ac = self.input_cookie_adv.toPlainText().strip()
        cfg.cookie = bc or ac
        cfg.request_headers.cookie = ac

        # Headers: 合并去重
        bh = self.input_headers.toPlainText().strip()
        ah = self.input_headers_adv.toPlainText().strip()
        merged, seen = [], set()
        for block in [bh, ah]:
            for line in block.splitlines():
                line = line.strip()
                if ":" in line:
                    k = line.split(":", 1)[0].strip().lower()
                    if k not in seen:
                        seen.add(k)
                        merged.append(line)
        cfg.headers_text = "\n".join(merged)

        qmap = ["auto", "4k", "1080p", "720p", "480p", "360p"]
        cfg.video_quality = qmap[self.combo_quality.currentIndex()]

        cfg.subtitle.download_external = self.chk_download_sub.isChecked()
        langs = []
        if self.chk_sub_zh.isChecked():
            langs.append("zh-CN")
        if self.chk_sub_zht.isChecked():
            langs.append("zh-TW")
        if self.chk_sub_en.isChecked():
            langs.append("en")
        if self.chk_sub_ja.isChecked():
            langs.append("ja")
        cfg.subtitle.languages = langs
        if self.radio_srt.isChecked():
            cfg.subtitle.format = "srt"
        elif self.radio_vtt.isChecked():
            cfg.subtitle.format = "vtt"
        else:
            cfg.subtitle.format = "ass"

        cfg.save_dir = self.input_save_dir.text().strip()
        cfg.filename = self.input_filename.text().strip()
        ofmap = ["mp4", "mkv", "ts"]
        cfg.output_format = ofmap[self.combo_output_format.currentIndex()]

        emap = ["auto", "aes-128", "cenc", "sample-aes"]
        cfg.decryption.encryption_type = emap[self.combo_enc_type.currentIndex()]
        cfg.decryption.key = self.input_key.text().strip()
        cfg.decryption.key_file = self.input_key_file.text().strip()
        dtmap = ["auto", "builtin", "none"]
        cfg.decryption.decrypt_tool = dtmap[self.combo_decrypt_tool.currentIndex()]

        cfg.request_headers.user_agent = self.input_ua.text().strip()
        cfg.request_headers.referer = self.input_referer.text().strip()

        return cfg

    # ══════════════════════════════════════════════
    # 解析 M3U8
    # ══════════════════════════════════════════════

    def _parse_m3u8(self) -> M3U8ParseResult | None:
        url = self.input_url.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请输入视频地址(M3U8/MPD)")
            return None

        # 自动识别格式
        fmt = detect_format(url)
        self._log(LOG_INFO, f"开始解析视频地址... 检测类型: {format_label(fmt)}")
        self._set_task_status("解析中", "#3b82f6")
        QApplication.processEvents()

        try:
            cookie = self.input_cookie.toPlainText().strip() or self.input_cookie_adv.toPlainText().strip()
            headers = {}
            ua = self.input_ua.text().strip()
            if ua:
                headers["User-Agent"] = ua
            ref = self.input_referer.text().strip()
            if ref:
                headers["Referer"] = ref
            for line in self.input_headers_adv.toPlainText().strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip()] = v.strip()

            # 本地文件 vs 远程URL
            if Path(url).is_file():
                fmt, result = parse_file(url, cookie=cookie, headers=headers)
            else:
                fmt, result = parse_media(url, cookie=cookie, headers=headers)
            self.parse_result = result
            self._current_format = fmt

            self._populate_video_tracks(result)
            self._populate_audio_tracks(result)

            enc = f"，加密: {result.encryption_detected}" if result.encryption_detected else ""
            vinfo = ", ".join(f"{v.width}x{v.height}" for v in result.videos[:3])
            ainfo = ", ".join((a.name or a.language or "?") for a in result.audios[:3])
            self._log(LOG_INFO, f"解析: 视频:{vinfo or '无'} 音频:{ainfo or '无'}")
            self._log(LOG_SUCCESS,
                      f"解析成功({format_label(fmt)})，共发现 {len(result.videos)} 个清晰度，"
                      f"{len(result.audios)} 个音频轨道，"
                      f"{len(result.subtitles)} 个字幕轨道{enc}")
            return result

        except Exception as e:
            self._log(LOG_ERROR, f"解析失败: {e}")
            QMessageBox.critical(self, "解析失败", str(e))
            return None
        finally:
            self._set_task_status("空闲中", "#22c55e")

    def _populate_video_tracks(self, result: M3U8ParseResult):
        self.combo_video_track.clear()
        self.combo_video_track.addItem("自动选择")
        self.list_video_track.clear()
        self.list_video_track.addItem("自动选择")
        for vs in result.videos:
            codec = ""
            if vs.codecs:
                if "hvc1" in vs.codecs.lower() or "hev1" in vs.codecs.lower():
                    codec = " (H.265)"
                elif "avc1" in vs.codecs.lower():
                    codec = " (H.264)"
            label = f"{vs.quality_label()}{codec}"
            if vs.bandwidth:
                label += f" [{vs.bandwidth // 1000}kbps]"
            self.combo_video_track.addItem(label)
            self.list_video_track.addItem(label)
        self.list_video_track.setCurrentRow(0)

    def _populate_audio_tracks(self, result: M3U8ParseResult):
        self.list_audio.clear()
        self._add_audio_item("音频轨道", True)
        self._add_audio_item("自动最佳", True)
        for at in result.audios:
            cat = at.language_category()
            codec = f"AAC/{at.channels}" if at.channels else "AAC"
            self._add_audio_item(f"{cat} ({codec})", at.default)

    def _add_audio_item(self, text: str, checked: bool = False):
        item = QListWidgetItem(text)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.list_audio.addItem(item)

    # ══════════════════════════════════════════════
    # 下载控制
    # ══════════════════════════════════════════════

    def _on_start(self):
        if self.download_thread and self.download_thread.isRunning():
            QMessageBox.information(self, "提示", "已有任务正在运行")
            return

        self.config = self._collect_config_from_ui()

        if not self.config.m3u8_url:
            QMessageBox.warning(self, "提示", "请输入视频地址(M3U8/MPD)")
            return
        if not self.config.tool_paths.get("n_m3u8dl"):
            QMessageBox.warning(self, "提示", "未找到 N_m3u8DL-RE，无法开始下载")
            return
        if not self.config.save_dir:
            QMessageBox.warning(self, "提示", "请选择保存目录")
            return
        if not self.config.filename:
            QMessageBox.warning(self, "提示", "请输入文件名")
            return

        # 自动创建目录
        Path(self.config.save_dir).mkdir(parents=True, exist_ok=True)

        result = self._parse_m3u8()
        if not result:
            return

        selected_video = self._get_selected_video(result)
        selected_audio = self._get_selected_audio(result)
        selected_subs = self._get_selected_subtitles(result)

        self._log(LOG_INFO, "准备开始下载...")
        if selected_video:
            self._log(LOG_INFO, f"视频: {selected_video.quality_label()}")
        if selected_audio:
            self._log(LOG_INFO, f"音频: {selected_audio.display_name()}")
        if selected_subs:
            self._log(LOG_INFO, f"字幕: {', '.join(s.display_name() for s in selected_subs)}")

        self.config.save()

        self.download_thread = DownloadThread(
            config=self.config,
            parse_result=result,
            selected_video=selected_video,
            selected_audio=selected_audio,
            selected_subtitles=selected_subs,
        )
        self.download_thread.log.connect(self._on_log)
        self.download_thread.progress.connect(self._on_progress)
        self.download_thread.speed.connect(self._on_speed)
        self.download_thread.size.connect(self._on_size)
        self.download_thread.eta.connect(self._on_eta)
        self.download_thread.finished_ok.connect(self._on_download_ok)
        self.download_thread.failed.connect(self._on_download_failed)

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._set_task_status("下载中", "#3b82f6")
        self.lbl_threads.setText("1/1")
        self.download_thread.start()

    def _on_stop(self):
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.stop()
            self._log(LOG_WARNING, "正在停止任务...")
            self.btn_stop.setEnabled(False)

    def _on_progress(self, pct: int):
        self.progress_bar.setValue(pct)
        self.status_progress.setValue(pct)
        self.lbl_progress.setText(f"{pct:.2f}%")
        self.lbl_total_progress.setText(f"{pct:.2f}%")

    def _on_speed(self, speed: str):
        self.lbl_speed.setText(speed)

    def _on_size(self, size: str):
        self.lbl_downloaded.setText(size)

    def _on_eta(self, eta: str):
        self.lbl_remaining.setText(eta)

    def _on_download_ok(self, output_path: str):
        self._log(LOG_SUCCESS, f"下载完成: {output_path}")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._set_task_status("已完成", "#22c55e")
        self.lbl_threads.setText("0/0")
        self.progress_bar.setValue(100)
        self.status_progress.setValue(100)
        self.lbl_status_left.setText("完成")
        if self.chk_open_after.isChecked():
            self._open_in_explorer(output_path)
        QMessageBox.information(self, "完成", f"下载完成:\n{output_path}")

    def _on_download_failed(self, error: str):
        self._log(LOG_ERROR, f"下载失败: {error}")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._set_task_status("失败", "#ef4444")
        self.lbl_threads.setText("0/0")
        self.lbl_status_left.setText("失败")
        QMessageBox.critical(self, "下载失败", error)

    def _get_selected_video(self, result: M3U8ParseResult) -> VideoStream | None:
        # 优先级1: 用户手动选择的视频轨道 (index > 0 表示非"自动选择")
        track_idx = self.list_video_track.currentRow()
        if track_idx > 0 and track_idx - 1 < len(result.videos):
            return result.videos[track_idx - 1]
        # 优先级2: 清晰度选择
        idx = self.list_quality.currentRow()
        if idx == 0:
            return result.best_video()
        targets = {1: 2160, 2: 1080, 3: 720, 4: 480, 5: 360}
        target = targets.get(idx)
        if target:
            for v in result.videos:
                if v.height == target:
                    return v
            if result.videos:
                return min(result.videos, key=lambda v: abs(v.height - target))
        # 优先级3: 自动最佳
        return result.best_video()

    def _get_selected_audio(self, result: M3U8ParseResult) -> AudioTrack | None:
        if not result.audios:
            return None
        for i in range(2, self.list_audio.count()):
            item = self.list_audio.item(i)
            if item.checkState() == Qt.Checked:
                for at in result.audios:
                    if at.language_category() in item.text():
                        return at
        return result.default_audio()

    def _get_selected_subtitles(self, result: M3U8ParseResult) -> list[SubtitleStream]:
        if not self.chk_download_sub.isChecked():
            return []
        selected = []
        for s in result.subtitles:
            cat = s.language_category()
            if cat == "简体中文" and self.chk_sub_zh.isChecked():
                selected.append(s)
            elif cat == "繁体中文" and self.chk_sub_zht.isChecked():
                selected.append(s)
            elif cat == "English" and self.chk_sub_en.isChecked():
                selected.append(s)
            elif cat == "日本語" and self.chk_sub_ja.isChecked():
                selected.append(s)
            elif cat == "其他" and self.chk_sub_other.isChecked():
                selected.append(s)
        return selected

    # ══════════════════════════════════════════════
    # 日志系统 (彩色 QTextEdit)
    # ══════════════════════════════════════════════

    def _log(self, level: str, msg: str):
        """对外接口: 写入彩色日志。"""
        self._append_colored_log(level, msg)

    def _on_log(self, level: str, msg: str):
        """下载线程日志回调。"""
        self._append_colored_log(level, msg)

    def _append_colored_log(self, level: str, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = LOG_COLORS.get(level, LOG_COLORS[LOG_INFO])
        safe_msg = (msg.replace("&", "&amp;").replace("<", "&lt;")
                    .replace(">", "&gt;"))
        html = (f'<div style="white-space:pre-wrap;">'
                f'<span style="color:#666;">[{timestamp}]</span> '
                f'<span style="color:{color};">{safe_msg}</span></div>')
        self.log_output.append(html)
        # 自动滚动
        cursor = self.log_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_output.setTextCursor(cursor)
        self.log_output.ensureCursorVisible()

    def _on_clear_log(self):
        self.log_output.clear()
        self._log(LOG_INFO, "日志已清空")

    def _on_copy_log(self):
        text = self.log_output.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self._log(LOG_SUCCESS, "日志已复制到剪贴板")

    def _on_save_log(self):
        """保存日志到 logs/YYYY-MM-DD.log"""
        try:
            log_dir = get_app_dir() / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.log"
            text = self.log_output.toPlainText()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n===== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====\n")
                f.write(text)
                f.write("\n")
            self._log(LOG_SUCCESS, f"日志已保存: {log_file}")
        except Exception as e:
            self._log(LOG_ERROR, f"保存日志失败: {e}")

    # ══════════════════════════════════════════════
    # 按钮事件
    # ══════════════════════════════════════════════

    def _on_paste_url(self):
        text = QApplication.clipboard().text()
        if text:
            self.input_url.setText(text.strip())
            self._log(LOG_INFO, "已粘贴M3U8地址")

    def _on_browse_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self, "选择保存目录",
            self.input_save_dir.text() or str(Path.home())
        )
        if directory:
            self.input_save_dir.setText(directory)

    def _on_save_as(self):
        default_name = self.input_filename.text() or "video.mp4"
        default_dir = self.input_save_dir.text() or str(Path.home())
        filepath, _ = QFileDialog.getSaveFileName(
            self, "另存为", str(Path(default_dir) / default_name),
            "MP4 文件 (*.mp4);;MKV 文件 (*.mkv);;所有文件 (*.*)"
        )
        if filepath:
            p = Path(filepath)
            self.input_save_dir.setText(str(p.parent))
            self.input_filename.setText(p.name)

    def _on_select_key_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择Key文件", "", "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if filepath:
            self.input_key_file.setText(filepath)

    def _on_save_config(self):
        self.config = self._collect_config_from_ui()
        if self.config.save():
            self._log(LOG_SUCCESS, "配置已保存到 config.json")
            QMessageBox.information(self, "保存成功", "配置已保存到 config.json")
        else:
            QMessageBox.warning(self, "保存失败", "无法写入 config.json")

    def _on_open_save_dir(self):
        d = self.input_save_dir.text().strip()
        if d and Path(d).is_dir():
            self._open_in_explorer(d)
        else:
            QMessageBox.warning(self, "提示", "保存目录不存在或未设置")

    def _on_open_temp_dir(self):
        self._open_in_explorer(tempfile.gettempdir())

    def _on_about(self):
        QMessageBox.about(
            self, "关于",
            f"{APP_NAME} v{APP_VERSION}\n\n"
            f"支持 HLS M3U8 / DASH MPD 双格式\n"
            f"基于 PySide6 + N_m3u8DL-RE + mp4decrypt + ffmpeg\n\n"
            f"程序目录: {get_app_dir()}\n"
            f"配置文件: config.json"
        )

    def _on_quality_selected(self, row: int):
        if 0 <= row < self.combo_quality.count():
            self.combo_quality.setCurrentIndex(row)

    # ══════════════════════════════════════════════
    # 工具方法
    # ══════════════════════════════════════════════

    def _set_task_status(self, text: str, color: str):
        self.lbl_task_status.setText(text)
        self.lbl_task_status.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")

    def _open_in_explorer(self, path: str):
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            self._log(LOG_ERROR, f"打开目录失败: {e}")

    def closeEvent(self, event):
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.stop()
            self.download_thread.wait(3000)
        self.config = self._collect_config_from_ui()
        self.config.save()
        event.accept()


# ══════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(DARK_QSS)
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
