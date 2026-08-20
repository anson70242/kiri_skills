# clip_highlight/scripts/translate.py
"""翻译层：把日语 SRT 逐条译成中文，时间轴不经过 LLM

流程是文件驱动的：切分 -> 逐片翻译 -> 逐片落盘 -> 全部完成后合并。
每片一翻完就写进 tmp/translated_srts/，所以 call_llm 的重试也救不回来时
(429 退避耗尽、5xx、断网、Ctrl+C)，已经翻好的分片不会跟着一起丢，
重跑会自动跳过它们。
"""
import argparse
import re
import sys
import traceback
from pathlib import Path
from typing import Dict, List

from clear_tmp import clear_tmp
from llm import MODEL, call_llm, client
from preprocess import add_knowledge, list_srts, split_srt
from srt_io import Cue, configure_utf8_stdio, format_srt, parse_srt, read_text

DEFAULT_MAX_CUES = 200
DEFAULT_MAX_REPAIR = 2
SRT_DIR = Path("tmp") / "srts"
TRANSLATED_DIR = Path("tmp") / "translated_srts"
DEFAULT_OUTPUT_DIR = Path("outputs")

# 内置文件(prompt / 知识库)跟着脚本走，不能用 CWD 相对路径
SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = SKILL_DIR / "assets"
TRANSLATE_PROMPT = ASSETS_DIR / "translate_prompt.md"

# 宽松匹配：编号后可以没有空格，译文可以带前后空白
LINE_PATTERN = re.compile(r"^\s*<(\d+)>\s*(.+?)\s*$")


def parse_args():
    """配置命令行参数解析"""
    parser = argparse.ArgumentParser(
        prog="translate.py",
        description="Translate a Japanese SRT into Chinese, part by part.",
    )
    parser.add_argument("srt", type=Path, help="Path to the source SRT file")
    parser.add_argument(
        "--knowledge",
        nargs="*",
        type=Path,
        default=[],
        help="One or more knowledge base files, e.g. --knowledge a.md b.md",
    )
    parser.add_argument(
        "--max-cues",
        type=int,
        default=DEFAULT_MAX_CUES,
        help=f"Upper bound of cues per part, i.e. per request "
             f"(default: {DEFAULT_MAX_CUES}). Parts are evenly balanced under it.",
    )
    parser.add_argument(
        "--max-repair",
        type=int,
        default=DEFAULT_MAX_REPAIR,
        help=f"Extra rounds to re-request missing cues (default: {DEFAULT_MAX_REPAIR})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Where to write the merged SRT (default: {DEFAULT_OUTPUT_DIR.as_posix()})",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Keep tmp/ and skip parts already translated, to continue a crashed run",
    )
    return parser.parse_args()


def parse_translation(response: str, count: int) -> Dict[int, str]:
    """从响应里逐行抽出 `<n> 译文`

    逐行解析而不是整体解析 —— 某一行写坏了只丢那一条，
    输出被截断时已输出的部分仍然全部可用；
    模型自作主张加了代码块或开场白也不影响解析。
    """
    translated = {}
    for line in response.splitlines():
        match = LINE_PATTERN.match(line)
        if not match:
            continue

        number = int(match.group(1))
        if 1 <= number <= count:
            translated[number] = match.group(2)

    return translated


def translate_cues(cues: List[Cue], system_prompt: str, knowledge: str,
                   max_repair: int) -> Dict[int, str]:
    """翻一个分片，缺的再补，返回 {分片内编号: 译文}

    编号直接用分片内的 1..N —— split_srt 已经把每份重新编号过，
    小而一致的编号 LLM 抄得更准，四位数编号更容易漂。
    """
    translated: Dict[int, str] = {}
    pending = [cue.index for cue in cues]

    for attempt in range(max_repair + 1):
        # 补翻时只发还缺的那几条，编号沿用分片内原编号，回填才对得上
        numbered = "\n".join(
            f"<{cues[number - 1].index}> {cues[number - 1].text}" for number in pending
        )

        user_prompt = f"【字幕原文】\n{numbered}"
        if knowledge.strip():
            user_prompt = f"【参考知识库】\n{knowledge}\n\n{user_prompt}"

        response, _ = call_llm(client, MODEL, system_prompt, user_prompt)
        translated.update(parse_translation(response, len(cues)))

        pending = [number for number in pending if number not in translated]
        if not pending:
            break

        if attempt < max_repair:
            print(f"[Warning] {len(pending)} cue(s) missing, re-requesting them")

    return translated


