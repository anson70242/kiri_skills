# downloader/twitter.py
import os
from pathlib import Path
from typing import Optional

from .base import BaseDownloader

class TwitterDownloader(BaseDownloader):
    """Twitter (X) Space 专用的下载器"""

    def download_video(self) -> Optional[Path]:
        url = self.metadata.get("original_url")
        if not url:
            print("[Error] No source URL found, cannot download the Twitter Space")
            return None
            
        ytdlp_exe = self.get_tool_path("yt_dlp")
        ffmpeg_exe = self.get_tool_path("ffmpeg")
        
        # Twitter Space 是纯音频，这里强制提取并保存为 wav 格式
        output_path = self.generate_output_path(ext="wav")
        # output_path = self.generate_output_path(ext="mp4")
        
        if output_path.exists():
            print(f"[Info] Audio file already exists, skipping download: {output_path.name}")
            return output_path

        print(f"[Info] Starting Twitter Space download: {url}")
        
        # 基础命令：使用 yt-dlp 抓取
        base_command = [
            str(ytdlp_exe),
            "--rm-cache-dir",
            "--ffmpeg-location", str(ffmpeg_exe),
            "--extract-audio", 
            "--audio-format", "wav",
            "-o", str(output_path),
            url
        ]

        # base_command = [
        #     str(ytdlp_exe),
        #     "--rm-cache-dir",
        #     "--ffmpeg-location", str(ffmpeg_exe),
        #     "-f", "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        #     "--merge-output-format", "mp4",
        #     # --- WAV 提取参数 ---
        #     # "--extract-audio",       
        #     # "--audio-format", "wav", 
        #     # "--keep-video",
        #     # ---
        #     "--js-runtimes", "node",
        #     "-N", "5",
        #     "-o", str(output_path),
        #     url
        # ]
        
        # 1. 尝试无 Cookie 下载
        print("[Info] Trying the plain download mode ...")
        success = self.run_command(base_command)

        # 2. 如果失败，尝试挂载 Cookie 重新下载 (针对锁推/仅限关注者可见的 Space)
        if not success:
            print("[Warning] Plain download failed, retrying with Firefox cookies ...")
            retry_command = base_command[:-1] + ["--cookies-from-browser", "firefox", url]
            success = self.run_command(retry_command)

        if success and output_path.exists():
            print(f"[Success] Twitter Space downloaded: {output_path.name}")
            return output_path

        print("[Error] Twitter Space download ultimately failed")
        return None

    def download_chat(self) -> Optional[Path]:
        """
        由于已在 Pipeline 层统一生成备忘录，此处直接跳过。
        """
        print("[Info] Twitter Space has no chat replay to fetch, skipped.")
        return None