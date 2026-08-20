---
name: vod_to_sheet
description: 从一条直播回放链接一路做到云端切片表 —— 下载回放与弹幕、生成日文字幕、翻译成中文、分析出高光切片、导成 Excel 并上传腾讯文档。当用户给出直播链接并要求「做切片表」「整理切片素材」「从头到尾走一遍」「做路灯」，或要求把一场直播的高光整理成可分工的表格时使用。
---

# 直播回放 → 云端切片表

串联本仓库四个 skill 的总流程。**优先用 `scripts/run_pipeline.py` 跑**（见下面「用法」），它把四步的调用、路径解析和编码都包好了；手动分步的写法在「分步执行」里，供除错和只跑某一步时参照。

```text
直播链接
  ↓  download_video    下载回放 + 弹幕
 .mp4
  ↓  finesub           ASR 出日文字幕（时间轴 + 原文）
 -raw.srt
  ↓  clip_highlight    翻译 → 高光分析 → 导表
 .xlsx
  ↓  tencent_docs_uploader   上传成在线表格的新子表
 docs.qq.com 链接
```

各步的细节、参数全集、除错方式在各自的 SKILL.md 里，**遇到该步出问题就去读那一份**，别在这里猜。

## 开跑前先问清楚

这条链路很长（长直播可能一两个小时），中途返工代价高。**动手前把这几件事跟用户对齐，缺了就问，不要猜**：

1. **直播链接** —— 必须由用户给。链接不明确时问，不要拿示例链接顶替。
2. **主播是谁、玩什么** —— 决定 `--extra-info` 和知识库效果，也决定表格标题怎么起。
3. **要不要弹幕** —— 默认抓；只要切片表的话加 `--no-chat` 省掉抓弹幕的时间。
4. **上传到哪个腾讯文档** —— 目标表格的凭证配好了没（见 `tencent_docs_uploader/SKILL.md`）。

另外**先告诉用户这活很慢**，尤其 finesub 那步（人声分离 + ASR，长音频动辄几十分钟）。用后台跑，别把会话卡死等它。

## 前置

四个 skill 都靠 uv，**先跑一次**：

```bash
uv --version
```

没有就照 `download_video/SKILL.md` 的说明引导用户安装，别自己闷头装。

另外需要：

- `finesub` CLI（用 `finesub doctor` 检查，**不是** `--version` —— 那个参数无效，会打 usage 并以退出码 2 结束；装法见 `finesub/SKILL.md`）
- `clip_highlight/scripts/.env` 里的 `gemini_api_key`
- `tencent_docs_uploader/config.json` 里的腾讯文档凭证

## 两条贯穿全程的执行规矩

这两条每一步都适用，**先读懂再往下走**，否则会踩出一堆看起来像别的毛病的错。

### `cd` 一律写绝对路径

**开跑前先记下这几个 skill 所在目录的绝对路径**（比如 `E:/kiri_skills/skills`，也就是本 skill 的上一层，四个兄弟 skill 都在里面），下文写 `<REPO>` 的地方就换成它。注意**不是 git 仓库根目录** —— 根目录下只有 `README.md`、`imgs/` 和这个 `skills/`，进错一层每条命令都会找不到脚本。每一步这样进目录：

```bash
cd <REPO>/clip_highlight        # ✅
cd clip_highlight               # ❌ 别这么写
```

原因是 **shell 的当前目录跨命令保留**。上一步 `cd download_video` 之后，下一步再 `cd download_video` 会失败，而且此时去读 `tencent_docs_uploader/config.json` 会报「文件不存在」—— 文件其实好好的，只是你还站在 `download_video` 里。**看到意料之外的 not found，先 `pwd` 确认位置，别急着断定凭证没配。**

`uv run` 的相对路径也以当前目录为准，在别处跑会找不到脚本。跨步传路径时同样**一律用绝对路径**。

### 每条命令都要带 UTF-8