def translate_part(part_path: Path, system_prompt: str, knowledge: str,
                   max_repair: int) -> List[Cue]:
    """翻译一个分片，把译文接回该分片的原始时间轴"""
    cues = parse_srt(read_text(part_path))
    if not cues:
        return []

    translated = translate_cues(cues, system_prompt, knowledge, max_repair)

    merged = []
    missing = []
    for cue in cues:
        text = translated.get(cue.index)
        if text is None:
            # 保留日文原文而不是留空 —— 空字幕在播放器里是一段诡异的静默，
            # 留着原文至少能看出这里漏了。
            text = cue.text
            missing.append(cue.index)
        merged.append(cue._replace(text=text))

    print(f"[Info] {part_path.name}: {len(translated)}/{len(cues)} cues translated")
    if missing:
        preview = ", ".join(str(number) for number in missing[:20])
        suffix = " ..." if len(missing) > 20 else ""
        print(
            f"[Error] {part_path.name}: {len(missing)} cue(s) still untranslated "
            f"after {max_repair} repair round(s), left as Japanese source: "
            f"{preview}{suffix}"
        )
    return merged


def main() -> int:
    configure_utf8_stdio()
    args = parse_args()

    if args.max_cues <= 0:
        print("[Error] --max-cues must be a positive integer")
        return 1

    system_prompt = read_text(TRANSLATE_PROMPT)
    if not system_prompt:
        return 1

    # 默认清空 tmp/，保证本次用的分片一定是按当前 --max-cues 现切的。
    # 不清的话，上次用别的粒度跑剩下的 tmp/translated_srts/ 会被错误复用。
    # 崩溃后要接着上次跑，用 --resume 保留它们。
    # 清不干净就别往下走：split_srt 之后是整个目录一起读，
    # 上次跑剩的分片会被当成本次的一起翻。
    if not args.resume:
        if clear_tmp() < 0:
            print("[Error] tmp/ 没清干净，停下来避免复用上次的分片。")
            return 1

    parts = split_srt(args.srt, args.max_cues, SRT_DIR)
    if not parts:
        return 1

    knowledge = add_knowledge(args.knowledge)
    TRANSLATED_DIR.mkdir(parents=True, exist_ok=True)

    for part_path in parts:
        translated_path = TRANSLATED_DIR / part_path.name
        if translated_path.is_file() and args.resume:
            print(f"[Info] {part_path.name}: already translated, skipping")
            continue

        merged = translate_part(part_path, system_prompt, knowledge, args.max_repair)
        if not merged:
            print(f"[Error] Nothing translated for {part_path.name}, aborting")
            return 1

        translated_path.write_text(format_srt(merged), encoding="utf-8")

    # 全部分片都到齐了才合并，顺序由 list_srts 的 [Part-N] 数值排序保证
    merged_cues = []
    for translated_path in list_srts(TRANSLATED_DIR):
        merged_cues.extend(parse_srt(read_text(translated_path)))

    if not merged_cues:
        print("[Error] No translated parts to merge")
        return 1

    # 每场直播一个子目录，多场的产物不会混在一起
    stream_dir = args.output_dir / args.srt.stem
    stream_dir.mkdir(parents=True, exist_ok=True)
    output_path = stream_dir / f"{args.srt.stem}.zh.srt"
    output_path.write_text(format_srt(merged_cues), encoding="utf-8")
    print(f"[Done] {len(merged_cues)} cues merged into {output_path}")
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
