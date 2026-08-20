# 腾讯文档 v3 表格 API 备忘

官方文档站是 SPA，搜索引擎抓不到内容，以下全部是实测确认的结果。

## 已知限制

这些是腾讯 v3 API 的硬限制，**不是代码能绕过的**，遇到时直接告诉用户，别尝试变通：

**新子表只能排在最后。** v3 的 `batchUpdate` 只支持 4 种操作 —— `addSheetRequest`、`deleteSheetRequest`、`updateRangeRequest`、`deleteDimensionRequest`。没有移动、排序的接口，建表时给 `index` 参数会被静默忽略。要放到最左边只能在浏览器里手动拖。

> 验证方式：给 `batchUpdate` 送一个不存在的 request 名称会返回 `400001 request name error`，可以用这个来枚举支持哪些操作。`moveSheetRequest`、`updateSheetPropertiesRequest`、`reorderSheetRequest`、`renameSheetRequest`、`insertDimensionRequest` 等全部不存在。

**子表标题建完就改不了。** 没有 rename 接口。所以脚本在建表前会先查一次重名，撞名直接拒绝并提示改 `--title`，而不是建出两个同名表。

**单表上限 10000 格**（`rowCount × columnCount`）。超了 `addSheetRequest` 会报 `cells count is too large`。脚本会自动收缩预留的空行空列去适配；但如果**数据本身**就超过 10000 格，会在调用 API 前就拒绝：

```
Data is 13000 cells; a sheet holds at most 10000. Split the file.
```

新表默认建成 26 列（和既有子表一致），**所以 26 列时单表最多 384 行**。数据更长就得拆档上传。

> 这个上限卡在**建表**那一步，不是写入那一步。实测 384×26 = 9984 格可以单次 `updateRangeRequest` 写完（约 7.6 秒）。既然整张表最多 10000 格，单次写入又能写满，**分块写入是不必要的**。

**所有值都以文本写入。** `cellValue` 统一用 `{"text": ...}`，纯数字列在腾讯文档里会显示「数字以文本形式存储」的小三角，不能直接求和排序。`cellValue` 支持 `number` 类型，若要数值化需按内容判断后改用它。

## 排错

**腾讯 API 失败时也返回 HTTP 200**，真正的状态在 response body 的 `code` 字段。所以别只看状态码 —— 脚本里 `get_remote_sheets` 和 `batch_update` 都是检查 `code`。

| 输出 | 原因 |
|---|---|
| `Config file not found: ...` | 没建 `config.json`，复制 `config.example.json` |
| `Missing in ...: access_token` | `config.json` 有档但栏位空着 |
| `API error 400006: Authentication Internal Error` | token 过期或填错 |
| `A sheet named 'x' already exists.` | 重名，换 `--title` |
| `UnicodeEncodeError: 'cp950' codec` | 不该出现 —— 脚本开头已 `sys.stdout.reconfigure(encoding="utf-8")`。若在别处重现，是该处少了这行 |

腾讯后端偶发 tcp timeout（返回 `code` 非 0、message 含 `i/o timeout`），重跑一次通常就好。

## 接口备忘

三个 header 都要带：`Access-Token`、`Client-Id`、`Open-Id`。

### 列出子表

```
GET /openapi/spreadsheet/v3/files/{fileId}
```

```json
{"properties": [
  {"sheetId": "12pip7", "title": "工作表1",
   "rowCount": 89, "columnCount": 10, "rowTotal": 200, "columnTotal": 26}
]}
```

注意实际返回是**扁平**的 `properties` 阵列，不是官方文档里那种 `sheets[].properties` 巢状结构，也没有 `fileID` / `metadata` / `ranges`。

带 `?concise=1` 会把 `rowCount`/`columnCount` 抹成 0，且偶发超时，不建议用。

### 读取储存格

```
GET /openapi/spreadsheet/v3/files/{fileId}/values/{range}?sheetId={sheetId}
```

`range` 放路径里（如 `A1:C3`），`sheetId` 放 query。写成 `values/{sheetId}!A1:C3` 会报 `Range Validate error`。

```json
{"gridData": {"startRow": 0, "startColumn": 0,
  "rows": [{"values": [{"cellValue": {"text": "开始时间"}, "cellFormat": {...}}]}]}}
```

### 写入 / 改结构

```
POST /openapi/spreadsheet/v3/files/{fileId}/batchUpdate
```

**注意是斜杠 `/batchUpdate`，不是冒号 `:batchUpdate`** —— 冒号那版会返回 `400003 Resource Not Found`。

新增子表：

```json
{"requests": [{"addSheetRequest": {"title": "新表", "rowCount": 200, "columnCount": 26}}]}
```

```json
{"responses": [{"addSheetResponse": {"properties": {"sheetId": "TnJZgx", "title": "新表", ...}}}]}
```

写入内容：

```json
{"requests": [{"updateRangeRequest": {
  "sheetId": "TnJZgx",
  "gridData": {"startRow": 0, "startColumn": 0,
    "rows": [{"values": [{"cellValue": {"text": "A1"}}, {"cellValue": {"text": "B1"}}]}]}
}}]}
```

`startRow` / `startColumn` 都是 0-based。

### 建立 / 删除文档（测试用）

在正式文档上试接口很危险，需要试的时候用临时文档：

```
POST   /openapi/drive/v2/files          title=<名称>&type=sheet   (form-urlencoded)
DELETE /openapi/drive/v2/files/{ID}
```

建立回传的 `data.ID` 形如 `300000000$XXXX`（删除时用这个），而 `data.url` 里 `/sheet/` 之后那段才是表格 API 用的 `fileId`，两者**不同**。
