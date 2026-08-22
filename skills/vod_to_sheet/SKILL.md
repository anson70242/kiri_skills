---
name: vod_to_sheet
description: 从一条直播回放链接一路做到云端切片表 —— 下载回放与弹幕、生成日文字幕、翻译成中文、分析出高光切片、导成 Excel 并上传腾讯文档。当用户给出直播链接并要求「做切片表」「整理切片素材」「从头到尾走一遍」「做路灯」，或要求把一场直播的高光整理成可分工的表格时使用。
---

# 直播回放 → 云端切片表

串联本仓库四个 skill 的总流程。**优先用 `scripts/run_pipeline.py` 跑**（见下面「用法」），它把四步的调用、路径解析和编码都包好了；手动分步的写法在 [references/manual-steps.md](references/manual-steps.md)，供除错和只跑某一步时参照。

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
3. **要不要弹幕** —— 默认抓；只要切片表的话也要下弹幕。
4. **上传到哪个腾讯文档** —— 凭证和 `file_id` 配好了没，见下面「凭证：动手前先查，缺了先补」。

另外**先告诉用户这活很慢**，尤其 finesub 那步（人声分离 + ASR，长音频动辄几十分钟）。用后台跑，别把会话卡死等它。

## 前置

四个 skill 都靠 uv，**先跑一次**：

```bash
uv --version
```

没有就照 `download_video/SKILL.md` 的说明引导用户安装，别自己闷头装。

另外需要：

- `finesub` CLI（用 `finesub doctor` 检查，**不是** `--version` —— 那个参数无效，会打 usage 并以退出码 2 结束；装法见 `finesub/SKILL.md`）
- 两份凭证档案，见下

### 凭证：动手前先查，缺了先补

**开跑第一件事是查这两个档案，缺哪个先协助用户补上，补齐前不要启动流程。** 两个都在 `.gitignore` 里，clone 下来是没有的；跑到翻译那步才发现没 key，前面几十分钟的 ASR 就白等了。

```bash
cd <REPO>
cat clip_highlight/scripts/.env          # gemini_api_key 有没有值
cat tencent_docs_uploader/config.json    # 四个值有没有填、是不是还留着 <...> 占位符
```

| 缺哪个 | 怎么补 |
|---|---|
| `clip_highlight/scripts/.env` 的 `gemini_api_key`（其余项有默认值，别动） | 先 `cp` 同目录的 `.env.example`，再请用户去 https://aistudio.google.com/apikey 取 key 给你 |
| `tencent_docs_uploader/config.json` 的 `access_token` / `client_id` / `open_id` | 先 `cp` 同目录的 `config.example.json`，再**把 https://docs.qq.com/open/document/app/get_started.html 整份丢给用户，请他从头看完再来配** —— 这三个值要先在开放平台建应用、走授权才拿得到，不是问一句就有的东西，别一项项跟他挤。**也别自己转述流程步骤**，平台接入方式会变，照文档走才不会错 |
| `config.json` 的 `file_id` | 就是目标表格 URL `https://docs.qq.com/sheet/<FILE_ID>` 里那段，让用户把链接贴给你即可 |

另外几条：

- **凭证只能由用户给**，别去别处翻、更别编一个填进去。
- **腾讯 token 约 30 天过期**，档案存在不等于能用。它是 JWT，先解出 `exp` 对一下今天；过期了让用户重取，否则上传会收到 `API error 400006: Authentication Internal Error`：

  ```bash
  python -c "import json,base64,datetime;t=json.load(open('tencent_docs_uploader/config.json'))['access_token'];p=t.split('.')[1]+'==';print(datetime.datetime.fromtimestamp(json.loads(base64.urlsafe_b64decode(p))['exp']))"
  ```
- **`file_id` 里已经有值也要跟用户确认是不是这次要传的那份**，不是就换掉，或上传时用 `--file-id` 临时覆盖。
- 这次只要本地 xlsx、不上传的话，腾讯那份可以先不配 —— 但要**明说「跑完只有本地表格，要上传得先配凭证」**，别默默跳过。

## 两条贯穿全程的执行规矩

每一步都适用，**先读懂再往下走**，否则会踩出一堆看起来像别的毛病的错。

**1. `cd` 一律写绝对路径。** 开跑前先记下四个兄弟 skill 所在目录的绝对路径（比如 `E:/kiri_skills/skills`，也就是本 skill 的上一层；**不是 git 仓库根目录** —— 根目录下只有 `README.md`、`imgs/` 和这个 `skills/`，进错一层每条命令都找不到脚本），下文 `<REPO>` 就换成它：`cd <REPO>/clip_highlight` ✅，`cd clip_highlight` ❌。原因是 **shell 的当前目录跨命令保留** —— 上一步 `cd download_video` 之后再 `cd download_video` 会失败，而且此时读 `tencent_docs_uploader/config.json` 会报「文件不存在」，文件其实好好的，只是你还站在 `download_video` 里。**看到意料之外的 not found，先 `pwd` 确认位置，别急着断定凭证没配。** `uv run` 的相对路径同理，跨步传路径也一律用绝对路径。

