---
name: download_video
description: 下载 YouTube / Twitch / TwitCasting / Twitter(X) 的直播回放（VOD、Archive、录播）与聊天室弹幕，并把弹幕清洗成标准 JSON。当用户要求下载直播回放、存档、录播、切片素材、弹幕或聊天记录，或直接给出 youtube.com / twitch.tv / twitcasting.tv / x.com 的影片链接时使用。
---

# AutoKiri 直播回放下载

把直播回放和聊天室弹幕一次抓下来，按「实况主 / 日期 / 标题」归档。

## 前置：确认 uv 装了没

三个入口都靠 uv 管理环境，所以**动手前先跑一次**：

```bash
uv --version
```

有版本号就直接往下走。命令不存在（`command not found` / 不是内部或外部命令）的话，**先问用户要不要装，别自己闷头装**，也别改用 `python`、`pip` 之类的方式绕开 —— 依赖不会齐。用户同意后：

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

装完要开个新终端（或让 PATH 生效）才认得到 `uv`。

## 前置：第一次用要先抓工具

内置工具（yt-dlp / ffmpeg / node / TwitchDownloaderCLI）约 370MB，**不进 git**，所以刚 clone 下来的 `assets/` 是空的。第一次使用先跑：

```bash
uv run scripts/setup_assets.py
```

只会下载缺的那几个，已经有的自动跳过；中断了再跑一次即可续。要强制重抓用 `--force`。

工具没齐时三个入口会直接退出码 `1` 并提示这条命令，不会自己闷头下载 —— 370MB 的流量值得先让用户知道。

## 用法

先 `cd` 到本 SKILL.md 所在目录 —— `uv run` 的相对路径以当前目录为准，在别处执行会找不到脚本。**`cd` 写绝对路径**：shell 的当前目录跨命令保留，用相对路径连着 `cd` 两次第二次就会失败，之后读别处的文件还会报出误导人的 not found。

同时**设 UTF-8**：Windows 终端默认 cp950 / cp936，影片标题和实况主名里的中日文会变成 `�F������` 这种乱码。**看到乱码不要照着猜名字**，回来设编码重跑。

```bash
cd <仓库绝对路径>/download_video
export PYTHONIOENCODING=utf-8                      # PowerShell: $env:PYTHONIOENCODING = "utf-8"

uv run scripts/down_video.py --link <video_link>   # 只下影片
uv run scripts/down_chat.py  --link <video_link>   # 只抓弹幕
uv run scripts/video_chat.py --link <video_link>   # 影片 + 弹幕
```

用户没指明要哪种时，默认用 `video_chat.py`。

**除了上面那步 uv，别的前置检查都不用做。** `uv run` 会自动建立 `.venv` 并装好依赖，不需要 `uv venv`、`activate` 或 `uv pip install`；凭证也不用事先确认 —— 缺什么程序会自己报出来，届时再照下面「按报错配置凭证」处理。

**参数**

- `--link`（必填）影片链接。**链接不明确时先问用户，不要猜、不要拿示例链接顶替。**
- `--yes`（可选）识别不到实况主时仍继续下载。默认是直接中止 —— 先读「识别到 Unknown」再决定要不要加。

三个入口都是纯非交互的：不会提示输入，成功退出码 `0`，失败 `1`，参数错误 `2`。影片超过 10GB 会自动等分切割成 `[P1]`、`[P2]`…，原文件保留。

## 按报错配置凭证

凭证是**按需**的，只在程序报出来之后才处理：

> **下载 YouTube 影片时不要向用户索取 `twitch_OAuth`。** 那个 token 只跟 Twitch 有关，YouTube / TwitCasting / Twitter 全程用不到，程序也不会为它们报这个警告。

**看到 `twitch_OAuth is not configured in ...`**

只会在下载 Twitch 时出现。公开 VOD 其实照样能下，所以先看这次是不是真的失败了 —— 只有在订阅限定影片下载失败时才需要配置。要配的话，把 `scripts/.env.example` 复制成 `scripts/.env`（文件名就是 `.env`，别加任何前缀），再引导用户取值：

1. 浏览器登录 Twitch，打开任意 Twitch 页面
2. 按 `F12` 打开开发者工具
3. **应用程序 (Application)** → 左侧 **Cookies** → `https://www.twitch.tv`
4. 找到 `auth-token`，把值填进 `scripts/.env`：

```env
twitch_OAuth="你的TwitchOAuth"
```

**看到读取 Firefox Cookie 失败，或影片被判定为会员限定**

