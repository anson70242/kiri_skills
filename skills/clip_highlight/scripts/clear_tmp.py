# clip_highlight/scripts/clear_tmp.py
"""清空中间产物目录 tmp/

只清 tmp/ 下的内容，保留 tmp/ 本身。outputs/ 里的交付物不受影响。
"""
import argparse
import shutil
import sys
import traceback
from pathlib import Path

from srt_io import configure_utf8_stdio

DEFAULT_TMP_DIR = Path("tmp")


def clear_tmp(tmp_dir: Path = DEFAULT_TMP_DIR) -> int:
    """删除 tmp_dir 下的所有内容，返回删掉的条目数

    只接受名为 tmp 的目录 —— 这个函数会递归删除，
    传错路径的代价太大，宁可多挡一层。
    """
    tmp_dir = Path(tmp_dir)
    if tmp_dir.name != DEFAULT_TMP_DIR.name:
        print(f"[Error] Refusing to clear a directory not named 'tmp': {tmp_dir}")
        return -1

    if not tmp_dir.is_dir():
        print(f"[Info] Nothing to clear, {tmp_dir} does not exist")
        return 0

    removed = 0
    for entry in tmp_dir.iterdir():
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
        removed += 1

    print(f"[Info] Cleared {removed} item(s) from {tmp_dir}")
    return removed


def main() -> int:
    configure_utf8_stdio()

    parser = argparse.ArgumentParser(
        prog="clear_tmp.py",
        description="Delete everything inside the tmp/ working directory.",
    )
    parser.add_argument(
        "--tmp-dir",
        type=Path,
        default=DEFAULT_TMP_DIR,
        help=f"Directory to clear (default: {DEFAULT_TMP_DIR.as_posix()})",
    )
    args = parser.parse_args()

    return 1 if clear_tmp(args.tmp_dir) < 0 else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\n" + "!" * 60, file=sys.stderr)
        print("[Fatal] The program crashed while running:", file=sys.stderr)
        traceback.print_exc()
        print("!" * 60, file=sys.stderr)
        sys.exit(1)