Windows 终端默认是 cp950 / cp936，本流程从头到尾都在处理中文和日文，不设编码会拿到 `�F������` 这种乱码：

```bash
export PYTHONIOENCODING=utf-8      # bash
$env:PYTHONIOENCODING = "utf-8"    # PowerShell
```

下文每条命令都已经带上。**看到乱码就是这里没设，不要照着乱码猜主播名或标题继续跑。**

## 用法：一条命令跑完

```bash
cd <REPO>/vod_to_sheet
uv run scripts/run_pipeline.py \
  --link "<直播链接>" \
  --name 20260326_haru \
  --extra-info "VTuber 東雲はる（Haru）的日文杂谈直播"
```

`--name` 自己起一个干净的短名（日期_主播）。**别用 mp4 原名** —— 它带方括号和空格，后面每一步的路径都会很难处理。这个名字会一路带到最终的表格文件名。

**默认跑到 xlsx 就停，不上传。** 上传是这条链路里唯一不可逆的动作（子表标题建完改不了、撞名直接被拒、只能排在最右边），所以要先核对表格再显式上传：

```bash
uv run scripts/run_pipeline.py --name 20260326_haru --only upload
```

想一次到底就加 `--upload`。

**常用参数**

| 参数 | 说明 |
|---|---|
| `--link` | 直播链接。**由用户给，不明确时问，别拿示例链接顶替** |
| `--name` | 短名，决定 SRT 名与输出目录名 |
| `--no-chat` | 只下影片，不抓弹幕（省下抓弹幕的时间） |
| `--extra-info` | 传给 finesub 的背景信息，主播名/游戏名/专名，显著提升纠错准确率 |
| `--gpu-budget-gb` | 显存够就传 `8` |
| `--from <步骤>` | 从这一步开始跑 |
| `--only <步骤>` | 只跑这一步 |
| `--force` | 产物已存在也重跑 |
| `--upload` / `--title` | 上传，及自定义子表标题（默认 `【<日期>】<实况主>`） |

步骤名：`download` `asr` `translate` `analysis` `excel` `upload`

### 断点续跑

每步跑完就把状态写进 `runs/<名字>/state.json`，**产物已存在的步骤自动跳过**。所以中途挂了直接原命令重跑即可，几十分钟的 ASR 不会白跑第二遍。要强制重来加 `--force`。

### 读 state.json，不要解析日志

跑完后所有路径都在 `runs/<名字>/state.json` 里：

```json
{
  "name": "20260326_haru",
  "media": "...\\[youtube][20260326][Haru] 【謝罪会見】.mp4",
  "date": "20260326",
  "streamer": "Haru",
  "raw_srt": "...\\FineSub\\tasks\\20260326_haru-260820-1349-a87b12\\20260326_haru-raw.srt",
  "zh_srt": "...", "analysis": "...", "rows_json": "...", "xlsx": "...",
  "notices": { "asr": ["..."], "translate": ["..."] }
}
```

**要哪个路径就从这里读**，别去日志里抠 —— 那正是这个脚本要消灭的事。

`notices` 收的是各步骤报出的 `[Warning]` / `[Error]` / ASR 摘要，脚本收尾时也会打印一遍。**原样转达给用户**，不要自行判定「应该没问题」。

### 退出码

| 码 | 含义 |
|---|---|
| `0` | 成功 |
| `1` | 某一步失败，错误信息会说明停在哪、怎么接着跑 |
| `2` | 参数不对 |
| `3` | **需要人拿主意**（比如认不出实况主），脚本不替你猜 |

### 跑完还要做的事

脚本不替你做这三件：

1. **核对表格** —— 尤其是最后一行的结束时间有没有超过片长，理由见下面第 3 步的说明
2. **决定要不要上传**
3. **把四样产物的位置报给用户** —— 见下

#### 收尾必须报全四样，只给表格链接不算交付

**光给 docs.qq.com 链接是不够的。** 表格里只有时间码和标题，拿着它没法开工：剪辑要 mp4 才能下刀，核对台词要中文 SRT，捕捉语气和造梗要日文原文 SRT。用户不该再回头问你「片子在哪」。

