# downloader/metadata.py
import os
import re
import subprocess
import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List, Tuple
from dotenv import load_dotenv

# ==========================================
# 1. 定義抽象基底類別 (Base Extractor)
# ==========================================
class BaseMetadataExtractor:
    """所有平台 Metadata 解析器的共用基底類別"""
    
    def __init__(self, project_root: Path, streamers: List[dict]):
        self.project_root = project_root
        self.streamers = streamers

    def analyze(self, url: str) -> Dict:
        """子類別必須實作這個方法"""
        raise NotImplementedError("請在子類別實作 analyze 方法")

    def _match_and_format(self, platform: str, uploader: str, title: str, date_str: str, url: str, video_id: str = "UnknownID") -> Dict:
        """共用的 config.yaml 實況主匹配邏輯"""
        creator_name = "Unknown"
        # 会限/受限影片时 yt-dlp 可能回传 None，统一降级成空字串再比对
        uploader = (uploader or "").lower()
        
        for streamer in self.streamers:
            for account in streamer.get("accounts", []):
                if account.get("platform") == platform:
                    target_id = account.get("channel_id", "").lower()
                    target_name = account.get("channel_name", "").lower()
                    
                    # 严谨的判断逻辑：只有在 config 确实有填写该栏位(不为空)时，才进行比对
                    match_id = (target_id != "") and (target_id == uploader)
                    match_name = (target_name != "") and (target_name == uploader or target_name in uploader)
                    
                    if match_id or match_name:
                        creator_name = streamer["name"]
                        break
            if creator_name != "Unknown":
                break

        return {
            "status": "success",
            "platform": platform,
            "creator": creator_name,
            "title": title,
            "date": date_str,
            "original_url": url,
            "video_id": video_id
        }

# ==========================================
# 2. yt-dlp 專用解析器 (YouTube, TwitCasting)
# ==========================================
class YtdlpExtractor(BaseMetadataExtractor):
    """專門負責呼叫 yt-dlp 解析 YouTube 與 TwitCasting 的 Metadata"""
    
    def __init__(self, project_root: Path, streamers: List[dict], exe_path: Path):
        super().__init__(project_root, streamers)
        self.exe_path = exe_path

    def analyze(self, url: str) -> Dict:
        if not self.exe_path.exists():
            print(f"[Error] yt-dlp not found: {self.exe_path}")
            return {"status": "error"}

        print(f"[yt-dlp] Parsing video: {url}")
        # 基础命令
        command = [str(self.exe_path), "-j", "--no-warnings", "--ignore-no-formats-error"]
        
        # ========== 新增：检查 Cookie ==========
        print("[Info] Trying to read cookies from Firefox for authorized parsing ...")
        command.extend(["--cookies-from-browser", "firefox"])
        # ==========================================
        
        command.append(url)
        
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True, encoding="utf-8", errors="ignore")
            raw_data = json.loads(result.stdout)
            
            # 判斷平台
            extractor = raw_data.get("extractor_key", "").lower()
            if "youtube" in extractor: platform = "youtube"
            elif "twitcast" in extractor: platform = "twitcast"
            elif "twitter" in extractor: platform = "twitter"
            else: platform = "unknown"

            # 取出 Uploader 與標題
            uploader = raw_data.get("channel_id") or raw_data.get("uploader_id") or raw_data.get("uploader") or ""
            title = raw_data.get("title") or "No Title"
            video_id = raw_data.get("id") or "UnknownID"
            
            # 取出日期
            timestamp = raw_data.get("timestamp")
            if timestamp:
                date_str = datetime.fromtimestamp(timestamp).strftime("%Y%m%d")
            else:
                date_str = raw_data.get("upload_date", "19700101")

            return self._match_and_format(platform, uploader, title, date_str, url, video_id)

        except subprocess.CalledProcessError as e:
            print("[Error] yt-dlp failed.")
            if e.stderr: print(f"        Reason: {e.stderr.strip()}")
            return {"status": "error"}
        except json.JSONDecodeError:
            print("[Error] Failed to parse yt-dlp JSON output.")
            return {"status": "error"}

