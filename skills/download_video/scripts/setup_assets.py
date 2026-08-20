# setup_assets.py
"""下载 assets/ 里的内置工具

这些二进制加起来约 370MB，不进 git（见 .gitignore），改由本脚本按需抓取。
只依赖标准库，因为它可能在依赖装好之前就被执行。
"""
import argparse
import io
import json
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

# assets/ 里的目标布局，与 scripts/config.yaml 的 tools_paths 一一对应。
# 刻意不带版本号 —— 上游改版本时不必同步改 config。
ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"

NODE_VERSION = "v24.13.1"

UA = {"User-Agent": "Mozilla/5.0 (AutoKiri setup_assets)"}


def _human(n: int) -> str:
    return f"{n / 1048576:.1f} MB"


def _progress(label: str, done: int, total: int) -> None:
    """非 TTY（被管道接走、CI）时不要每 1MB 刷一行，只在每 10% 报一次"""
    if sys.stdout.isatty():
        if total:
            print(f"\r  [{label}] {done * 100 // total:3d}%  {_human(done)} / {_human(total)}",
                  end="", flush=True)
        else:
            print(f"\r  [{label}] {_human(done)}", end="", flush=True)
    elif total and (done * 10 // total) != ((done - (1 << 20)) * 10 // total):
        print(f"  [{label}] {done * 100 // total:3d}%  {_human(done)} / {_human(total)}", flush=True)


def _download(url: str, dest: Path, label: str) -> None:
    """下载到同目录的 .part 再改名

    临时档刻意放在目标目录旁边：一来跨磁碟搬移会退化成整档复制，
    二来 rename 是原子的，中断不会留下被误判成「已安装」的半截档案。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    _progress(label, done, total)
            if sys.stdout.isatty():
                print()
        if total and done != total:
            raise RuntimeError(f"incomplete download: got {_human(done)}, expected {_human(total)}")
        os.replace(tmp, dest)   # 同目录，原子改名
    finally:
        if tmp.exists():
            tmp.unlink()


def _download_zip_members(url: str, label: str, wanted: dict) -> None:
    """下载 zip 并只取出需要的档案

    :param wanted: {zip 内档名的结尾: 目标绝对路径}
    """
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        buf = io.BytesIO()
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            buf.write(chunk)
            done += len(chunk)
            _progress(label, done, total)
        if sys.stdout.isatty():
            print()

    with zipfile.ZipFile(buf) as zf:
        names = zf.namelist()
        for suffix, dest in wanted.items():
            match = next((n for n in names if n.replace("\\", "/").endswith(suffix)), None)
            if match is None:
                raise RuntimeError(f"{label}: {suffix} not found inside the archive")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(match) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            print(f"  -> {dest.relative_to(ASSETS_DIR.parent)}")


def _twitch_cli_url() -> str:
    """TwitchDownloaderCLI 的档名带版本号，得先问一次 GitHub API"""
    req = urllib.request.Request(
        "https://api.github.com/repos/lay295/TwitchDownloader/releases/latest",
        headers={**UA, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if name.startswith("TwitchDownloaderCLI-") and name.endswith("-Windows-x64.zip"):
            return asset["browser_download_url"]
    raise RuntimeError("no TwitchDownloaderCLI Windows x64 release asset found")


# ---- 各工具的安装步骤 ----

def install_ytdlp() -> None:
    # 用 nightly 通道：pipeline 每次跑也会 --update-to nightly，来源保持一致
    _download(
        "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp.exe",
        ASSETS_DIR / "yt-dlp" / "yt-dlp.exe",
        "yt-dlp",
    )


def install_node() -> None:
    # 只要 node.exe —— 它单纯当 yt-dlp 的 JS runtime，npm / node_modules 全用不到
    _download(
        f"https://nodejs.org/dist/{NODE_VERSION}/win-x64/node.exe",
        ASSETS_DIR / "node" / "node.exe",
        "node",
    )


def install_ffmpeg() -> None:
    _download_zip_members(
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        "ffmpeg",
        {
            "/bin/ffmpeg.exe": ASSETS_DIR / "ffmpeg" / "bin" / "ffmpeg.exe",
            "/bin/ffprobe.exe": ASSETS_DIR / "ffmpeg" / "bin" / "ffprobe.exe",
        },
    )


def install_twitch_cli() -> None:
    _download_zip_members(
        _twitch_cli_url(),
        "TwitchDownloaderCLI",
        {"TwitchDownloaderCLI.exe": ASSETS_DIR / "TwitchDownloaderCLI" / "TwitchDownloaderCLI.exe"},
    )


# 名称 -> (安装函式, 用于判断是否已安装的档案)
TOOLS = {
    "yt-dlp": (install_ytdlp, ASSETS_DIR / "yt-dlp" / "yt-dlp.exe"),
    "ffmpeg": (install_ffmpeg, ASSETS_DIR / "ffmpeg" / "bin" / "ffmpeg.exe"),
    "ffprobe": (install_ffmpeg, ASSETS_DIR / "ffmpeg" / "bin" / "ffprobe.exe"),
    "node": (install_node, ASSETS_DIR / "node" / "node.exe"),
    "TwitchDownloaderCLI": (install_twitch_cli,
                            ASSETS_DIR / "TwitchDownloaderCLI" / "TwitchDownloaderCLI.exe"),
}


def missing_tools() -> list:
    """回传还没安装的工具名单，供 pipeline 判断要不要挡下来"""
    missing = []
    for name, (_, probe) in TOOLS.items():
        if not probe.exists():
            missing.append(name)
    # ffmpeg / ffprobe 同一个压缩包，别报两次
    if "ffmpeg" in missing and "ffprobe" in missing:
        missing.remove("ffprobe")
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="setup_assets.py",
        description="Download the bundled tools into assets/ (about 370 MB in total).",
    )
    parser.add_argument("--force", action="store_true",
                        help="Re-download even if the tool is already present")
    args = parser.parse_args()

    # 路径或错误讯息可能含非 ASCII，Windows 主控台预设 cp950 会直接崩
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    print("=" * 60)
    print("       AutoKiri-Flow [asset setup]")
    print("=" * 60)
    print(f"Target directory: {ASSETS_DIR}")

    # ffmpeg 与 ffprobe 共用一次下载，去重后再跑
    planned, seen = [], set()
    for name, (installer, probe) in TOOLS.items():
        if not args.force and probe.exists():
            print(f"[Skip] {name} already present")
            continue
        if installer in seen:
            continue
        seen.add(installer)
        planned.append((name, installer))

    if not planned:
        print("\n[Info] All tools are already installed. Nothing to do.")
        return 0

    print(f"\n[Info] Need to download: {', '.join(n for n, _ in planned)}")
    failed = []
    for name, installer in planned:
        print(f"\n>>> {name}")
        try:
            installer()
        except Exception as e:
            print(f"[Error] {name} failed: {e}")
            failed.append(name)

    print("\n" + "=" * 60)
    if failed:
        print(f"[Error] These tools failed to install: {', '.join(failed)}")
        print("        Check your network and re-run this script.")
        return 1
    print("[Success] All tools are ready.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[Info] Interrupted. Re-run to resume; finished tools are skipped.")
        sys.exit(1)