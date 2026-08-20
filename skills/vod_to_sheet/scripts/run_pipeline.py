# vod_to_sheet/scripts/run_pipeline.py
"""直播链接 -> 云端切片表：把四个 skill 按顺序串起来

存在的理由不是省几条命令，而是**消灭「从散文里抠路径」这件事**。
原本每个交接点都要人肉解析上一步的输出：
download_video 的 `Output directory:` 里藏着日期与实况主，
finesub 的 `完成：` 里藏着带哈希、拼不出来的 SRT 路径。
抠错一个，后面每一步都错，而且错得不像是这里错。

所以本脚本把这些值解析一次、写进 state.json，
下游（人或 agent）只读结构化数据，不再碰日志。

默认跑到 xlsx 为止就停。上传是不可逆的（子表标题建完改不了、
撞名直接被拒、只能排在最右边），要传得显式加 --upload。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 顺序即依赖顺序，后一步吃前一步的产物
STEPS = ["download", "asr", "translate", "analysis", "excel", "upload"]

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_ARGS = 2
EXIT_NEEDS_HUMAN = 3  # 需要人来拿主意，脚本不猜

# download_video 会把归档目录打出来，日期与实况主都在这个路径里
OUTPUT_DIR_LINE = re.compile(r"Output directory:\s*(.+?)\s*$", re.MULTILINE)
# finesub 唯一可信的成功信号。它失败时退出码仍是 0，只认这一行
FINESUB_DONE = re.compile(r"完成：\s*(.+?)\s*$", re.MULTILINE)
# 上传脚本最后一行的直达链接
UPLOAD_DONE = re.compile(r"Done:\s*(\S+)\s*$", re.MULTILINE)

# 值得原样转达给用户的行，不做判断只做收集
NOTICE_LINE = re.compile(
    r"^(?:\[(?:Warning|Error)\].*|Warning:.*|.*字幕稳定化摘要：.*|.*语音识别摘要：.*"
    r"|.*Chat cleaning finished.*)$",
    re.MULTILINE,
)


def configure_utf8_stdio() -> None:
    """强制 UTF-8 输出

    Windows 控制台默认 cp950 / cp936，本流程整条链路都在处理中日文，
    不设的话自己打的中文和子进程转发的内容都会变成乱码。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def parse_args():
    """配置命令行参数解析

    所有需要人拿主意的事情都在这里一次问清 —— 跑到一半再提问会卡死
    后台任务，而这条链路动辄几十分钟，没人盯着。
    """
    parser = argparse.ArgumentParser(
        prog="run_pipeline.py",
        description="Run the whole VOD-to-sheet pipeline: download, ASR, "
                    "translate, analyse, export. Uploading is opt-in.",
    )
    parser.add_argument("--link", help="直播链接（必填，除非 --from 跳过了下载）")
    parser.add_argument(
        "--name",
        required=True,
        help="这场直播的短名，如 20260326_haru。决定 SRT 名与输出目录名，"
             "别用 mp4 原名（带方括号和空格，后面每一步都难处理）",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent,
        help="四个兄弟 skill 所在的目录，即本 skill 的上一层（默认由脚本位置推出）",
    )
    parser.add_argument(
        "--no-chat",
        action="store_true",
        help="只下影片，不抓弹幕（用 down_video.py 而非 video_chat.py）",
    )
    parser.add_argument(
        "--extra-info",
        default="",
        help="传给 finesub 的背景信息：主播名、游戏名、关键专名",
    )
    parser.add_argument(
        "--knowledge",
        default="assets/knowledge/finesub_kb.md",
        help="clip_highlight 的知识库，相对 clip_highlight/ "
             "(default: assets/knowledge/finesub_kb.md)",
    )
    parser.add_argument("--gpu-budget-gb", type=int, default=None, help="finesub 显存预算")
    parser.add_argument(
        "--from",
        dest="from_step",
        choices=STEPS,
        default=None,
        help="从这一步开始跑，之前的步骤一律跳过",
    )
    parser.add_argument(
        "--only", choices=STEPS, default=None, help="只跑这一步"
    )
    parser.add_argument(
        "--force", action="store_true", help="产物已存在也重跑，不做断点续跑"
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="跑完再上传腾讯文档。**不可逆**：子表标题建完改不了、撞名被拒、"
             "只能排最右边，所以默认不做",
    )
    parser.add_argument(
        "--title",
        default="",
        help="上传时的子表标题（默认 【<日期>】<实况主>）",
    )
    return parser.parse_args()


