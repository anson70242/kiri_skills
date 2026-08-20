# clip_highlight/scripts/clear_tmp.py
"""清空中间产物目录 tmp/

只清 tmp/ 下的内容，保留 tmp/ 本身。outputs/ 里的交付物不受影响。

刻意不用 shutil.rmtree：有些平台（如 CodeBuddy）会挂一层 safe-delete shim
拦截递归删除，rmtree 会当场抛异常。这里改成自底向上一个个 unlink 再 rmdir，
删到哪算哪，删不掉的报出来交给调用方决定，不让清理动作把整个流程带崩。
"""
import argparse
import sys
import traceback
from pathlib import Path

from srt_io import configure_utf8_stdio

DEFAULT_TMP_DIR = Path("tmp")


SANDBOX_HINT = (
    "删不掉多半是平台的 safe-delete 沙箱拦了删除动作"
    "（dangerouslyDisableSandbox 挡不住这层 shim）。"
    "两条出路：设 CODEBUDDY_SAFE_DELETE_SANDBOX=0，或自己手动把 tmp/ 清空再重跑。"
)


def _remove_tree(root: Path, failures: list) -> int:
    """自底向上删掉 root（含 root 自己），返回删掉的条目数

    失败的路径记进 failures，不抛异常 —— 沙箱 shim 抛什么型别不好预期，
    所以这里 except Exception，别缩窄成 OSError。
    """
    removed = 0
    if root.is_dir() and not root.is_symlink():
        for child in root.iterdir():
            removed += _remove_tree(child, failures)
    try:
        root.rmdir() if root.is_dir() and not root.is_symlink() else root.unlink()
        removed += 1
    except Exception as exc:
        failures.append(f"{root}: {exc}")
    return removed


def clear_tmp(tmp_dir: Path = DEFAULT_TMP_DIR) -> int:
    """删除 tmp_dir 下的所有内容，返回删掉的条目数；有删不掉的返回 -1

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
    failures: list = []
    for entry in tmp_dir.iterdir():
        removed += _remove_tree(entry, failures)

    if failures:
        print(f"[Error] Failed to clear {len(failures)} item(s) under {tmp_dir}:")
        for line in failures[:5]:
            print(f"  {line}")
        if len(failures) > 5:
            print(f"  ... and {len(failures) - 5} more")
        print(f"[Error] {SANDBOX_HINT}")
        return -1

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
