# clip_highlight/scripts/analysis.py
"""分析流程层：拼中日对照 -> 切分 -> 按顺序喂给 LLM，串成整场分析

每次启动先清空 tmp/，所以分片一定是本次现切的 ——
不会误吃到 translate.py 留下的 200 条切分。
"""
import argparse
import re
import sys
import traceback
from pathlib import Path

from clear_tmp import clear_tmp
from llm import MODEL, call_llm, client
from preprocess import add_knowledge, list_srts, merge_bilingual, split_srt
from srt_io import configure_utf8_stdio, read_text

DEFAULT_MAX_CUES = 800
SRT_DIR = Path("tmp") / "srts"
BILINGUAL_DIR = Path("tmp") / "bilingual"
DEFAULT_OUTPUT_DIR = Path("outputs")

# 内置文件(prompt / 知识库)跟着脚本走，不能用 CWD 相对路径
SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = SKILL_DIR / "assets"
ANALYSIS_PROMPT = ASSETS_DIR / "analysis_prompt.md"

# 中日对照文件里的时间轴（毫秒已在 merge_bilingual 里剥掉）
TIME_LINE = re.compile(r"(\d{2}:\d{2}:\d{2}) --> (\d{2}:\d{2}:\d{2})")
# 分析输出里出现的时间戳，用于校验是否越界
OUTPUT_STAMP = re.compile(r"\b(\d{2}:\d{2}:\d{2})\b")
# 合法时间戳的完整形状，配 fullmatch 用
WELL_FORMED = re.compile(r"\d{2}:\d{2}:\d{2}")
# 输出里的时间范围，形如 `[00:00:28 - 00:01:27]` 或 `00:00:28 - 00:03:42`。
# 两侧宽松地抓成「数字加冒号」再逐个验形状 —— 收紧成 hh:mm:ss 就只能匹配到
# 正确的那些，而畸形的正是要找的东西。模块二的 `[00:28]` 不带连字号，不会命中。
OUTPUT_RANGE = re.compile(
    r"(?<![\d:])(\d{1,3}(?::\d{1,3})+)\s*-\s*(\d{1,3}(?::\d{1,3})+)(?![\d:])"
)


def parse_args():
    """配置命令行参数解析"""
    parser = argparse.ArgumentParser(
        prog="analysis.py",
        description="Analyse a stream for highlight clips, using the Japanese "
                    "source and its Chinese translation side by side.",
    )
    parser.add_argument("srt", type=Path, help="Path to the Japanese source SRT")
    parser.add_argument(
        "--translated",
        type=Path,
        default=None,
        help="Chinese SRT from translate.py (default: outputs/<stem>.zh.srt)",
    )
    # nargs='*' 表示可以接收 0 个或多个参数，解析后会变成一个列表
    # type=Path 会自动把传入的字符串转成 Path 对象
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
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Where to write the analysis (default: {DEFAULT_OUTPUT_DIR.as_posix()})",
    )
    return parser.parse_args()


def time_range(part_content: str) -> str:
    """算出分片的首尾时间，形如 `00:00:28 - 01:05:05`

    把范围当数据喂给模型，而不是让它自己去找最后一条 cue 再比较 ——
    实测它会编出超过片长两分半的时间戳。照抄边界值比推理边界值可靠得多。
    """
    stamps = TIME_LINE.findall(part_content)
    if not stamps:
        return ""
    return f"{stamps[0][0]} - {stamps[-1][1]}"


