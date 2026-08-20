---
name: finesub
description: 用 finesub 把长音频/视频转成精修级中文字幕（人声分离 → VAD+ASR → 稳定化 → LLM 纠错翻译 → SRT）。当用户要求生成字幕、上字幕、转写、听写、翻译字幕、做 SRT、给直播回放/切片配中文字幕，或给出音视频文件与影片链接要求出字幕时使用。
---

# finesub 精修中文字幕

一条命令从音视频出中文 SRT：

```text
音频/视频 → 人声分离 → VAD + ASR → 稳定化 → LLM 纠错翻译 → 成品 SRT
```

上游完整说明见 `references/finesub/README.md`（本 skill 不含脚本，全部靠 finesub CLI）。

## 前置：确认 uv 装了没

finesub 靠 uv 安装和管理环境，所以**动手前先跑一次**：

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

## 前置：确认 finesub 装了没

```bash
finesub doctor
```

装好的话会列出各路径与 `runtime ready`，退出码 `0`。

**别用 `finesub --version` 检查** —— 它不是有效参数，会打出一段 usage 并以退出码 `2` 结束，看着很像装坏了，其实装得好好的。

命令不存在就**先问用户要不要装**，同意后：

```bash
uv tool install finesub
```

装的只是个轻量壳。**首次运行**才会自动拉隔离的 Python 运行环境（无需预装 Python）和 FFmpeg，模型按需下载 —— 所以第一次跑会明显慢很多，而且要下几个 GB，**先跟用户说一声**再开跑。一切落在 `%LOCALAPPDATA%\FineSub` 下；要搬盘用 `finesub relocate`，要卸干净用 `finesub uninstall`。

装完要开个新终端才认得到 `finesub`。

## 用法

```bash
# 本地文件（音频、视频都行）
finesub <输入>.mp4 --language ja --extra-info "主播四月一日，原神直播切片" --stage final-srt
```

**跑之前先跟用户对齐三件事**，缺了就问，不要猜：

1. **要不要中文成品**——不传 `--stage` 只出 raw SRT（ASR 原文，不调 API、不花额度）。用户要的是中文字幕就必须加 `--stage final-srt`。
2. **`--extra-info` 有没有料**——主播名、游戏名、角色名、关键专名。非必须，但对纠错准确率影响很大，**值得主动问一句**。
3. **知识库要不要写回**——见下面 `--knowledge`。

**参数**

| 参数 | 说明 |
|---|---|
| `--language` | 不传则自动检测。已知语种就传（如 `ja`），少一次误判 |
| `--extra-info` | 背景信息，自由文本。显著提升纠错准确率 |
| `--stage final-srt` | 跑 LLM 纠错翻译出成品；不传则停在 raw SRT |
| `--knowledge` | `collect`（默认，只读不写）/ `update`（写回）/ `none`（不读不写） |
| `--name` | 指定并覆盖输入名（决定输出目录名）。URL 输入时尤其有用 |
| `--gpu-budget-gb` | 显存够就传 `8`，人声分离阶段并行提速。好卡可传 `12`/`16`，但边际收益有限 |

**`--knowledge` 怎么选**——默认 `collect` 会自动注入已有的主播术语、角色名，但**不改动**知识库。`update` 才把本次发现写回，同一主播越跑越准；因为它会改用户的本地知识库，**同一主播的素材建议先问一句要不要 `update`**。一次性、跟已有主播无关的素材用 `none`。

**这活很慢**（人声分离 + ASR + 逐窗口 LLM，长音频动辄几十分钟），用后台跑，别把会话卡死等它。

## `--stage final-srt` 需要额度

纠错翻译这一步要调模型，**二选一或组合**，跑之前确认用户配好了哪一种，没配就问，别默认它能跑通：

- **API**——Gemini API key（Desktop 在设置页填，CLI/源码写 `.env`），推荐再配 Exa API key；都是免费的。CLI 的写法：在 `%LOCALAPPDATA%\FineSub\user-data\.env` 里写一行 `GEMINI_API_KEY=你的key` 就行，finesub 会自动读取（首次运行会把明文就地加密成 `fs$…` 密文，无需手动处理）。
- **本机 agent 后端**——直接用 **Antigravity CLI / Codex CLI / Claude Code** 已有的订阅额度。其中 Antigravity 有现成预设，且是唯一支持音频多模态的。

