import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import requests

# sheet titles are non-ASCII; avoid UnicodeEncodeError on Windows consoles
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ================= Config =================
API_BASE = "https://docs.qq.com/openapi/spreadsheet/v3"

# addSheetRequest rejects rowCount * columnCount above this
MAX_CELLS = 10000

# new-sheet dimensions; the existing sheets in this doc are all 200 x 26
MIN_ROWS = 200
MIN_COLUMNS = 26
ROW_HEADROOM = 20  # spare rows beyond the uploaded data

# credentials and the target document live outside the repo (config.json is
# gitignored); see config.example.json
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def load_config():
    if not CONFIG_PATH.exists():
        sys.exit(
            f"Config file not found: {CONFIG_PATH}\n"
            "Copy config.example.json to config.json and fill in your credentials."
        )

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    required = ("access_token", "client_id", "open_id", "file_id")
    missing = [k for k in required if not config.get(k)]
    if missing:
        sys.exit(f"Missing in {CONFIG_PATH}: {', '.join(missing)}")

    headers = {
        "Access-Token": config["access_token"],
        "Client-Id": config["client_id"],
        "Open-Id": config["open_id"],
    }
    return headers, config["file_id"]


# file_id is the <FILE_ID> in https://docs.qq.com/sheet/<FILE_ID>; --file-id overrides it
HEADERS, FILE_ID = load_config()
# ==========================================


def get_remote_sheets():
    # get the sheets from tencent cloud
    url = f"{API_BASE}/files/{FILE_ID}"
    response = requests.get(url, headers=HEADERS, timeout=60)
    body = response.json()

    # the API answers HTTP 200 even on failure, so the real status is in "code"
    if body.get("code"):
        print(f"API error {body['code']}: {body.get('message')}")
        return None

    sheets = body.get("properties")
    if not sheets:
        print(f"No sheet found. Response: {body}")
        return None

    print(f"Found {len(sheets)} sheets, first one is '{sheets[0]['title']}'")
    return sheets


def batch_update(request_list):
    # the API answers HTTP 200 even on failure, so the real status is in "code"
    url = f"{API_BASE}/files/{FILE_ID}/batchUpdate"
    response = requests.post(
        url,
        headers={**HEADERS, "Content-Type": "application/json"},
        json={"requests": request_list},
        timeout=60,
    )
    body = response.json()

    if body.get("code"):
        print(f"API error {body['code']}: {body.get('message')}")
        return None

    return body


def read_local_sheet(path):
    # read sheet from path
    # header=None keeps the first row as data instead of letting pandas
    # turn blank header cells into "Unnamed: N"
    df = pd.read_excel(path, dtype=str, header=None).fillna("")
    matrix = df.values.tolist()

    print(f"Read '{path}': {len(matrix)} rows x {len(df.columns)} columns")
    return matrix


def sheet_size(matrix):
    # the API caps a sheet at MAX_CELLS, so trim the spare rows/columns to fit
    data_rows = len(matrix)
    data_columns = max(len(row) for row in matrix)

    rows = max(data_rows + ROW_HEADROOM, MIN_ROWS)
    columns = max(data_columns, MIN_COLUMNS)

    if rows * columns > MAX_CELLS:
        columns = max(data_columns, MAX_CELLS // rows)
    if rows * columns > MAX_CELLS:
        rows = max(data_rows, MAX_CELLS // columns)

    return rows, columns


def add_to_sheets(title, matrix):
    # append a new sheet; v3 cannot set a position, so it always lands last
    rows, columns = sheet_size(matrix)
    body = batch_update([
        {
            "addSheetRequest": {
                "title": title,
                "rowCount": rows,
                "columnCount": columns,
            }
        }
    ])
    if not body:
        return None

    for item in body.get("responses", []):
        properties = item.get("addSheetResponse", {}).get("properties", {})
        if properties.get("sheetId"):
            print(f"Created sheet '{title}' (sheetId={properties['sheetId']})")
            return properties["sheetId"]

    print(f"Sheet created but no sheetId in response: {body}")
    return None


def upload_sheets(sheet_id, matrix):
    # a sheet can never exceed MAX_CELLS, so the whole grid fits in one request
    grid_data = {
        "startRow": 0,
        "startColumn": 0,
        "rows": [
            {"values": [{"cellValue": {"text": str(cell)}} for cell in row]}
            for row in matrix
        ],
    }
    if not batch_update([
        {"updateRangeRequest": {"sheetId": sheet_id, "gridData": grid_data}}
    ]):
        return False

    print(f"Wrote {len(matrix)} rows")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Upload a local Excel sheet as a new sheet in a Tencent Docs spreadsheet."
    )
    parser.add_argument("--sheet", required=True, help="Path to the local .xlsx file")
    parser.add_argument("--title", help="Sheet title (default: the file name)")
    parser.add_argument(
        "--file-id",
        help="Target spreadsheet, the <FILE_ID> in https://docs.qq.com/sheet/<FILE_ID> "
             "(default: file_id from config.json)",
    )
    args = parser.parse_args()

    if args.file_id:
        global FILE_ID
        FILE_ID = args.file_id

    matrix = read_local_sheet(args.sheet)
    if not matrix:
        return 1

    cells = len(matrix) * max(len(row) for row in matrix)
    if cells > MAX_CELLS:
        print(f"Data is {cells} cells; a sheet holds at most {MAX_CELLS}. Split the file.")
        return 1

    sheets = get_remote_sheets()
    if sheets is None:
        return 1

    # titles cannot be changed after creation, so refuse to make a duplicate
    title = args.title or Path(args.sheet).stem
    if any(sheet["title"] == title for sheet in sheets):
        print(f"A sheet named '{title}' already exists. Use --title to pick another name.")
        return 1

    sheet_id = add_to_sheets(title, matrix)
    if not sheet_id:
        return 1

    if not upload_sheets(sheet_id, matrix):
        return 1

    print(f"Done: https://docs.qq.com/sheet/{FILE_ID}?tab={sheet_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())