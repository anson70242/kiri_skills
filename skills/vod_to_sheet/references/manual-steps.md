# 手动分步执行 & 产物分布

`run_pipeline.py` 内部实际做的事，一步一条命令。**只在除错、或想单独跑某一步、或素材是外来的（不是本流程产的、`state.json` 里没有路径）时才需要手动敲**；正常情况回 `SKILL.md` 用脚本。

每条命令都带着 `export PYTHONIOENCODING=utf-8`，别省（理由见 `SKILL.md` 的「每条命令都要带 UTF-8」）。`<REPO>` 换成四个 skill 所在目录的绝对路径，别写相对路径（同上，「`cd` 一律写绝对路径」）。

---

## 1. 下载回放

```bash
cd <REPO>/download_video
export PYTHONIOENCODING=utf-8
uv run scripts/video_chat.py --link <直播链接>     # 影片 + 弹幕
uv run scripts/down_video.py --link <直播链接>     # 只要影片
```

产物：

```
videos/<实况主>/<日期>/<标题>_[<video_id>]/
├── [平台][日期][实况主] 标题.mp4
└── [平台][日期][实况主] 标题_chat_parsed.json
```

**记下这三样，后面每一步都要用**：mp4 的绝对路径、`<日期>`、`<实况主>`。

识别不到实况主会中止并归入 `Unknown`；先读该 skill 的「识别到 Unknown」再决定要不要加 `--yes`。

## 2. 出日文字幕（时间轴 + 原文）

```bash
export PYTHONIOENCODING=utf-8
finesub "<mp4 绝对路径>" --language ja --name <名字>
```

### 产物路径只能从输出里读，不要自己拼

成功时最后几行长这样，**`完成：` 后面那个路径就是唯一可信的产物位置**：

```
完成：C:\Users\<你>\AppData\Local\FineSub\tasks\<名字>-<时间戳>-<哈希>\<名字>-raw.srt
总耗时：1m 58s
```

