# AutoKiri

AutoKiri 是一个专为直播回放（Archive/VOD）设计的自动化工具，支持 **YouTube、Twitch、TwitCasting** 平台。它可以一键完成视频下载、弹幕抓取与清洗。

## 🌟 核心功能

* **多平台支持**：完整支持 YouTube、Twitch、TwitCasting 的视频与信息提取。
* **智能下载**：自动处理 YouTube 会员限定视频（需 Cookie）与 Twitch 订阅者限定视频（需 OAuth）。
* **弹幕清洗**：将复杂的原始弹幕格式转换为标准化的 JSON 格式，方便后续分析。

## 已知问题
1. YouTube聊天室处理需时，直播结束没法马上取得，目前建议后续使用 `down_chat.py` 重新下载
2. TwitCasting聊天室抓取功能实现较为复杂，目前不支援

## ⚡ 快速开始

在**项目根目录**（`scripts/` 的上一层）执行。第一次使用要先抓内置工具（约 370MB，不进 git）：

```bash
uv run scripts/setup_assets.py                     # 首次使用，抓 yt-dlp/ffmpeg/node/TwitchDownloaderCLI
```

之后就是三个入口：

```bash
uv run scripts/down_video.py --link <video_link>   # 只下影片
uv run scripts/down_chat.py  --link <video_link>   # 只抓弹幕
uv run scripts/video_chat.py --link <video_link>   # 影片 + 弹幕
```

`uv run` 会依据根目录的 `pyproject.toml` 自动建立 `.venv` 并安装依赖，
不需要手动执行 `uv venv` / `activate` / `uv pip install`。

加上 `--yes` 可以在识别不到实况主时仍继续下载。三个入口皆为非交互模式，
成功退出码 `0`、失败 `1`、参数错误 `2`。

配置前置：
1. 将 `scripts/.env.example` 复制为 `scripts/.env`(不需加任何前缀) 并填入你的 `Twitch Token`。
2. 对于 YouTube 会员限定影片，`请下载firefox浏览器并登入Youtube账号`
    - (Chrome, Edge目前不支援自动获取Cookie)

## 🛠️ 环境准备与安装

为了确保程序正常运行，请按以下步骤配置环境：

### 1. 基础配置 (.env)

在 `scripts/` 目录下建立一个名为 `.env` 的文件(不需加任何前缀，与 `config.yaml` 同级)，
并填入你的 Twitch 授权信息：

```env
twitch_OAuth="你的TwitchOAuth"
```

**如何获取 Twitch OAuth？**

1. 在浏览器登录 Twitch 账号，并打开 Twitch 页面。
2. 按下 `F12` 打开开发者工具。
3. 点击 **应用程序 (Application)** 选项卡 -> 左侧 **Cookies** -> 找到 `https://www.twitch.tv`。
4. 在列表中找到名为 `auth-token` 的值，将其复制到 `.env` 文件中。

### 2. YouTube 会员限定视频

对于 YouTube 会员限定影片，`请下载firefox浏览器并登入Youtube账号`

## ⚖️ 许可证

本项目采用 **GNU Affero General Public License v3.0 (AGPL-3.0)** 协议授权。

## ⚠️ 注意事项

* 请确保你的网络环境可以正常访问对应的直播平台。
* 如果下载速度缓慢，可以在 `config.yaml` 中调整 `yt-dlp` 的相关参数。
* 内置工具 (yt-dlp / ffmpeg / node / TwitchDownloaderCLI) 位于项目根目录的 `assets/`，由 `scripts/setup_assets.py` 下载，不纳入 git 版控，无需另外安装。