配置细节在上游 `docs/manual/env.md` 与 `docs/manual/agent.md`（<https://github.com/caca2331/finesub>），本地 references 里没有这两份。

只跑 raw SRT（不传 `--stage`）完全不需要上面任何一项。

## 输出位置

**唯一可信的产物路径是输出里 `完成：` 后面那个**，照抄它，不要自己拼：

```
完成：C:\Users\<你>\AppData\Local\FineSub\tasks\<名字>-<时间戳>-<哈希>\<名字>-raw.srt
```

落点取决于命令怎么写：**输入放在最前面**（`finesub <输入> ...`，也就是上面「用法」那种写法）时归档到 `%LOCALAPPDATA%\FineSub\tasks\<名字>-<时间戳>-<哈希>\`，目录名带时间戳与哈希，**拼不出来**；输入不在最前面时它会提示一句 `writing to the working directory instead`，产物才落到当前目录的 `out/<输入名>/`。

两种落点下的文件名一致：

| 文件 | 说明 |
|---|---|
| `<输入名>-raw.srt` | 未纠错原文 SRT |
| `<输入名>.srt` | **成品 SRT**（纠错翻译 + 后处理） |

## ⚠️ 失败也返回退出码 0

**不要用退出码判断成败。** 跑挂时它只在 stderr 留一串 traceback，退出码照样是 `0`。判据只有一条：输出里有没有 `完成：<路径>` 那一行 —— 没有就是失败，去 stderr 找 traceback，别拿着不存在的路径往下走。

一个实际踩过的例子：报 `processor_config.json is not a valid JSON file`，看着像解析 bug，实际是 `%LOCALAPPDATA%\FineSub\models\huggingface\hub\` 下某个 `models--*` 目录里的文件全是 0 字节（上次下载中断留下的残骸）。把那个目录整个删掉重跑就好。凡是 config 读取失败、报某某文件不是合法 JSON，都先去那里看文件大小。

成品里带置信度标注，低置信行**如实转达给用户**建议人工核对，不要自己判定「应该没问题」。

## 批量

```bash
finesub batch a.wav b.mp4 --stage final-srt --language ja
finesub batch --manifest tasks.jsonl --knowledge update
```

单项失败不影响其余，**重跑即续跑**——所以批量任务里挂了几个，直接原命令重跑，不用挑出来单独处理。

## 环境要求与常见情况

| 阶段 | 需要 |
|---|---|
| 人声分离 + ASR | NVIDIA 显卡（见下）、≥8GB 内存 |
| LLM 纠错翻译 | 无需 GPU；≥4GB 内存 |

**显卡支持范围**

- 支持：RTX 50/40/30/20 系（含 Ti、SUPER、笔记本版）、GTX 1660、GTX 1650，以及 V100 / A100 / H100 —— 显存 ≥4GB
- 不支持：GTX 10 系及更早（1080/1070/1060/1050、GTX 9 系等），以及 AMD、Intel 核显

**看到 stderr 里的 `Warning:` 说回退 CPU** —— 这**不是报错**，字幕照样正确，只是慢很多（人声分离尤其慢）。别去 kill 任务或改参数重跑，**先告诉用户**：长音频这么跑不划算，让他决定要不要继续等。

**显存 4GB 起就够**，更大显存只在人声分离阶段换并行提速，别为了这个劝用户换卡。

**除错**
```bash
finesub --help
```
可以列出

## 和 download_video 的关系

finesub 自己就能吃 URL。但如果用户是要**下回放 + 弹幕再上字幕**，先用本仓库的 `download_video` skill 把影片和弹幕按「实况主/日期/标题」归档下来，再把落地的 mp4 路径喂给 finesub —— 这样弹幕和字幕在同一个目录里，也省得 finesub 重下一遍。
