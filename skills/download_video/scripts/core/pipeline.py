# core/pipeline.py
from pathlib import Path
from .config import ConfigManager
from downloader import (
    MetadataManager, YoutubeDownloader, TwitchDownloader,
    TwitcastDownloader, TwitterDownloader,
)
from post_process import YoutubeChatParser, TwitchChatParser, VideoSplitter
import subprocess

class DownloadPipeline:
    """专职负责：解析 Metadata -> 下载影片与弹幕 -> 弹幕清洗 -> 影片切割"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.config = ConfigManager(project_root)
        self.metadata_manager = MetadataManager(project_root, self.config.config_dir)

    def _check_assets(self) -> bool:
        """内置工具不进 git，第一次使用要先跑 setup_assets.py 抓下来

        这里只挡下来并提示，不自作主张下载 —— 那是约 370MB 的流量。
        """
        try:
            from setup_assets import missing_tools
        except ImportError:
            # 找不到安装脚本就别挡路，让后续的 FileNotFoundError 自己报
            return True

        missing = missing_tools()
        if not missing:
            return True

        print("\n" + "!" * 60)
        print(f"[Error] Bundled tools are missing: {', '.join(missing)}")
        print("        They are not tracked in git and must be downloaded once.")
        print("        Run this first (about 370 MB in total):")
        print("            uv run scripts/setup_assets.py")
        print("!" * 60)
        return False

    def _update_ytdlp(self):
        print("\n" + "-" * 60)
        print(">>> [Download step 0] Checking / updating bundled yt-dlp (nightly channel) ...")
        print("-" * 60)

        # 获取自带 yt-dlp 的绝对路径
        ytdlp_exe = self.config.get_tool_exe("yt_dlp", "yt-dlp/yt-dlp.exe")

        if not ytdlp_exe or not Path(ytdlp_exe).exists():
            print(f"[Warning] Bundled yt-dlp not found ({ytdlp_exe}), check the path. Skipping update.")
            return

        try:
            # 执行更新命令
            result = subprocess.run(
                [str(ytdlp_exe), "--update-to", "nightly"],
                capture_output=True,
                text=True,
                check=True
            )

            output = result.stdout.strip() if result.stdout else result.stderr.strip()

            # yt-dlp 如果是最新的，通常会输出 "... is up to date"
            if "up to date" in output.lower():
                print("[Info] Bundled yt-dlp is already up to date.")
            else:
                print(f"[Info] Bundled yt-dlp updated:\n{output}")

        except subprocess.CalledProcessError as e:
            # check=True 会在命令执行失败（返回码非0）时抛出此异常
            print("[Warning] yt-dlp update failed (network issue or file in use); "
                  f"continuing with the current version.\nError: {e.stderr.strip()}")
        except Exception as e:
            print(f"[Warning] Unexpected error while updating yt-dlp: {e}")

    def process(self, url: str,
                download_video: bool = True,
                download_chat: bool = True,
                assume_yes: bool = False) -> dict:

        if not self._check_assets():
            return {}

        self._update_ytdlp()

        print("\n" + "-" * 60)
        print(">>> [Download step 1] Parsing video metadata ...")
        print("-" * 60)

        metadata = self.metadata_manager.analyze(url)
        if metadata["status"] != "success":
            print("[Error] Metadata parsing failed, aborting.")
            return {}

        creator = metadata.get("creator", "Unknown")
        title = metadata.get("title", "UnknownTitle")
        video_id = metadata.get("video_id", "UnknownID")

        # 拦截机制：如果是 Unknown，极大概率是 Cookie 失效被墙了
        if creator == "Unknown":
            print(f"\n[Warning] Unknown streamer or suspicious title: {title}")
            print("[Warning] For a members-only video this usually means your cookie / OAuth token has expired.")
            if not assume_yes:
                print("[Info] Task cancelled; no empty folders were created.")
                print("[Info] Re-run with --yes if you want to download it anyway.")
                return {}
            print("[Info] --yes was given, continuing anyway.")

        unique_title = f"{title}_[{video_id}]"

        output_dir = self.config.get_output_dir(
            creator,
            metadata.get("date", "UnknownDate"),
            unique_title
        )

        # 延迟创建：只有通过了上面的拦截，才真正建立文件夹
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"[Info] Output directory: {output_dir}")

        platform = metadata["platform"]

        # Create a txt file to store the source link
        link_file_path = output_dir / f"{self.config.sanitize_filename(title)}_source_link.txt"
        try:
            with open(link_file_path, "w", encoding="utf-8") as f:
                f.write(f"Platform: {platform}\n")
                f.write(f"Title: {title}\n")
                f.write(f"URL: {url}\n")
            print(f"[Info] Wrote source link memo: {link_file_path.name}")
        except Exception as e:
            print(f"[Warning] Failed to write source link file: {e}")

        tools_paths_dict = self.config.tools_paths
        config_dir = self.config.config_dir

        # 分配下载器
        if platform == "youtube":
            downloader = YoutubeDownloader(self.project_root, metadata, output_dir, tools_paths_dict, config_dir=config_dir)
            chat_parser = YoutubeChatParser()
        elif platform == "twitch":
            downloader = TwitchDownloader(self.project_root, metadata, output_dir, tools_paths_dict, config_dir=config_dir)
            chat_parser = TwitchChatParser()
        elif platform == "twitcast":
            downloader = TwitcastDownloader(self.project_root, metadata, output_dir, tools_paths_dict, config_dir=config_dir)
            chat_parser = None
        elif platform == "twitter":
            downloader = TwitterDownloader(self.project_root, metadata, output_dir, tools_paths_dict, config_dir=config_dir)
            chat_parser = None
        elif platform == "tiktok":
            downloader = None
            chat_parser = None
        else:
            print(f"[Error] Unsupported platform: {platform}")
            return {}

        print("\n" + "-" * 60)
        print(">>> [Download step 2] Running download tasks ...")
        print("-" * 60)

        video_path = downloader.download_video() if download_video else None
        chat_path = downloader.download_chat() if download_chat else None

        if not chat_path and (download_video and not video_path):
            print("[Error] Neither video nor chat could be fetched. Aborting.")

            # 自动清理机制：如果下载组件彻底失败，且没留下任何文件，就删掉空文件夹
            try:
                if output_dir.exists() and not any(output_dir.iterdir()):
                    output_dir.rmdir()
                    # 尝试连同上一级的日期文件夹一并清理
                    if not any(output_dir.parent.iterdir()):
                        output_dir.parent.rmdir()
                    print("[Info] Cleaned up the empty folders left by the failed download.")
            except Exception:
                pass
            return {}

        print("\n" + "-" * 60)
        print(">>> [Download step 3] Cleaning the chat file ...")
        print("-" * 60)

        parsed_chat_path = None
        if chat_parser and chat_path and chat_path.exists():
            parsed_chat_path = chat_path.with_name(chat_path.name.replace("_chat", "_chat_parsed")).with_suffix(".json")
            chat_parser.parse(chat_path, parsed_chat_path)
        else:
            print("[Info] This platform needs no JSON chat cleaning, or it is not supported yet. Skipped.")
            if chat_path and chat_path.exists():
                parsed_chat_path = chat_path # TwitCasting 的 txt 备忘录

        if download_video and video_path and video_path.exists():
            print("\n" + "-" * 60)
            print(">>> [Download step 4] Checking whether the video needs splitting ...")
            print("-" * 60)
            ffmpeg_exe = self.config.get_tool_exe("ffmpeg", "ffmpeg-8.0.1-essentials_build/bin/ffmpeg.exe")
            ffprobe_exe = self.config.get_tool_exe("ffprobe", "ffmpeg-8.0.1-essentials_build/bin/ffprobe.exe")
            splitter = VideoSplitter(ffmpeg_exe, ffprobe_exe, max_size_gb=10.0)
            splitter.split(video_path)

        return {
            "output_dir": output_dir,
            "video_path": video_path,
            "chat_path": parsed_chat_path
        }


class HighlightPipeline:
    """专职负责：提取音频文字 (Whisper) -> 结合弹幕生成 Prompt -> 请求 LLM (预留)"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.config = ConfigManager(project_root)

    def process(self, video_path: Path, chat_path: Path = None) -> dict:
        if not video_path or not video_path.exists():
            print("[Error] Video file does not exist, cannot run AI analysis.")
            return {}

        # 惰性导入：AI 精华功能依赖额外的 highlight_cliper 模块，
        # 缺少它时下载流程仍应正常可用。
        try:
            from highlight_cliper import WhisperTranscriber, SrtSplitter
        except ImportError:
            print("[Error] The highlight_cliper module is not installed; AI highlight analysis is unavailable.")
            print("        Downloading is unaffected - use down_video.py / down_chat.py / video_chat.py instead.")
            return {}

        print("\n" + "-" * 60)
        print(">>> [AI step 1] Speech recognition (Faster-Whisper) ...")
        print("-" * 60)

        whisper_exe = self.config.get_tool_exe("faster_whisper", "faster-whisper-xxl/faster-whisper-xxl.exe")
        transcriber = WhisperTranscriber(whisper_exe)

        srt_path = transcriber.transcribe(
            video_path,
            whisper_config=self.config.whisper_config
        )

        #  =========== 步骤 2 字幕切割与 Prompt 部署 ===========
        split_files = []
        if srt_path and Path(srt_path).exists():
            print("\n" + "-" * 60)
            print(">>> [AI step 2] Splitting the subtitle file and deploying prompts ...")
            print("-" * 60)

            splitter = SrtSplitter(max_blocks=800)
            split_files = splitter.split_srt(Path(srt_path))

            # 读取 config 中配置的 Prompt 路径
            prompt_analyze = self.config.get_prompt_path("speech_analyze")
            prompt_sentence = self.config.get_prompt_path("to_excel")

            valid_prompts = [p for p in [prompt_analyze, prompt_sentence] if p is not None]

            # 部署 Prompt 到和 SRT 相同的资料夹下
            splitter.copy_prompts(Path(srt_path).parent, valid_prompts)
        #  =========================================================

        return {
            "srt_path": srt_path,
            "split_srt_paths": split_files
        }

class TotalPipeline:
    """一条龙服务：串联 Download 和 Highlight"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.downloader = DownloadPipeline(project_root)
        self.highlighter = HighlightPipeline(project_root)

    def process(self, url: str, assume_yes: bool = False):
        # 1. 先跑下载
        download_results = self.downloader.process(url, download_video=True, assume_yes=assume_yes)

        video_path = download_results.get("video_path")
        chat_path = download_results.get("chat_path")

        # 2. 如果视频下载成功，无缝衔接跑 AI 分析
        if video_path:
            if not chat_path:
                print("\n[Info] No chat file; AI analysis will rely on Whisper transcription only.")
            self.highlighter.process(video_path, chat_path)

        print("\n" + "=" * 60)
        print(" All stages finished.")
        print("=" * 60)
