# M3U8视频下载助手 v1.0.0 (Beta)

基于 PySide6 的 Windows 桌面视频下载工具，支持 M3U8 流媒体解析、多清晰度选择、多音轨/字幕下载、DRM 解密和 ffmpeg 封装。

## 功能特性

- **M3U8 解析**：自动解析 master.m3u8，识别所有视频清晰度、音频轨道、字幕流
- **多清晰度**：自动最佳 / 4K (2160P) / 1080P / 720P / 480P / 360P
- **多音轨**：中文、英文、日语、原声等自动识别并可选
- **字幕下载**：支持 SRT / VTT / ASS 外挂字幕，多语言可选
- **DRM 解密**：支持 AES-128 / CENC / SAMPLE-AES，Key 或 Key 文件
- **请求头定制**：User-Agent、Referer、Cookie、自定义 Headers
- **下载流水线**：N_m3u8DL-RE → mp4decrypt → ffmpeg 自动封装
- **彩色日志系统**：QTextEdit HTML 彩色输出，成功绿/警告黄/错误红/执行蓝
- **日志控制**：清空 / 复制 / 保存(logs/YYYY-MM-DD.log)
- **实时状态**：下载速度、已下载大小、百分比、剩余时间 ETA
- **无黑窗**：Windows 下 CREATE_NO_WINDOW，所有工具输出捕获到 GUI
- **工具自动扫描**：三级优先级(程序目录/tools/PATH)，缺失时弹窗选择
- **配置持久化**：所有选项保存到 config.json，下次启动自动恢复
- **深色专业界面**：1:1 还原设计稿

## 环境要求

- Windows 10/11
- Python 3.11（开发环境）
- 运行目录需放置以下工具（自动扫描，禁止写死路径）：
  - `N_m3u8DL-RE(6).exe`
  - `mp4decrypt.exe`
  - `ffmpeg.exe`

## 项目结构

```
M3U8视频下载助手/
├── main.py              # 主窗口 GUI（PySide6，彩色日志）
├── m3u8_parser.py       # M3U8 解析器
├── download_thread.py   # 下载工作线程（无黑窗+进度解析）
├── config.py            # 配置管理（config.json）
├── tool_scanner.py      # 工具自动扫描（三级优先级）
├── styles.py            # 深色主题 QSS
├── requirements.txt     # Python 依赖
├── build.bat            # PyInstaller 打包脚本
└── README.md            # 本文件
```

## 开发运行

```bash
pip install -r requirements.txt
python main.py
```

## 打包 EXE

```bash
build.bat
```

或手动：
```bash
pip install -r requirements.txt
pyinstaller --onefile --noconsole --name "M3U8视频下载助手" main.py
```

打包完成后，输出位于 `dist\M3U8视频下载助手\` 目录。

## 运行目录结构

```
M3U8视频下载助手/
├── M3U8视频下载助手.exe
├── N_m3u8DL-RE(6).exe   ← 自行放入
├── mp4decrypt.exe       ← 自行放入
├── ffmpeg.exe           ← 自行放入
├── config.json          （首次运行后自动生成）
└── logs/                （保存日志后自动生成）
    └── YYYY-MM-DD.log
```

## 使用说明

1. 输入 M3U8 地址（必填）
2. 如有需要，填写 Cookie 和 Headers
3. 点击「开始下载」→ 自动解析并填充可用清晰度/音轨/字幕
4. 选择目标清晰度、音轨、字幕
5. 设置保存目录和文件名（支持中文）
6. （可选）在高级设置中配置解密密钥和请求头
7. 等待下载完成，日志窗口实时显示彩色进度

## 日志颜色说明

| 颜色 | 级别 | 含义 |
|------|------|------|
| 绿色 | SUCCESS | 成功信息 |
| 黄色 | WARNING | 警告信息 |
| 红色 | ERROR | 错误信息 |
| 蓝色 | INFO | 执行信息 |

## 技术栈

- **GUI**：PySide6 (Qt for Python)
- **下载核心**：N_m3u8DL-RE
- **解密**：mp4decrypt (Bento4)
- **封装**：ffmpeg
- **打包**：PyInstaller