所以每次收尾**固定报这四样**，路径从 `runs/<名字>/state.json` 读，**写绝对路径**，别写 `outputs/...` 这种相对路径 —— 用户的终端不一定站在哪：

| 报什么 | state.json 字段 |
|---|---|
| 切片表链接 | 上传那步输出的 `Done: https://docs.qq.com/...`（没上传就说明只有本地 xlsx，并给 `xlsx` 路径） |
| 回放 mp4 | `media` |
| 中文字幕 SRT | `zh_srt` |
| 日文字幕 SRT | `raw_srt` |

`analysis` 和 `rows_json` 属于中间产物，用户问起再给，不用主动列。

写成表格，别塞进一段话里 —— 这几个路径又长又带方括号和中日文，混在散文里没法复制：

```markdown
| 产物 | 位置 |
|---|---|
| 切片表 | https://docs.qq.com/sheet/<FILE_ID>?tab=<sheetId> |
| 回放 mp4 | E:\...\[youtube][20260326][Haru] 【謝罪会見】.mp4 |
| 中文字幕 | E:\...\20260326_haru-raw.zh.srt |
| 日文字幕 | C:\Users\<你>\AppData\Local\FineSub\tasks\<名字>-<时间戳>-<哈希>\<名字>-raw.srt |
```

日文 SRT 那条尤其要写全 —— 它躺在 `%LOCALAPPDATA%` 下带时间戳和哈希的目录里，**用户自己翻不到**。

另外**报完路径再报 `notices`**，两者都要有，别拿其中一个顶替另一个。

## 分步执行

以下是脚本内部实际做的事。**只在除错、或想单独跑某一步时才需要手动敲**；正常情况用上面的 `run_pipeline.py`。

### 1. 下载回放

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

### 2. 出日文字幕（时间轴 + 原文）

```bash
export PYTHONIOENCODING=utf-8
finesub "<mp4 绝对路径>" --language ja --name <名字>
```

#### 产物路径只能从输出里读，不要自己拼

成功时最后几行长这样，**`完成：` 后面那个路径就是唯一可信的产物位置**：

```
完成：C:\Users\<你>\AppData\Local\FineSub\tasks\<名字>-<时间戳>-<哈希>\<名字>-raw.srt
总耗时：1m 58s
```