**2. 每条命令都要带 UTF-8。** Windows 终端默认 cp950 / cp936，本流程从头到尾都在处理中文和日文，不设编码会拿到 `�F������` 这种乱码 —— `export PYTHONIOENCODING=utf-8`（bash）/ `$env:PYTHONIOENCODING = "utf-8"`（PowerShell）。下文命令都已带上。**看到乱码就是这里没设，不要照着乱码猜主播名或标题继续跑。**

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

1. **核对表格** —— 尤其是最后一行的结束时间有没有超过片长（理由见 `references/manual-steps.md` 的「出表后核一眼时间轴」）
2. **决定要不要上传**
3. **把四样产物的位置报给用户** —— 见下

#### 收尾必须报全四样，只给表格链接不算交付

**光给 docs.qq.com 链接是不够的。** 表格里只有时间码和标题，拿着它没法开工：剪辑要 mp4 才能下刀，核对台词要中文 SRT，捕捉语气和造梗要日文原文 SRT。用户不该再回头问你「片子在哪」。

所以每次收尾**固定报这四样**，路径从 `runs/<名字>/state.json` 读，**写绝对路径**（用户的终端不一定站在哪），并**写成表格**别塞进一段话里 —— 这几个路径又长又带方括号和中日文，混在散文里没法复制：

| 报什么 | 取自 state.json |
|---|---|
| 切片表链接 | 上传那步输出的 `Done: https://docs.qq.com/sheet/<FILE_ID>?tab=<sheetId>`；没上传就说明只有本地 xlsx，并给 `xlsx` 路径 |
| 回放 mp4 | `media`，形如 `E:\...\[youtube][20260326][Haru] 【謝罪会見】.mp4` |
| 中文字幕 SRT | `zh_srt` |
| 日文字幕 SRT | `raw_srt` —— 躺在 `%LOCALAPPDATA%\FineSub\tasks\` 下带时间戳和哈希的目录里，**用户自己翻不到，务必写全** |

`analysis` 和 `rows_json` 属于中间产物，用户问起再给，不用主动列。另外**报完路径再报 `notices`**，两者都要有，别拿其中一个顶替另一个。

## 手动分步执行

脚本内部实际做的四步命令、每一步的产物路径规则、以及各步特有的坑（finesub 失败也返回退出码 0、出表后要核时间轴、改产物文件前先问用户……），加上一张各产物分布在哪个目录的总表，都在 [references/manual-steps.md](references/manual-steps.md)。**只在除错或想单独跑某一步时才需要它**。

## 只跑其中几步

各步彼此独立，用文件交接，所以可以从任意一步切入。用脚本的话就是 `--from` / `--only`；素材是外来的（不是本流程产的）就得手动敲那一步的命令，因为 `state.json` 里没有它的路径：

| 情况 | 怎么做 |
|---|---|
| 已经有 mp4（本流程下的） | `--from asr` |
| 已经有 mp4（外来的） | 照 `references/manual-steps.md` 手动跑第 2 步，再 `--from translate` |
| 已经有日文 SRT（外来的） | 照 `references/manual-steps.md` 手动跑第 3 步的三条命令 |
| 只要中文字幕不要切片表 | `--only translate` |
| 表格已有要重传 | `--only upload --title <新标题>` |

## 出问题去哪查

| 症状 | 去读 |
|---|---|
| 脚本退出码 `3` | 需要人拿主意，看它打出的那段说明；常见是认不出实况主 |
| 不知道某个产物在哪 | 读 `runs/<名字>/state.json`，别去日志里抠 |
| 输出是 `�F������` 一类乱码 | 上面「每条命令都要带 UTF-8」（用脚本的话它已经处理好） |
| 文件明明在却报 not found | 上面「`cd` 一律写绝对路径」，先 `pwd` |
| finesub 退出码 0 但找不到 SRT | `references/manual-steps.md` 的「finesub 失败也返回退出码 0」 |
| 表格里的时间超过片长 | `references/manual-steps.md` 的「出表后核一眼时间轴」 |
| 下载失败、要凭证、认不出实况主 | `download_video/SKILL.md` |
| ASR 慢、回退 CPU、显卡不支持 | `finesub/SKILL.md` |
| translate / analysis 一启动就报清不掉 `tmp/` | 平台的 safe-delete 沙箱拦了删除，设 `CODEBUDDY_SAFE_DELETE_SANDBOX=0` 或手动清空 `tmp/`；`dangerouslyDisableSandbox` 挡不住它。详见 `clip_highlight/SKILL.md` 的「清不掉 tmp/」 |
| 翻译漏条、时间戳越界、术语译错 | `clip_highlight/SKILL.md` 与 `clip_highlight/references/lessons.md` |
| 上传被拒、子表撞名、格数超限 | `tencent_docs_uploader/SKILL.md` 与其 `references/api-notes.md` |
