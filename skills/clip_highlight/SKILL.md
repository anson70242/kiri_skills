---
name: clip_highlight
description: 把日语直播字幕 (SRT) 翻译成中文字幕，再分析出高光切片时间轴，最后导出成剪辑用的 Excel 工作表。当用户要求翻译直播字幕、找切片素材/高能点、生成切片时间轴，或把直播记录整理成表格时使用。
---

# 直播字幕翻译与高光切片分析

三步流水线，每步产物独立，可以只跑其中一步。

## 前置：确认 uv 装了没

本 skill 靠 uv 安装和管理环境，所以**动手前先跑一次**：

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

## 前置：填 API key

凭证放在 `scripts/.env`，**这个档案在 `.gitignore` 里，不会进版本库**。第一次用先复制模板：

```bash
cp scripts/.env.example scripts/.env
```

然后填 `gemini_api_key`（从 https://aistudio.google.com/apikey 取得）。其余项有默认值，不用动。

## 用法

以下命令都在 `clip_highlight/` 目录下执行。示例用 `test.srt`，换成实际的日语 SRT 即可。

### 1. 翻译：日语 SRT → 中文 SRT

```bash
uv run scripts/translate.py test.srt --knowledge assets/knowledge/finesub_kb.md
```

按 200 条一批切分翻译，**每批翻完立刻落盘**到 `tmp/translated_srts/`。

**启动时会清空 `tmp/`**，所以每次都是干净重跑。中途失败（断网、限流退避耗尽）想接着上次继续，加 `--resume` —— 它会保留 `tmp/` 并跳过已翻好的分片，不重复烧 API。

耗时参考：2 小时直播约 2.5 分钟。

### 2. 分析：找出高光切片

```bash
uv run scripts/analysis.py test.srt --knowledge assets/knowledge/finesub_kb.md
```

自动读取第 1 步产出的中文 SRT（`outputs/<名字>/<名字>.zh.srt`），拼成中日对照后按 800 条切分分析。译文用于快速理解，日文原文用于捕捉译文会碾平的语气与造梗。

**启动时同样会清空 `tmp/`**。译文放在别处的话用 `--translated <路径>` 指定。耗时约 25 秒。

### 3. 导表：分析记录 → JSON + Excel

```bash
uv run scripts/to_excel.py outputs/test/test.analysis.md
```

JSON 解析失败时会把报错回送给模型重出，最多 2 轮。直播日期用 `--sheet-date 20260819` 指定，不给就用当天日期。耗时约 15 秒。

作为流水线最后一步，**跑完会清空 `tmp/`**。

出表后**核一眼最后一行的结束时间有没有超过片长**。模型偶尔把 `00:21:43` 写成 `02:43`，到这一步会被补成形状完全合法的 `02:43:00`，格式上挑不出毛病、值却是片长的好几倍。`analysis.py` 现在会对这种畸形时间戳报 `[Warning] ... malformed timestamp(s)`，但那只是告警，最终还得你看一眼。

### 修表：改一格而不惊动整张表

```bash
uv run scripts/to_excel.py --from-json outputs/test/test.rows.json --sheet-date 20260819
```

改完 `rows.json` 里那一格就跑这个，**跳过模型直接重出 xlsx**。不调 API，因此也不需要 API key；`--from-json` 是事后修表，不会清 `tmp/`。

别用重跑 `to_excel.py <analysis.md>` 的方式修 —— 那会让模型把没问题的行也一并重出，改一格却动了整张表，反而更难对。

### 单独切分 SRT

```bash
uv run scripts/preprocess.py test.srt --max-blocks 800
```

### 清空中间产物

```bash
uv run scripts/clear_tmp.py
```

## 产物在哪

**交付物**在 `outputs/<SRT名字>/` 下，每场直播一个子目录：

| 文件 | 来自 | 内容 |
|---|---|---|
| `<名字>.zh.srt` | 第 1 步 | 中文字幕，时间轴与源文件逐字节相同 |
| `<名字>.analysis.md` | 第 2 步 | 模块一时间轴 + 模块二高能切片素材库 |
| `<名字>.rows.json` | 第 3 步 | 结构化数据，六个栏位 |
| `<名字>.xlsx` | 第 3 步 | 剪辑用工作表，「剪辑」栏留空给组员填 |

**中间产物**在 `tmp/` 下，可随时删：`tmp/srts/`（切好的分片）、`tmp/translated_srts/`（翻译断点）、`tmp/bilingual/`（中日对照）。

`outputs/` 和 `tmp/` 都在 `.gitignore` 里。

## ⚠️ 改 md / 产物文件前必须先问用户

`outputs/` 下的 `.analysis.md`、`.zh.srt`、`.rows.json`，以及 `assets/` 下的各种 `*_prompt.md` 和知识库，**都是交付物或用户的配置，不是你的草稿纸**。

**动它们之前一律先问用户**，说清楚要改哪个文件、改哪一处、为什么，得到同意再改。

- 发现分析里有错 → **先报告，问要不要改**，不要顺手改完再说
- 想换提示词 → 见下面「改提示词」，路径是写死的，换用就得覆盖生效文件，**这是在改用户的配置**
- 只是嫌表格不好看 → 那就别改，交给用户自己编辑

## 改提示词

提示词路径**写死在脚本里**，没有 `--prompt` 之类的参数可传，所以「换一套提示词」实际等于「覆盖掉下面这几个文件」—— 这是在改用户的配置，**先问过再动**，并说明跑完要不要还原。

- `assets/translate_prompt.md` —— 翻译规则
- `assets/analysis_prompt.md` —— 分析规则与切片雷达
- `assets/to_excel/excel_prompt.md` —— 导表栏位定义
- `assets/knowledge/finesub_kb.md` —— 人名/角色/术语的权威译法，`--knowledge` 传的就是它

改之前先读 `references/lessons.md`，里面记了 17 条实测踩坑，包括几个反直觉的（比如给模型时间范围反而会让它输出更差）。