注意目录名带**时间戳和哈希后缀，拼不出来也猜不到**。source 参数放在最前面时 finesub 就归档到 `%LOCALAPPDATA%\FineSub\tasks\` 下；`out/<名字>/` 这个路径在这种调用方式下**根本不存在**，别去那里找。

### ⚠️ finesub 失败也返回退出码 0

**不要用退出码判断成败**。它失败时只在 stderr 留一串 traceback，退出码照样是 `0`。判据只有一条：

- 输出里有 `完成：<路径>` → 成功，用那个路径
- 没有这一行 → **失败**，去 stderr 找 traceback，不要往下一步走

一个实际发生过的例子：报 `processor_config.json is not a valid JSON file`，看起来像解析 bug，实际是 `%LOCALAPPDATA%\FineSub\models\huggingface\hub\` 下某个模型目录的文件全是 0 字节（上次下载中断的残骸）。把那个 `models--*` 目录整个删掉重跑即可。

若无视这一条，下一步会拿着一个不存在的 SRT 路径去跑 `translate.py`，然后收到一个语焉不详的 not found —— 排查方向从一开始就偏到 clip_highlight 上了。

**关键：不要传 `--stage final-srt`。** 这里只要 ASR 原文，中文翻译由下一步的 clip_highlight 负责 —— 它带着专属知识库和逐条校验，质量更可控。raw 阶段不调 LLM，所以**不花任何 API 额度**。

`--name` 自己起一个干净的短名（比如 `20260819_haru`）。mp4 原名带方括号和空格，直接用会让后面每一步的路径都很难处理。这个名字会一路带到最终的表格文件名。

看到 stderr 里 `Warning:` 说回退 CPU **不是报错**，字幕照样对，只是慢很多 —— 先告诉用户，让他决定要不要继续等。

## 3. 翻译 + 高光分析 + 导表

```bash
cd <REPO>/clip_highlight
export PYTHONIOENCODING=utf-8
uv run scripts/translate.py <raw.srt 绝对路径> --knowledge assets/knowledge/finesub_kb.md
uv run scripts/analysis.py  <raw.srt 绝对路径> --knowledge assets/knowledge/finesub_kb.md
uv run scripts/to_excel.py  outputs/<名字>-raw/<名字>-raw.analysis.md --sheet-date <日期>
```

三条必须按顺序跑，后一条吃前一条的产物。产物都在 `clip_highlight/outputs/<名字>-raw/` 下：

| 文件 | 内容 |
|---|---|
| `<名字>-raw.zh.srt` | 中文字幕，时间轴与 raw SRT 逐字节相同 |
| `<名字>-raw.analysis.md` | 高光切片分析 |
| `<名字>-raw.xlsx` | **要上传的就是它** |

目录名里带 `-raw` 是因为它跟着输入档名走（`<名字>-raw.srt`）。嫌难看的话，第 2 步之后把 SRT 改名再进这一步。

`--sheet-date` 传第 1 步记下的 `<日期>`，8 位数字。不传会用当天日期，跟直播日期对不上。

留意终端里的 `[Error]` / `[Warning]`：翻译未覆盖的条目、分析畸形或越界的时间戳都会当场报出来，**如实转达给用户**，不要自行判定「应该没问题」。

### 出表后核一眼时间轴

看一下最后一行的**结束时间有没有超过片长**。模型偶尔会把 `00:21:43` 写成 `02:43`，到导表这步又被补成形状完全合法的 `02:43:00` —— 一场 22 分钟的直播，表格里躺着一个 2 小时 43 分。格式上挑不出毛病，只能靠这一眼。

要修就改 `rows.json` 里那一格，然后**不重跑模型**地重出表格：

```bash
uv run scripts/to_excel.py --from-json outputs/<名字>-raw/<名字>-raw.rows.json --sheet-date <日期>
```

别用重跑 `to_excel.py` 的方式修 —— 那会让模型把没问题的行也一并重出，改一格却动了整张表。

### ⚠️ 改 md / 产物文件前必须先问用户

`outputs/` 下的 `.analysis.md`、`.zh.srt`、`.rows.json`，以及 `assets/` 下的各种 `*_prompt.md` 和知识库，**都是交付物或用户的配置，不是你的草稿纸**。

**动它们之前一律先问用户，说清楚要改哪个文件、改哪一处、为什么。** 得到同意再改。

- 发现分析里有错 → **先报告，问要不要改**，不要顺手改完再说
- 想换一套提示词 → 路径写死在脚本里，没有参数可传，换用就得**覆盖** `assets/analysis_prompt.md` 之类的文件，**这是在改用户的配置，必须先问**，并说明跑完要不要还原
- 只是想让表格好看点 → 那就别改，交给用户在腾讯文档里编辑

## 4. 上传腾讯文档

```bash
cd <REPO>/tencent_docs_uploader
export PYTHONIOENCODING=utf-8
uv run scripts/upload_to_qqdocs.py --sheet <xlsx 绝对路径> --title 【<日期>】<实况主>
```

最后一行会输出直达链接，**把它给用户**：

```
Done: https://docs.qq.com/sheet/<FILE_ID>?tab=<sheetId>
```

三条硬限制（API 层面，代码绕不过）：

- **子表标题建完改不了**，撞名会被直接拒绝 —— 所以标题里务必带日期。
- **新子表只能排在最右边**，没有排序接口。
- **单表上限 10000 格**；本表 6 列，约 1600 行封顶。一般一场直播十几到几十行，够用；真超了要拆档。

## 产物汇总

准确路径以 `runs/<名字>/state.json` 为准。大致分布在三个 skill 目录下：

| 位置 | 内容 |
|---|---|
| `download_video/videos/<实况主>/<日期>/<标题>_[<id>]/` | 回放 mp4、弹幕 JSON、原始链接 |
| `%LOCALAPPDATA%\FineSub\tasks\<名字>-<时间戳>-<哈希>\` | 日文 raw SRT（准确路径见第 2 步 `完成：` 那行） |
| `clip_highlight/outputs/<名字>-raw/` | 中文 SRT、分析记录、JSON、xlsx |
| 腾讯文档 | 在线子表 |

`clip_highlight/tmp/` 是中间产物，`to_excel.py` 跑完会自动清掉。

这张表是给你查位置用的，**不是交给用户的格式** —— 里面都是带占位符的目录模式。收尾报给用户的必须是 `state.json` 里的绝对路径，见 `SKILL.md` 的「收尾必须报全四样」。
