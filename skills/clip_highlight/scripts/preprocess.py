# clip_highlight/scripts/preprocess.py
"""输入准备层：切分 SRT、按顺序列出分片、载入知识库

translate.py 与 analysis.py 共用这里，两者只是切分粒度不同。
"""
import argparse
import math
import re
import sys
import traceback
from pathlib import Path
from typing import List, Optional

from srt_io import configure_utf8_stdio, read_text

DEFAULT_MAX_BLOCKS = 800
DEFAULT_OUTPUT_DIR = Path("tmp") / "srts"

# SRT 时间轴的毫秒段，形如 00:13:36,040 里的 ",040"
MILLISECONDS = re.compile(r",\d{3}")


def split_srt(
    srt_path: Path,
    max_blocks: int = DEFAULT_MAX_BLOCKS,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    """将过长的 SRT 以块为单位读取，计算等分并切片，产物写到 output_dir"""
    if not srt_path or not srt_path.exists():
        print(f"[Error] SRT file not found: {srt_path}")
        return []

    content = read_text(srt_path)
    if not content:
        return []

    # 使用正则匹配空行来分割每一个字幕块 (支援 Windows/Linux 换行符)
    blocks = re.split(r'\r?\n[ \t]*\r?\n', content)
    total_blocks = len(blocks)

    # 计算要切成几份，以及每份多少块 (确保尽量均分)
    # 比如 801 块 -> 切成 2 份 -> 每份 ceil(801/2) = 401 块 (而不是 800 和 1)
    num_chunks = math.ceil(total_blocks / max_blocks)
    if num_chunks == 0:
        return []

    blocks_per_chunk = math.ceil(total_blocks / num_chunks)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = srt_path.stem
    split_files = []

    for i in range(num_chunks):
        start_idx = i * blocks_per_chunk
        end_idx = min((i + 1) * blocks_per_chunk, total_blocks)
        chunk_blocks = blocks[start_idx:end_idx]

        # 顺手重新编号 (对 LLM 解析更友好，让每份 SRT 都从 1 开始)
        renumbered_blocks = []
        for idx, block in enumerate(chunk_blocks, start=1):
            # 把第一行的原数字替换为新的数字
            lines = block.split('\n', 1)
            if len(lines) == 2:
                renumbered_blocks.append(f"{idx}\n{lines[1]}")
            else:
                renumbered_blocks.append(block)

        chunk_path = output_dir / f"[Part-{i+1}]{base_name}.srt"
        with open(chunk_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(renumbered_blocks) + "\n\n")

        split_files.append(chunk_path)
        print(f"[Info] Subtitle chunk created: {chunk_path} ({len(chunk_blocks)} cues)")

    return split_files


def merge_bilingual(source_path: Path, translated_path: Path,
                    output_path: Path) -> Optional[Path]:
    """把日文原文与中文译文按 cue 逐条拼成中日对照文件

    产物每块是四行：序号 / 时间轴 / 日文 / 中文。
    时间轴会去掉毫秒 —— 实测模型会把 `00:13:36,040` 读成 `13:36:04`，
    把毫秒当成秒段，同一份输出里还会混用两种格式。少给它三位数字就少一个歧义源。

    刻意走纯字符串路径，不用 srt_io.parse_srt —— 那个函数会把多行正文
    压成一行，对照格式正好是两行，读进去就塌了。
    切分用的 split_srt 同样是按空行分块的字符串操作，不碰正文结构。
    """
    source = read_text(source_path)
    translated = read_text(translated_path)
    if not source or not translated:
        return None

    source_blocks = re.split(r'\r?\n[ \t]*\r?\n', source)
    translated_blocks = re.split(r'\r?\n[ \t]*\r?\n', translated)

    if len(source_blocks) != len(translated_blocks):
        print(
            f"[Error] Cue count mismatch: {source_path.name} has "
            f"{len(source_blocks)}, {translated_path.name} has {len(translated_blocks)}"
        )
        return None

    merged_blocks = []
    for number, (source_block, translated_block) in enumerate(
        zip(source_blocks, translated_blocks), start=1
    ):
        source_lines = source_block.strip().splitlines()
        translated_lines = translated_block.strip().splitlines()
        if len(source_lines) < 3 or len(translated_lines) < 3:
            print(f"[Warning] Skipping malformed block #{number}")
            continue

        # 时间轴必须一致，否则两份文件根本没对齐，拼出来的对照全是错的
        if source_lines[1].strip() != translated_lines[1].strip():
            print(
                f"[Error] Timeline mismatch at cue #{number}: "
                f"{source_lines[1].strip()} vs {translated_lines[1].strip()}"
            )
            return None

        japanese = "\n".join(source_lines[2:])
        chinese = "\n".join(translated_lines[2:])
        time_line = MILLISECONDS.sub("", source_lines[1].strip())
        merged_blocks.append(f"{number}\n{time_line}\n{japanese}\n{chinese}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n\n".join(merged_blocks) + "\n\n", encoding="utf-8")
    print(f"[Info] Bilingual file created: {output_path} ({len(merged_blocks)} cues)")
    return output_path


def list_srts(srt_dir: Path = DEFAULT_OUTPUT_DIR) -> List[Path]:
    """取出切好的分片，按 [Part-N] 的 N 由小到大排列

    不能直接用字典序 —— [Part-10] 会被排到 [Part-2] 前面，
    分片顺序一乱，后面拼出来的时间线就是错的。
    没有 [Part-N] 前缀的文件(比如没被切过的整份 SRT)排在最后。
    """
    if not srt_dir.is_dir():
        print(f"[Error] SRT directory not found: {srt_dir}")
        return []

    def sort_key(path: Path):
        match = re.match(r"\[Part-(\d+)\]", path.name)
        return (0, int(match.group(1)), path.name) if match else (1, 0, path.name)

    srt_list = sorted(srt_dir.glob("*.srt"), key=sort_key)
    if not srt_list:
        print(f"[Warning] No SRT files found in {srt_dir}")
    return srt_list


def add_knowledge(knowledge_paths: List[Path]) -> str:
    """读取并合并多个知识库文件"""
    if not knowledge_paths:
        return ""

    combined_knowledge = []
    for path in knowledge_paths:
        content = read_text(path)
        if content:
            combined_knowledge.append(content)

    # 用分隔符把多个知识库内容拼接起来
    return "\n\n---\n\n".join(combined_knowledge)


def main() -> int:
    configure_utf8_stdio()

    parser = argparse.ArgumentParser(
        prog="preprocess.py",
        description="Split an oversized SRT file into evenly sized parts, "
                    "renumbering each part from 1.",
    )
    parser.add_argument("srt", type=Path, help="Path to the SRT file to split")
    parser.add_argument(
        "--max-blocks",
        type=int,
        default=DEFAULT_MAX_BLOCKS,
        help=f"Maximum subtitle blocks per part (default: {DEFAULT_MAX_BLOCKS})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for the split files (default: {DEFAULT_OUTPUT_DIR.as_posix()})",
    )
    args = parser.parse_args()

    if args.max_blocks <= 0:
        parser.error("--max-blocks must be a positive integer")

    split_files = split_srt(args.srt, args.max_blocks, args.output_dir)
    if not split_files:
        return 1

    print(f"[Done] {len(split_files)} part(s) written to {args.output_dir}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\n" + "!" * 60, file=sys.stderr)
        print("[Fatal] The program crashed while running:", file=sys.stderr)
        traceback.print_exc()
        print("!" * 60, file=sys.stderr)
        sys.exit(1)