注意目录名带**时间戳和哈希后缀，拼不出来也猜不到**。source 参数放在最前面时 finesub 就归档到 `%LOCALAPPDATA%\FineSub\tasks\` 下；`out/<名字>/` 这个路径在这种调用方式下**根本不存在**，别去那里找。

#### ⚠️ finesub 失败也返回退出码 0

**不要用退出码判断成败**。它失败时只在 stderr 留一串 traceback，退出码照样是 `0`。判据只有一条：

- 输出里有 `完成：<路径>` → 成功，用那个路径
- 没有这一行 → **失败**，去 stderr 找 traceback，不要往下一步走

一个实际发生过的例子：报 `processor_config.json is not a valid JSON file`，看起来像解析 bug，实际是 `%LOCALAPPDATA%\FineSub\models\huggingface\hub\` 下某个模型目录的文件全是 0 字节（上次下载中断的残骸）。把那个 `models--*` 目录整个删掉重跑即可。

若无视这一条，下一步会拿着一个不存在的 SRT 路径去跑 `translate.py`，然后收到一个语焉不详的 not found —— 排查方向从一开始就偏到 clip_highlight 上了。

**关键：不要传 `--stage final-srt`。** 这里只要 ASR 原文，中文翻译由下一步的 clip_highlight 负责 —— 它带着专属知识库和逐条校验，质量更可控。raw 阶段不调 LLM，所以**不花任何 API 额度**。

`--name` 自己起一个干净的短名（比如 `20260819_haru`）。mp4 原名带方括号和空格，直接用会让后面每一步的路径都很难处理。这个名字会一路带到最终的表格文件名。

看到 stderr 里 `Warning:` 说回退 CPU **不是报错**，字幕照样对，只是慢很多 —— 先告诉用户，让他决定要不要继续等。

### 3. 翻译 + 高光分析 + 导表

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

#### 出表后核一眼时间轴

看一下最后一行的**结束时间有没有超过片长**。模型偶尔会把 `00:21:43` 写成 `02:43`，到导表这步又被补成形状完全合法的 `02:43:00` —— 一场 22 分钟的直播，表格里躺着一个 2 小时 43 分。格式上挑不出毛病，只能靠这一眼。

要修就改 `rows.json` 里那一格，然后**不重跑模型**地重出表格：

```bash
uv run scripts/to_excel.py --from-json outputs/<名字>-raw/<名字>-raw.rows.json --sheet-date <日期>
```

别用重跑 `to_excel.py` 的方式修 —— 那会让模型把没问题的行也一并重出，改一格却动了整张表。

#### ⚠️ 改 md / 产物文件前必须先问用户

`outputs/` 下的 `.analysis.md`、`.zh.srt`、`.rows.json`，以及 `assets/` 下的各种 `*_prompt.md` 和知识库，**都是交付物或用户的配置，不是你的草稿纸**。

**动它们之前一律先问用户，说清楚要改哪个文件、改哪一处、为什么。** 得到同意再改。

- 发现分析里有错 → **先报告，问要不要改**，不要顺手改完再说
- 想换一套提示词 → 路径写死在脚本里，没有参数可传，换用就得**覆盖** `assets/analysis_prompt.md` 之类的文件，**这是在改用户的配置，必须先问**，并说明跑完要不要还原
- 只是想让表格好看点 → 那就别改，交给用户在腾讯文档里编辑

### 4. 上传腾讯文档

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

这张表是给你查位置用的，**不是交给用户的格式** —— 里面都是带占位符的目录模式。收尾报给用户的必须是 `state.json` 里的绝对路径，见上面「收尾必须报全四样」。

## 只跑其中几步

各步彼此独立，用文件交接，所以可以从任意一步切入。用脚本的话就是 `--from` / `--only`；素材是外来的（不是本流程产的）就得手动敲那一步的命令，因为 `state.json` 里没有它的路径：

| 情况 | 怎么做 |
|---|---|
| 已经有 mp4（本流程下的） | `--from asr` |
| 已经有 mp4（外来的） | 手动跑第 2 步，再 `--from translate` |
| 已经有日文 SRT（外来的） | 手动跑第 3 步的三条命令 |
| 只要中文字幕不要切片表 | `--only translate` |
| 表格已有要重传 | `--only upload --title <新标题>` |

## 出问题去哪查

| 症状 | 去读 |
|---|---|
| 脚本退出码 `3` | 需要人拿主意，看它打出的那段说明；常见是认不出实况主 |
| 不知道某个产物在哪 | 读 `runs/<名字>/state.json`，别去日志里抠 |
| 输出是 `�F������` 一类乱码 | 上面「每条命令都要带 UTF-8」（用脚本的话它已经处理好） |
| 文件明明在却报 not found | 上面「`cd` 一律写绝对路径」，先 `pwd` |
| finesub 退出码 0 但找不到 SRT | 第 2 步的「finesub 失败也返回退出码 0」 |
| 表格里的时间超过片长 | 第 3 步的「出表后核一眼时间轴」 |
| 下载失败、要凭证、认不出实况主 | `download_video/SKILL.md` |
| ASR 慢、回退 CPU、显卡不支持 | `finesub/SKILL.md` |
| 翻译漏条、时间戳越界、术语译错 | `clip_highlight/SKILL.md` 与 `clip_highlight/references/lessons.md` |
| 上传被拒、子表撞名、格数超限 | `tencent_docs_uploader/SKILL.md` 与其 `references/api-notes.md` |