# ==========================================
# 3. Twitch 專用解析器
# ==========================================
class TwitchExtractor(BaseMetadataExtractor):
    """專門負責呼叫 TwitchDownloaderCLI 解析 Twitch 的 Metadata"""
    
    def __init__(self, project_root: Path, streamers: List[dict], exe_path: Path, oauth_token: str, env_path: Path = None):
        super().__init__(project_root, streamers)
        self.exe_path = exe_path
        self.oauth_token = oauth_token
        self.env_path = env_path  # 僅用於缺 token 時提示使用者該去哪裡設定

    def analyze(self, url: str) -> Dict:
        if not self.exe_path.exists():
            print(f"[Error] TwitchDownloaderCLI not found: {self.exe_path}")
            return {"status": "error"}

        print(f"[Twitch CLI] Parsing Twitch VOD: {url}")
        
        # 根據最新官方文件，直接餵 URL 給 --id 即可，不需要寫正則表達式拆解 ID 了！
        command = [str(self.exe_path), "info", "--id", url]
        
        # 如果有讀取到 OAuth token，就加入指令中 (突破訂閱者限定防護)
        if self.oauth_token:
            # 注意官方文件的參數是 --oauth
            command.extend(["--oauth", self.oauth_token])
        else:
            # 只有 Twitch 需要這個 token，YouTube / TwitCasting 一律不會走到這裡
            print(f"[Warning] twitch_OAuth is not configured in {self.env_path}")
            print("[Warning] Public VODs still work; subscriber-only VODs will fail without it.")

        video_id = "UnknownID"
        id_match = re.search(r"(?:videos/|video=)(\d+)", url)
        if id_match:
            video_id = id_match.group(1)
        
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True, encoding="utf-8")
            # print(f"[Debug] Twitch CLI 原生输出:\n{result.stdout}")
            
            title = "No Title"
            uploader = ""
            date_str = "19700101"
            
            # 逐行解析文字輸出 (支援最新的 ASCII Table 格式)
            for line in result.stdout.split("\n"):
                # 如果這行包含表格的分隔符號 '│'
                if "│" in line:
                    # 用 '│' 切割並去除空白
                    parts = [p.strip() for p in line.split("│")]
                    
                    # parts 會長得像 ['', 'Streamer', '柊優花 (hiiragiyukaofficial)', '']
                    if len(parts) >= 3:
                        key = parts[1]
                        val = parts[2]
                        
                        if key == "Streamer":
                            uploader = val  # 這裡會抓到 "柊優花 (hiiragiyukaofficial)"
                        elif key == "Title":
                            title = val     # 這裡會抓到 "LET's Play!"
                        elif key == "Created at":
                            date_match = re.search(r"(\d{4})[-/]?(\d{1,2})[-/]?(\d{1,2})", val)
                            if date_match:
                                y, m, d = date_match.groups()
                                date_str = f"{y}{int(m):02d}{int(d):02d}"

            return self._match_and_format("twitch", uploader, title, date_str, url, video_id)

        except subprocess.CalledProcessError as e:
            print("[Error] TwitchDownloaderCLI failed (bad URL, or the OAuth token has expired).")
            if e.stderr: print(f"        Reason: {e.stderr.strip()}")
            return {"status": "error"}

# ==========================================
# 4. 工廠類別 (Manager / Factory)
# ==========================================
class MetadataManager:
    """負責讀取設定檔，並根據網址分配正確的 Extractor"""
    
    def __init__(self, project_root: Path, config_dir: Path = None):
        self.project_root = project_root
        # downloader/metadata.py -> 上级(downloader) 的 上级(scripts)
        self.config_dir = config_dir or Path(__file__).resolve().parents[1]
        self.config_path = self.config_dir / "config.yaml"
        self.env_path = self.config_dir / ".env"

        # 載入設定與機密
        load_dotenv(self.env_path)
        
        # 優先讀取你自定義的 twitch_OAuth，若沒有再嘗試讀取全大寫的 TWITCH_OAUTH
        self.twitch_oauth = os.getenv("twitch_OAuth")
        
        self.streamers, self.tools_paths = self._load_config()
        
        # 定義執行檔路徑
        self.ytdlp_exe = self.project_root / "assets" / self.tools_paths.get("yt_dlp", "yt-dlp/yt-dlp.exe")
        self.twitch_cli_exe = self.project_root / "assets" / self.tools_paths.get("twitch_downloader_cli", "TwitchDownloaderCLI/TwitchDownloaderCLI.exe")

    def _load_config(self) -> Tuple[list, dict]:
        if not self.config_path.exists():
            return [], {}
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config.get("streamers", []), config.get("tools_paths", {})

    def get_extractor(self, url: str) -> BaseMetadataExtractor:
        """工廠方法：根據網址特徵，實例化並回傳對應的解析器"""
        if "twitch.tv" in url:
            return TwitchExtractor(self.project_root, self.streamers, self.twitch_cli_exe, self.twitch_oauth, self.env_path)
        else:
            # 預設交給 yt-dlp 處理 (YouTube, TwitCasting 等)
            return YtdlpExtractor(self.project_root, self.streamers, self.ytdlp_exe)

    def analyze(self, url: str) -> Dict:
        """提供一個便利的對外介面，直接一步完成解析"""
        extractor = self.get_extractor(url)
        return extractor.analyze(url)
    
# === 快速測試區塊 ===
if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    manager = MetadataManager(project_root)
    
    test_urls = [
        "https://www.youtube.com/watch?v=Q_Yra_F2c3c", 
        "https://www.twitch.tv/videos/2687840344",
        "https://twitcasting.tv/shino_nome22/movie/831202251",
        "https://www.youtube.com/watch?v=QFDgL7R2nk4",
        "https://www.youtube.com/watch?v=X3FkUzf1Hxk"
    ]
    
    for target_url in test_urls:
        print("-" * 40)
        result = manager.analyze(target_url)
        
        if result["status"] == "success":
            print(f"- platform: {result['platform']}")
            print(f"- creator: {result['creator']}")
            print(f"- date: {result['date']}")
            print(f"- title: {result['title']}")