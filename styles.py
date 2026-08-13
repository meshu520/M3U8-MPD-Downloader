# -*- coding: utf-8 -*-
"""
深色专业软件风格 QSS 样式表 (Beta)
"""

DARK_QSS = """
/* ══════════════ 全局 ══════════════ */
QWidget {
    background-color: #16161e;
    color: #e0e0e8;
    font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
    font-size: 13px;
}
QMainWindow { background-color: #16161e; }

/* ══════════════ 左侧栏 ══════════════ */
#sidebar {
    background-color: #1c1c28;
    border-right: 1px solid #2a2a3a;
}
#sidebarTitle {
    color: #8888a0;
    font-size: 12px;
    font-weight: bold;
    padding: 12px 16px 4px 16px;
    letter-spacing: 1px;
}

/* ══════════════ 工具卡片 ══════════════ */
#toolCard {
    background-color: #22222e;
    border-radius: 6px;
    margin: 4px 12px;
    padding: 8px 12px;
}
#toolCardName { color: #e0e0e8; font-size: 13px; font-weight: bold; }
#toolCardVersion { color: #6a6a80; font-size: 11px; }

/* ══════════════ 任务信息 ══════════════ */
#taskInfoLabel { color: #8888a0; font-size: 12px; }
#taskInfoValue { color: #e0e0e8; font-size: 12px; }

/* ══════════════ 进度条 ══════════════ */
QProgressBar {
    background-color: #22222e;
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background-color: #3b82f6;
    border-radius: 3px;
}

/* ══════════════ 按钮 ══════════════ */
QPushButton {
    background-color: #2a2a3a;
    color: #e0e0e8;
    border: 1px solid #3a3a4e;
    border-radius: 4px;
    padding: 8px 16px;
    font-size: 13px;
}
QPushButton:hover { background-color: #35354a; border-color: #4a4a60; }
QPushButton:pressed { background-color: #252535; }
QPushButton:disabled {
    background-color: #1e1e28;
    color: #555566;
    border-color: #2a2a3a;
}

/* 开始按钮 */
#btnStart {
    background-color: #2563eb;
    border: 1px solid #3b82f6;
    color: #ffffff;
    font-weight: bold;
    padding: 10px 16px;
}
#btnStart:hover { background-color: #3b82f6; }
#btnStart:pressed { background-color: #1d4ed8; }

/* 停止按钮 */
#btnStop {
    background-color: #991b1b;
    border: 1px solid #dc2626;
    color: #ffffff;
    font-weight: bold;
    padding: 10px 16px;
}
#btnStop:hover { background-color: #dc2626; }
#btnStop:pressed { background-color: #7f1d1d; }

/* 日志控制按钮 (小) */
#btnLogControl {
    background-color: #22222e;
    border: 1px solid #3a3a4e;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 12px;
    color: #a0a0b8;
}
#btnLogControl:hover { background-color: #2a2a3a; color: #e0e0e8; }

/* 底部导航 */
#btnNav {
    background-color: transparent;
    border: none;
    color: #6a6a80;
    padding: 8px;
    font-size: 11px;
}
#btnNav:hover {
    color: #e0e0e8;
    background-color: #22222e;
    border-radius: 4px;
}

/* ══════════════ 分组框 ══════════════ */
QGroupBox {
    background-color: #1c1c28;
    border: 1px solid #2a2a3a;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
    color: #c0c0d0;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    background-color: #1c1c28;
}

/* ══════════════ 输入框 ══════════════ */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #22222e;
    border: 1px solid #3a3a4e;
    border-radius: 4px;
    padding: 6px 10px;
    color: #e0e0e8;
    selection-background-color: #3b82f6;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus { border-color: #3b82f6; }
QLineEdit:disabled, QTextEdit:disabled {
    background-color: #1a1a24;
    color: #555566;
}

/* ══════════════ 下拉框 ══════════════ */
QComboBox {
    background-color: #22222e;
    border: 1px solid #3a3a4e;
    border-radius: 4px;
    padding: 6px 10px;
    color: #e0e0e8;
}
QComboBox:hover { border-color: #4a4a60; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #8888a0;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #22222e;
    border: 1px solid #3a3a4e;
    color: #e0e0e8;
    selection-background-color: #3b82f6;
    outline: none;
}

/* ══════════════ 列表控件 ══════════════ */
QListWidget {
    background-color: #22222e;
    border: 1px solid #3a3a4e;
    border-radius: 4px;
    color: #e0e0e8;
    outline: none;
}
QListWidget::item { padding: 6px 10px; border-radius: 3px; }
QListWidget::item:hover { background-color: #2a2a3a; }
QListWidget::item:selected { background-color: #3b82f6; color: #ffffff; }

/* ══════════════ 单选/复选框 ══════════════ */
QRadioButton, QCheckBox { color: #c0c0d0; spacing: 6px; }
QRadioButton::indicator, QCheckBox::indicator { width: 16px; height: 16px; }
QRadioButton::indicator:unchecked, QCheckBox::indicator:unchecked {
    border: 2px solid #4a4a60;
    border-radius: 3px;
    background-color: #22222e;
}
QRadioButton::indicator:unchecked { border-radius: 9px; }
QRadioButton::indicator:checked, QCheckBox::indicator:checked {
    border: 2px solid #3b82f6;
    background-color: #3b82f6;
    border-radius: 3px;
}
QRadioButton::indicator:checked { border-radius: 9px; }

/* ══════════════ 日志窗口 (QTextEdit) ══════════════ */
#logOutput {
    background-color: #0e0e14;
    border: 1px solid #2a2a3a;
    border-radius: 4px;
    color: #9090a0;
}
#logOutput QTextEdit {
    background-color: #0e0e14;
    border: none;
}

/* ══════════════ 状态栏 ══════════════ */
QStatusBar {
    background-color: #1c1c28;
    border-top: 1px solid #2a2a3a;
    color: #8888a0;
    font-size: 12px;
}
QStatusBar QLabel { color: #8888a0; padding: 0 8px; }

/* ══════════════ 滚动条 ══════════════ */
QScrollBar:vertical {
    background-color: #16161e;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #3a3a4e;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background-color: #4a4a60; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background-color: #16161e;
    height: 8px;
}
QScrollBar::handle:horizontal {
    background-color: #3a3a4e;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ══════════════ 标签 ══════════════ */
QLabel { color: #c0c0d0; }
#sectionLabel {
    color: #8888a0;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
}

/* ══════════════ 分割线 ══════════════ */
QFrame[frameShape="4"] { color: #2a2a3a; }

/* ══════════════ 工具提示 ══════════════ */
QToolTip {
    background-color: #22222e;
    color: #e0e0e8;
    border: 1px solid #3a3a4e;
    padding: 4px 8px;
}
"""
