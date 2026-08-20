# downloader/twitcast.py
import os
from pathlib import Path
from typing import Optional

from .base import BaseDownloader

class TwitcastDownloader(BaseDownloader):
    """TwitCasting 平台专用的下载器"""

    def download_video(self) -> Optional[Path]:
        url = self.metadata.get("original_url")
        if not url:
            print("[Error] No source URL found, cannot download the TwitCasting video")
            return None

        ytdlp_exe = self.get_tool_path("yt_dlp")
        ffmpeg_exe = self.get_tool_path("ffmpeg")

        output_path = self.generate_output_path(ext="mp4")

        if output_path.exists():
            print(f"[Info] Video file already exists, skipping download: {output_path.name}")
            return output_path

        print(f"[Info] Starting TwitCasting video download: {url}")
        
        command = [
            str(ytdlp_exe),
            "--rm-cache-dir",
            "--js-runtimes", "node",                  
            "--ffmpeg-location", str(ffmpeg_exe),    
            # --- 下面这两行是新增的修复代码 ---
            "--downloader", "m3u8:ffmpeg",
            # -----------------------------------
            "--hls-use-mpegts",
            "--write-comments", 
            "--merge-output-format", "mp4",
            "-o", str(output_path),
            url
        ]
        
        if self.run_command(command):
            if output_path.exists():
                print(f"[Success] TwitCasting video downloaded: {output_path.name}")
                return output_path

        print("[Error] TwitCasting video download failed")
        return None

    def download_chat(self) -> Optional[Path]:
        """
        由于已在 Pipeline 层统一生成备忘录，此处直接跳过弹幕处理。
        """
        print("[Info] TwitCasting chat download is not supported yet, skipped.")
        return None