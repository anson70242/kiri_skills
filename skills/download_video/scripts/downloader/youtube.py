# downloader/youtube.py
import os
from pathlib import Path
from typing import Optional

from .base import BaseDownloader

class YoutubeDownloader(BaseDownloader):
    """YouTube 平台专用的下载器"""

    def download_video(self) -> Optional[Path]:
        url = self.metadata.get("original_url")
        if not url:
            print("[Error] No source URL found, cannot download the video")
            return None

        ytdlp_exe = self.get_tool_path("yt_dlp")
        ffmpeg_exe = self.get_tool_path("ffmpeg")

        output_path = self.generate_output_path(ext="mp4")

        if output_path.exists():
            print(f"[Info] Video file already exists, skipping download: {output_path.name}")
            return output_path

        print(f"[Info] Starting YouTube video download: {url}")

        # 基础命令 (不包含 Cookie)
        base_command = [
            str(ytdlp_exe),
            "--rm-cache-dir",
            "--ffmpeg-location", str(ffmpeg_exe),
            "-f", "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            # --- WAV 提取参数 ---
            # "--extract-audio",
            # "--audio-format", "wav",
            # "--keep-video",
            # ---
            "--js-runtimes", "node",
            "-N", "5",
            "-o", str(output_path),
            url
        ]

        # 1. 尝试无 Cookie 下载
        print("[Info] Trying the plain download mode ...")
        success = self.run_command(base_command)

        # 2. 如果失败，尝试挂载 Cookie 重新下载
        if not success:
            print("[Warning] Plain download failed (members-only or age-restricted?), "
                  "retrying with Firefox cookies ...")
            # 将 --cookies-from-browser firefox 插入到 url 前面
            retry_command = base_command[:-1] + ["--cookies-from-browser", "firefox", url]
            success = self.run_command(retry_command)

            if not success:
                print("[Error] Download still failed with Firefox cookies. "
                      "Make sure you are logged into the right account in Firefox.")

        # 检查最终结果
        if success and output_path.exists():
            print(f"[Success] Video downloaded: {output_path.name}")
            return output_path

        print("[Error] Video download ultimately failed")
        return None

    def download_chat(self) -> Optional[Path]:
        url = self.metadata.get("original_url")
        if not url:
            print("[Error] No source URL found, cannot download the chat")
            return None

        ytdlp_exe = self.get_tool_path("yt_dlp")
        node_exe = self.get_tool_path("node")

        base_output_template = self.generate_output_path(suffix="_chat", ext="%(ext)s")
        expected_live_chat_path = self.generate_output_path(suffix="_chat", ext="live_chat.json")

        if expected_live_chat_path.exists():
            print(f"[Info] Chat file already exists, skipping download: {expected_live_chat_path.name}")
            return expected_live_chat_path

        print(f"[Info] Fetching YouTube chat replay / subtitles: {url}")

        # 基础命令 (不包含 Cookie)
        base_command = [
            str(ytdlp_exe),
            "--skip-download",
            "--write-subs",
            "--sub-lang", "live_chat",
            "--js-runtimes", "node",
            "-o", str(base_output_template),
            url
        ]

        # 1. 尝试无 Cookie 获取弹幕
        print("[Info] Trying the plain mode to fetch chat ...")
        success = self.run_command(base_command)

        # 2. 如果失败，尝试挂载 Cookie 重新获取
        if not success:
            print("[Warning] Fetching chat failed, retrying with Firefox cookies ...")
            retry_command = base_command[:-1] + ["--cookies-from-browser", "firefox", url]
            success = self.run_command(retry_command)

            if not success:
                print("[Error] Still failed with Firefox cookies. "
                      "Make sure you are logged into the right account in Firefox.")

        # 验证文件是否成功生成
        possible_extensions = ["live_chat.json", "ja.vtt", "en.vtt", "json", "vtt"]
        for ext in possible_extensions:
            check_path = self.generate_output_path(suffix="_chat", ext=ext)
            if check_path.exists():
                print(f"[Success] Chat / subtitles downloaded: {check_path.name}")
                return check_path

        # 针对 YouTube 的特性，增加更详细的提示
        print("\n[Warning] No chat or subtitle file was found.")
        print("          Possible reasons:")
        print("          1. The stream just ended and YouTube has not finished processing")
        print("             the chat replay yet (usually takes a few hours).")
        print("          2. The video genuinely has no chat replay or subtitles.")
        print("          Tip: finish the video download now, then re-run down_chat.py")
        print("               a few hours later to fetch the chat separately.")

        return None

# === 快速测试区块 ===
if __name__ == "__main__":
    current_file = Path(__file__).resolve()
    project_root = current_file.parents[2]

    test_output_dir = project_root / "test_output"

    mock_tools_paths = {
        "yt_dlp": "yt-dlp/yt-dlp.exe",
        "ffmpeg": "ffmpeg-8.0.1-essentials_build/bin/ffmpeg.exe",
        "node": "node-v24.13.1-win-x64/node.exe"
    }

    # 模拟 MetadataManager 解析出来的资料
    mock_metadata = {
        "status": "success",
        "platform": "youtube",
        "creator": "Haru",
        "title": "Youtube download test video",
        "date": "20260223",
        "original_url": "https://www.youtube.com/watch?v=OBNqNcLrlDQ"
    }

    downloader = YoutubeDownloader(
        project_root=project_root,
        metadata=mock_metadata,
        output_dir=test_output_dir,
        tools_paths=mock_tools_paths
    )

    print("-" * 50)
    print("[Test] Testing YoutubeDownloader")
    print("-" * 50)

    print("\n>>> Step 1: download the video")
    video_result = downloader.download_video()

    print("\n>>> Step 2: download the chat replay")
    chat_result = downloader.download_chat()
