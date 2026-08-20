---
name: tencent-docs-uploader
description: 把本地 Excel (.xlsx) 上传成腾讯在线文档（docs.qq.com）表格里的一个新子表。当用户要求把表格/数据上传到腾讯文档、同步到在线表格、或提到 docs.qq.com 的 spreadsheet 时使用。
---

# 腾讯文档表格上传

读本地 `.xlsx`，在云端表格里新建一个子表并把内容逐格写进去。

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

## 前置：填凭证

凭证放在 `config.json`，**这个档案在 `.gitignore` 里，不会进版本库**。第一次用先复制模板：

```bash
cp config.example.json config.json
```

然后填四个值：

```json
{
  "access_token": "...",
  "client_id": "...",
  "open_id": "...",
  "file_id": "..."
}
```

Access token 取得方法见[腾讯文档开放平台](https://docs.qq.com/open/document/app/get_started.html)。平台直发的 token **约 30 天过期**，过期后所有请求会返回 `API error 400006: Authentication Internal Error`，重新取一个填回去即可。

`file_id` 是目标文档，就是表格 URL `https://docs.qq.com/sheet/<FILE_ID>` 里那一段。**四个值缺一个脚本就会当场退出并指名是哪个**，不会跑到一半才失败。

要临时传到别的文档，用 `--file-id` 覆盖，不必改 config：

```bash
uv run scripts/upload_to_qqdocs.py --sheet <xlsx> --file-id <另一个 FILE_ID>
```

**别把 `file_id` 写回脚本里。** 它跟 token 一样属于「指向你自己文档」的信息，硬编码就会跟着代码进版本库；放 config.json 才在 `.gitignore` 的保护范围内。

## 使用

```bash
uv run scripts/upload_to_qqdocs.py --sheet <path_to_xlsx>
uv run scripts/upload_to_qqdocs.py --sheet data.xlsx --title 【20260819】某某直播
```

| 参数 | 说明 |
|---|---|
| `--sheet` | 必填，本地 `.xlsx` 路径 |
| `--title` | 子表名称，不给就用档名（`data.xlsx` → `data`） |

跑完最后一行会输出直达链接：

```
Done: https://docs.qq.com/sheet/<FILE_ID>?tab=<sheetId>
```

**建议把这个链接给用户** —— 新子表排在最右边（原因见下），带 `?tab=` 的链接点开会直接落在新表上，省得手动找。

## 重点限制

以下三条会直接影响你怎么回覆用户，**都是 API 硬限制，不是代码能绕过的**：

- **新子表只能排在最后**，v3 没有移动/排序接口。要放最左边只能在浏览器里手动拖 —— 所以把 `?tab=` 链接给用户比较实际。
- **子表标题建完就改不了**，没有 rename 接口。脚本会先查重名，撞名直接拒绝并提示改 `--title`。
- **单表上限 10000 格**，26 列时最多 384 行。数据更长要拆档上传。

完整的限制说明、错误讯息对照表、以及实测确认的 API endpoint 与响应结构，见 [references/api-notes.md](references/api-notes.md)。