def analysis(parts, system_prompt: str, knowledge: str) -> str:
    """逐个分片调 LLM，把每轮输出按顺序拼成整场分析"""
    session_id = None
    all_responses = []
    total = len(parts)

    for index, part_path in enumerate(parts):
        part_content = read_text(part_path)

        # 只用来做输出校验，不再喂给模型 ——
        # 实测把范围写进 prompt 反而更糟：模型会锚定到范围终点，
        # 把它当成起点往后外推，整个模块一塌成一条覆盖全片的记录。
        span = time_range(part_content)

        # 第一轮时，如果知识库有内容，才加上【参考知识库】部分
        if index == 0 and knowledge.strip():
            user_prompt = f"【参考知识库】\n{knowledge}\n\n【字幕分片内容】\n{part_content}"
        else:
            user_prompt = f"【字幕分片内容】\n{part_content}"

        response, session_id = call_llm(
            client,
            MODEL,
            system_prompt,
            user_prompt,
            session_id,
        )

        print(f"[Info] Analyzed part {index + 1}/{total}: {part_path.name}")
        check_stamps(response, span, part_path.name)
        all_responses.append(response)

    return "\n\n".join(all_responses)


def check_stamps(response: str, span: str, part_name: str) -> None:
    """报告畸形与越界的时间戳

    只报不改 —— 跟翻译那边的覆盖率报告是同一个思路：
    让质量问题当场可见，而不是等下游用的时候才发现。
    字符串比较对 hh:mm:ss 是有效的，位数固定且左侧补零。

    畸形要单独查：越界检查靠 OUTPUT_STAMP 抓时间戳，而它只认 hh:mm:ss，
    模型把 `00:21:43` 写成 `02:43` 时根本不会被抓出来，于是安然通过越界检查。
    到了 to_excel 那步，模型又会把 `02:43` 补成合法的 `02:43:00`，
    格式再也挑不出毛病、值却是片长的七倍 —— 实测发生过，必须在这里就拦住。
    """
    malformed = sorted(
        {
            stamp
            for pair in OUTPUT_RANGE.findall(response)
            for stamp in pair
            if not WELL_FORMED.fullmatch(stamp)
        }
    )
    if malformed:
        print(
            f"[Warning] {part_name}: {len(malformed)} malformed timestamp(s), "
            f"expected hh:mm:ss: {', '.join(malformed)}"
        )

    if not span:
        return

    start, end = span.split(" - ")
    out_of_range = sorted(
        {stamp for stamp in OUTPUT_STAMP.findall(response) if not start <= stamp <= end}
    )
    if out_of_range:
        print(
            f"[Warning] {part_name}: {len(out_of_range)} timestamp(s) outside "
            f"{span}: {', '.join(out_of_range)}"
        )


def main() -> int:
    configure_utf8_stdio()
    args = parse_args()

    if args.max_cues <= 0:
        print("[Error] --max-cues must be a positive integer")
        return 1

    # 每场直播一个子目录，多场的产物不会混在一起
    stream_dir = args.output_dir / args.srt.stem
    translated_path = args.translated or (stream_dir / f"{args.srt.stem}.zh.srt")
    if not translated_path.is_file():
        print(f"[Error] Translated SRT not found: {translated_path}")
        print("[Error] Run translate.py first, or pass --translated")
        return 1

    system_prompt = read_text(ANALYSIS_PROMPT)
    if not system_prompt:
        return 1

    # 先清空 tmp/，保证下面的分片一定是本次现切的。
    # 注意这会连 translate.py 的 tmp/translated_srts 一起删掉，
    # 它的断点续跑状态会丢失(交付物在 outputs/ 下，不受影响)。
    clear_tmp()

    bilingual_path = merge_bilingual(
        args.srt, translated_path, BILINGUAL_DIR / f"{args.srt.stem}.srt"
    )
    if not bilingual_path:
        return 1

    parts = split_srt(bilingual_path, args.max_cues, SRT_DIR)
    if not parts:
        return 1

    knowledge = add_knowledge(args.knowledge)
    result = analysis(list_srts(SRT_DIR), system_prompt, knowledge)
    if not result:
        print("[Error] No analysis produced.")
        return 1

    stream_dir.mkdir(parents=True, exist_ok=True)
    output_path = stream_dir / f"{args.srt.stem}.analysis.md"
    output_path.write_text(result, encoding="utf-8")
    print(f"[Done] Analysis written to {output_path}")
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