只有 YouTube 会员限定影片需要。程序自动用 `--cookies-from-browser firefox` 读 Cookie，所以用户必须**安装 Firefox 并在其中登录 YouTube 账号**；Chrome 和 Edge 无法自动获取 Cookie。公开影片不受影响。

## 平台支持

| 平台 | 影片 | 弹幕 | 备注 |
|---|---|---|---|
| YouTube | ✅ | ✅ | 会员限定影片需要 Firefox Cookie |
| Twitch | ✅ | ✅ | 订阅限定影片需要 OAuth Token；弹幕内嵌 BTTV / FFZ / 7TV 表情 |
| TwitCasting | ✅ | ❌ | 弹幕抓取暂不支持 |
| Twitter (X) | ✅ | ❌ | Space 为纯音频，输出 `.wav` |

## 输出位置

```
videos/<实况主>/<日期>/<标题>_[<video_id>]/
├── [平台][日期][实况主] 标题.mp4              # 影片（Twitter Space 为 .wav）
├── [平台][日期][实况主] 标题_chat_parsed.json  # 清洗后的弹幕
└── 标题_source_link.txt                       # 原始链接备忘
```

「实况主」取自 `scripts/config.yaml` 的 `streamers` 列表，匹配不到时归入 `Unknown`。新增实况主的字段与取值方式见下面「问用户要不要归档进 config」。

## 常见问题

**识别到 `Unknown` 实况主，任务被中止**

先分清是哪一种，不要无脑加 `--yes`：

- **影片是会限 / 订阅限定，Cookie 或 Token 已失效** —— 先按上面「按报错配置凭证」修好。此时硬加 `--yes` 只会下到低画质版本或直接失败，也不要去动 `config.yaml`（这种情况下抓到的名字本来就是错的）
- **该实况主本来就不在 `config.yaml` 里** —— 属正常，按下面处理

后者**就在这时问用户**要不要顺手建档，不要自己闷头决定：

> 这位实况主不在 `config.yaml` 里，影片会被归到 `Unknown` 底下。要不要我先把他加进去？这样这次和以后的影片都会自动归到正确的名字下面。

- 用户要 —— 按下面写进 `config.yaml`，然后**重新跑一次原来的命令**（不必加 `--yes`，这次就能正确归档）
- 用户不要 —— 加 `--yes` 重跑，影片直接落在 `videos/Unknown/` 底下

写进 `scripts/config.yaml` 的 `streamers` 列表前，先取得频道标识：

| 平台 | 填哪个字段 | 怎么取 |
|---|---|---|
| youtube | `channel_id` | 见下方命令 |
| twitch | `channel_name` | 取日志里 `Streamer` 那一行的值，含括号部分要一起 |
| twitcast | `channel_name` | 网址中 `twitcasting.tv/<这段>` |
| twitter | `channel_id` | 网址中 `x.com/<这段>` |

YouTube 的 channel_id（用内置的 yt-dlp 与 node，避免 JS runtime 警告）：

```bash
PATH="$PWD/assets/node-v24.13.1-win-x64:$PATH" \
  ./assets/yt-dlp/yt-dlp.exe --js-runtimes node --print channel_id <video_link>
```

`name` 用用户习惯的称呼 —— 它会直接变成资料夹名。同一位实况主的多个平台并列在同一个 `accounts` 底下：

```yaml
  - name: "Haru"
    accounts:
      - platform: "youtube"
        channel_id: "UCrOV-crqUmRluPVOjjVs-Xw"
      - platform: "twitcast"
        channel_name: "shino_nome22"
```

如果之前已经有影片落在 `videos/Unknown/` 里，写完 config 也不会自动搬走 —— 要不要移到新名字底下，问过用户再动。

**弹幕没抓到** —— 直播刚结束时 YouTube 还没生成弹幕存档，或该影片本来就没有弹幕。影片不受影响，**跟用户说一声就行**，不用改用别的入口、也不用重跑。

**TwitCasting 没有弹幕** —— 暂不支持，只会下影片。

**下载很慢** —— 可在 `scripts/config.yaml` 调整 yt-dlp 相关参数。

## 内部结构

- `scripts/` —— 三个 CLI 入口，加 `core/`（配置与管线）、`downloader/`（各平台下载器）、`post_process/`（弹幕清洗、影片切割）
- `scripts/setup_assets.py` —— 抓取内置工具，第一次使用时跑
- `scripts/config.yaml`、`scripts/.env` —— 配置与凭证
- `assets/` —— yt-dlp、ffmpeg、node、TwitchDownloaderCLI；由 setup 脚本下载，已 gitignore
- 更完整的说明见 `scripts/README.md`