def run(command: List[str], cwd: Path) -> Tuple[int, str]:
    """跑一条命令，边转发输出边收集

    stderr 并进 stdout：finesub 失败时 traceback 只在 stderr，
    退出码却仍是 0 —— 两股流都得看到才判得出成败。
    子进程环境里写死 PYTHONIOENCODING，否则中日文回来就是乱码。
    """
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    # 本脚本自己跑在 vod_to_sheet 的 .venv 里，继承下去会让子进程的 uv
    # 打一句「VIRTUAL_ENV 与本项目不符，已忽略」的警告 —— 行为是对的，
    # 但那句话很像出了错，会把人和 agent 都带偏。摘掉它。
    for leaked in ("VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT"):
        env.pop(leaked, None)

    printable = " ".join(str(part) for part in command)
    print(f"\n$ cd {cwd}\n$ {printable}", flush=True)

    process = subprocess.Popen(
        [str(part) for part in command],
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    collected = []
    for line in process.stdout:
        print(line.rstrip(), flush=True)
        collected.append(line)

    return process.wait(), "".join(collected)


def collect_notices(state: dict, step: str, output: str) -> None:
    """把该转达的行收进 state，让下游照实报告而不是自行判定「应该没问题」

    整段替换而不是追加：重跑某一步时该步的告警要跟着刷新，
    追加的话续跑几次就会堆出一串早已不成立的旧告警。
    """
    found = [line.strip() for line in NOTICE_LINE.findall(output) if line.strip()]
    state.setdefault("notices", {})[step] = found


def save_state(state: dict, path: Path) -> None:
    """每步跑完就落盘，中途挂了也不丢已经解析出来的路径"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def find_media(directory: Path) -> Optional[Path]:
    """在归档目录里找影片，Twitter Space 是纯音频所以也认 .wav"""
    for pattern in ("*.mp4", "*.wav"):
        found = sorted(directory.glob(pattern))
        if found:
            # 超过 10GB 会被切成 [P1]、[P2]…，原档保留，这里要的是原档
            originals = [item for item in found if not re.search(r"\[P\d+\]", item.name)]
            return (originals or found)[0]
    return None


def step_download(args, state: dict) -> bool:
    """第 1 步：下载回放（可选弹幕），并解出日期与实况主"""
    if not args.link:
        print("[Error] --link is required to run the download step")
        return False

    entry = "down_video.py" if args.no_chat else "video_chat.py"
    code, output = run(
        ["uv", "run", f"scripts/{entry}", "--link", args.link],
        args.repo / "download_video",
    )
    collect_notices(state, "download", output)

    if code != 0:
        if "Unknown" in output:
            print(
                "\n[Error] 认不出实况主，任务被中止。这需要人来拿主意："
                "把该实况主写进 download_video/scripts/config.yaml 再重跑，"
                "还是接受归档到 Unknown 底下（原命令加 --yes）。"
                "先读 download_video/SKILL.md 的「识别到 Unknown」，别无脑加 --yes。"
            )
            raise SystemExit(EXIT_NEEDS_HUMAN)
        print(f"[Error] download step failed with exit code {code}")
        return False

    match = OUTPUT_DIR_LINE.search(output)
    if not match:
        print("[Error] 输出里找不到 `Output directory:`，无法确定归档位置")
        return False

    archive = Path(match.group(1))
    media = find_media(archive)
    if media is None:
        print(f"[Error] 归档目录里没有影片文件：{archive}")
        return False

    # videos/<实况主>/<日期>/<标题>_[<id>]/ —— 日期与实况主都从这个路径读，
    # 不要去用 yt-dlp 的 upload_date：那是 UTC，跟归档目录能差一天，
    # 而子表标题一旦建好就改不了。
    state["archive_dir"] = str(archive)
    state["media"] = str(media)
    state["date"] = archive.parent.name
    state["streamer"] = archive.parent.parent.name
    print(
        f"\n[Info] streamer={state['streamer']} date={state['date']}\n"
        f"[Info] media={state['media']}"
    )
    return True


def step_asr(args, state: dict) -> bool:
    """第 2 步：出日文 raw SRT

    只跑 raw 阶段（不传 --stage final-srt）：中文翻译交给 clip_highlight，
    它带着专属知识库和逐条校验，质量更可控，而且 raw 不调 LLM、不花额度。
    """
    media = state.get("media")
    if not media:
        print("[Error] 没有影片路径，先跑 download 步或用 --from download")
        return False

    command = ["finesub", media, "--language", "ja", "--name", args.name]
    if args.extra_info:
        command += ["--extra-info", args.extra_info]
    if args.gpu_budget_gb:
        command += ["--gpu-budget-gb", str(args.gpu_budget_gb)]

    code, output = run(command, args.repo)
    collect_notices(state, "asr", output)

    # 关键：不看退出码。finesub 跑挂时 traceback 只在 stderr，退出码照样 0，
    # 拿着不存在的路径往下走会在 translate 那步报出一个方向完全错的 not found。
    match = FINESUB_DONE.search(output)
    if not match:
        print(
            f"\n[Error] finesub 没有输出 `完成：` 行，判定为失败"
            f"（它的退出码 {code} 不可信）。"
            "\n[Error] 往上翻 traceback。若报某个 config 不是合法 JSON，"
            "多半是 %LOCALAPPDATA%\\FineSub\\models\\huggingface\\hub\\ 下"
            "某个 models--* 目录里的文件是 0 字节（下载中断的残骸），整个删掉重跑。"
        )
        return False

    state["raw_srt"] = str(Path(match.group(1)))
    print(f"\n[Info] raw_srt={state['raw_srt']}")
    return True


def clip_highlight_stem(args) -> str:
    """clip_highlight 的产物目录名跟着输入档名走，而输入是 <名字>-raw.srt"""
    return f"{args.name}-raw"


def step_translate(args, state: dict) -> bool:
    """第 3a 步：日文 SRT -> 中文 SRT"""
    raw_srt = state.get("raw_srt")
    if not raw_srt:
        print("[Error] 没有 raw SRT 路径，先跑 asr 步或用 --from asr")
        return False

    code, output = run(
        [
            "uv", "run", "scripts/translate.py", raw_srt,
            "--knowledge", args.knowledge,
        ],
        args.repo / "clip_highlight",
    )
    collect_notices(state, "translate", output)
    if code != 0:
        print(f"[Error] translate step failed with exit code {code}")
        return False

    state["zh_srt"] = str(
        args.repo / "clip_highlight" / "outputs"
        / clip_highlight_stem(args) / f"{clip_highlight_stem(args)}.zh.srt"
    )
    return True


def step_analysis(args, state: dict) -> bool:
    """第 3b 步：找出高光切片"""
    raw_srt = state.get("raw_srt")
    if not raw_srt:
        print("[Error] 没有 raw SRT 路径，先跑 asr 步或用 --from asr")
        return False

    code, output = run(
        [
            "uv", "run", "scripts/analysis.py", raw_srt,
            "--knowledge", args.knowledge,
        ],
        args.repo / "clip_highlight",
    )
    collect_notices(state, "analysis", output)
    if code != 0:
        print(f"[Error] analysis step failed with exit code {code}")
        return False

    state["analysis"] = str(
        args.repo / "clip_highlight" / "outputs"
        / clip_highlight_stem(args) / f"{clip_highlight_stem(args)}.analysis.md"
    )
    return True


def step_excel(args, state: dict) -> bool:
    """第 3c 步：分析记录 -> JSON + xlsx"""
    analysis = state.get("analysis")
    if not analysis:
        print("[Error] 没有分析记录，先跑 analysis 步或用 --from analysis")
        return False

    command = ["uv", "run", "scripts/to_excel.py", analysis]
    if state.get("date"):
        command += ["--sheet-date", state["date"]]

    code, output = run(command, args.repo / "clip_highlight")
    collect_notices(state, "excel", output)
    if code != 0:
        print(f"[Error] excel step failed with exit code {code}")
        return False

    stream_dir = (
        args.repo / "clip_highlight" / "outputs" / clip_highlight_stem(args)
    )
    state["rows_json"] = str(stream_dir / f"{clip_highlight_stem(args)}.rows.json")
    state["xlsx"] = str(stream_dir / f"{clip_highlight_stem(args)}.xlsx")
    return True


def step_upload(args, state: dict) -> bool:
    """第 4 步：上传腾讯文档（--upload 才会走到这里）"""
    xlsx = state.get("xlsx")
    if not xlsx:
        print("[Error] 没有 xlsx，先跑 excel 步")
        return False

    title = args.title or f"【{state.get('date', '')}】{state.get('streamer', '')}"
    code, output = run(
        [
            "uv", "run", "scripts/upload_to_qqdocs.py",
            "--sheet", xlsx, "--title", title,
        ],
        args.repo / "tencent_docs_uploader",
    )
    collect_notices(state, "upload", output)
    if code != 0:
        print(f"[Error] upload step failed with exit code {code}")
        return False

    match = UPLOAD_DONE.search(output)
    if match:
        state["sheet_url"] = match.group(1)
        state["sheet_title"] = title
    return True


HANDLERS = {
    "download": step_download,
    "asr": step_asr,
    "translate": step_translate,
    "analysis": step_analysis,
    "excel": step_excel,
    "upload": step_upload,
}

# 产物已存在就跳过这一步，据此实现断点续跑
ARTIFACTS = {
    "download": "media",
    "asr": "raw_srt",
    "translate": "zh_srt",
    "analysis": "analysis",
    "excel": "xlsx",
    "upload": "sheet_url",
}


def planned_steps(args) -> List[str]:
    """按 --only / --from / --upload 决定这趟要跑哪几步"""
    if args.only:
        return [args.only]

    steps = list(STEPS)
    if not args.upload:
        steps.remove("upload")
    if args.from_step:
        if args.from_step not in steps:
            return [args.from_step]
        steps = steps[steps.index(args.from_step):]
    return steps


def should_skip(step: str, state: dict, args) -> bool:
    """产物在不在？在就跳过 —— finesub 那步几十分钟，不该白跑第二遍"""
    if args.force or args.only or (args.from_step and step == args.from_step):
        return False

    key = ARTIFACTS[step]
    recorded = state.get(key)
    if not recorded:
        return False
    if step == "upload":
        return True
    return Path(recorded).exists()


def report(state: dict, uploaded: bool) -> None:
    """收尾汇总：产物在哪、有哪些该转达的告警"""
    print("\n" + "=" * 60)
    print("产物")
    print("=" * 60)
    for key in ("media", "raw_srt", "zh_srt", "analysis", "rows_json", "xlsx"):
        if state.get(key):
            print(f"  {key:<10} {state[key]}")

    # 按 STEPS 全量遍历，而不是只看这趟跑了哪几步 ——
    # 续跑或 --only 时，之前那些步骤的告警一样要露出来，
    # 否则「跳过=没问题」这个错觉正是这个汇总要防的东西。
    notices = state.get("notices", {})
    if any(notices.get(step) for step in STEPS):
        print("\n" + "=" * 60)
        print("以下是各步骤报出的告警，请原样转达给用户，不要自行判定「应该没问题」")
        print("=" * 60)
        for step in STEPS:
            for line in notices.get(step, []):
                print(f"  [{step}] {line}")

    if uploaded and state.get("sheet_url"):
        print(f"\n腾讯文档：{state['sheet_url']}")
    elif "xlsx" in state:
        print(
            "\n未上传（默认行为）。先核对表格 —— 尤其是**最后一行的结束时间"
            "有没有超过片长** —— 再决定上传：\n"
            "  uv run scripts/run_pipeline.py --name <名字> --only upload"
        )


def main() -> int:
    configure_utf8_stdio()
    args = parse_args()

    if not args.repo.is_dir():
        print(f"[Error] repo not found: {args.repo}")
        return EXIT_ARGS
    if args.only and args.from_step:
        print("[Error] --only and --from are mutually exclusive")
        return EXIT_ARGS

    state_path = args.repo / "vod_to_sheet" / "runs" / args.name / "state.json"
    state: Dict[str, object] = {}
    if state_path.is_file() and not args.force:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        print(f"[Info] Resuming from {state_path}")
    state["name"] = args.name

    steps = planned_steps(args)
    print(f"[Info] Steps: {' -> '.join(steps)}")

    for step in steps:
        if should_skip(step, state, args):
            print(f"\n[Info] {step}: 产物已存在，跳过（要重跑加 --force）")
            continue

        print(f"\n{'=' * 60}\n>>> {step}\n{'=' * 60}")
        if not HANDLERS[step](args, state):
            save_state(state, state_path)
            print(f"\n[Error] 停在 {step} 这一步。已解析出的路径保留在 {state_path}，"
                  f"修好之后用 --from {step} 接着跑。")
            return EXIT_FAILED
        save_state(state, state_path)

    report(state, args.upload)
    print(f"\n[Done] state: {state_path}")
    return EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        print("\n" + "!" * 60, file=sys.stderr)
        print("[Fatal] The pipeline crashed while running:", file=sys.stderr)
        traceback.print_exc()
        print("!" * 60, file=sys.stderr)
        sys.exit(EXIT_FAILED)
