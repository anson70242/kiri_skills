# clip_highlight/scripts/srt_io.py
"""共享的文件与 SRT 读写。刻意不依赖 llm.py —— 只想读个文件的脚本
不该被迫初始化 genai client(那需要 API key)。
"""
import re
import sys
from pathlib import Path
from typing import List, NamedTuple

# 空行分隔字幕块，支援 Windows/Linux 换行符
BLOCK_SEPARATOR = re.compile(r"\r?\n[ \t]*\r?\n")


class Cue(NamedTuple):
    """一条字幕。time_line 原样保留，避免解析再格式化时丢失毫秒"""
    index: int
    time_line: str
    text: str


def configure_utf8_stdio() -> None:
    """强制 stdout / stderr 使用 UTF-8 输出

    Windows 控制台与管道默认是 cp950 或 cp936，字幕里的日文与 emoji
    会触发 UnicodeEncodeError 让整个程序崩溃。无法编码的字符降级替换。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def read_text(file_path: Path) -> str:
    """读取文本文件(prompt / 知识库 / SRT)，读不到就返回空字符串

    用 utf-8-sig：它读普通 UTF-8 的结果与 utf-8 完全一致，只是顺手剥掉 BOM。
    Whisper 产出的 SRT 常带 BOM，不剥掉的话第一个块的序号会变成 "﻿1"。
    编码必须写死 —— 内容里全是日语假名，
    在 Windows 上走系统默认的 cp936 会直接抛 UnicodeDecodeError。
    """
    file_path = Path(file_path)
    if not file_path.is_file():
        print(f"[Error] File not found: {file_path}")
        return ""

    content = file_path.read_text(encoding="utf-8-sig").strip()
    if not content:
        print(f"[Warning] File is empty: {file_path}")
    return content


def parse_srt(content: str) -> List[Cue]:
    """把 SRT 文本解析成 Cue 列表

    ⚠️ 注意：多行正文会被压成一行(用空格连接)，原有换行**会丢失**。
    这是为翻译流程设计的 —— `<n> 译文` 一个编号只能对一行文本。
    所以本函数不适合处理需要保留多行结构的 SRT，
    比如「日文一行 + 中文一行」的中日对照文件，读进来会塌成一行。
    那类文件请走纯字符串路径(split_srt 按空行分块，不碰正文结构)。

    index 一律按出现顺序重排，不信任文件里原有的序号 ——
    preprocess 切片时会重新编号，源文件也可能本身就断号。
    """
    cues = []
    for block in BLOCK_SEPARATOR.split(content.strip()):
        lines = block.strip().splitlines()
        if not lines:
            continue

        # 首行是序号时跳过它；时间轴行才是块的锚点
        time_index = 1 if lines and "-->" not in lines[0] else 0
        if time_index >= len(lines) or "-->" not in lines[time_index]:
            print(f"[Warning] Skipping malformed subtitle block: {lines[0][:40]!r}")
            continue

        # 多行字幕拼成一行 —— 译文按 id 回填时一条只能对一行
        text = " ".join(line.strip() for line in lines[time_index + 1:] if line.strip())
        cues.append(Cue(len(cues) + 1, lines[time_index].strip(), text))

    return cues


def format_srt(cues: List[Cue]) -> str:
    """把 Cue 列表写回标准 SRT，序号按列表顺序重排"""
    blocks = [
        f"{index}\n{cue.time_line}\n{cue.text}"
        for index, cue in enumerate(cues, start=1)
    ]
    return "\n\n".join(blocks) + "\n"