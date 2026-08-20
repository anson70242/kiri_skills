# core/config.py
import os
import re
import sys
import yaml
from pathlib import Path

def configure_utf8_stdio() -> None:
    """强制 stdout / stderr 使用 UTF-8 输出

    Windows 控制台与管道默认是 cp950 或 cp936，直播标题里的日文与 emoji
    会触发 UnicodeEncodeError 让整个程序崩溃。无法编码的字符降级替换。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

def get_base_path() -> Path:
    """项目根目录：下面放 assets/ (内置工具) 与 videos/ (下载产物)

    当前文件在 scripts/core/config.py，所以根目录是它的
    上级(core) 的 上级(scripts) 的 上级(根目录)。
    """
    return Path(__file__).resolve().parents[2]

def get_config_dir() -> Path:
    """配置文件目录：config.yaml 与 .env 都放在 scripts/ 下

    注意这与 get_base_path() 不同 —— 配置文件跟着脚本走，
    而内置工具 (assets/) 与下载产物 (videos/) 放在项目根目录。
    """
    return Path(__file__).resolve().parents[1]

class ConfigManager:
    """全局配置与路径管理器"""
    def __init__(self, project_root: Path, config_dir: Path = None):
        self.project_root = project_root
        self.config_dir = config_dir or get_config_dir()
        self.config_data = self._load_yaml()
        self.tools_paths = self.config_data.get("tools_paths", {})
        self.streamers = self.config_data.get("streamers", [])
        self.whisper_config = self.config_data.get("whisper", {})
        self.prompts_paths = self.config_data.get("prompts", {})

    def _load_yaml(self) -> dict:
        config_path = self.config_dir / "config.yaml"
        if not config_path.exists():
            print(f"[Error] Config file not found: {config_path}")
            return {}
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def get_tool_exe(self, tool_name: str, default_path: str) -> Path:
        """获取工具的绝对路径"""
        rel_path = self.tools_paths.get(tool_name, default_path)
        return self.project_root / "assets" / rel_path
    
    def get_prompt_path(self, prompt_key: str) -> Path:
        """新增：获取 Prompt Markdown 文件的绝对路径"""
        rel_path = self.prompts_paths.get(prompt_key)
        if rel_path:
            return self.project_root / rel_path
        return None
    
    @staticmethod
    def sanitize_filename(name: str) -> str:
        """清除 Windows 档案/文件夹名称中不允许的特殊字符"""
        return re.sub(r'[\\/*?:"<>|]', "_", name)

    def get_output_dir(self, creator: str, date_str: str, title: str) -> Path:
        """统一生成标准的输出文件夹路径: videos/streamer_name/video_date/title/"""
        safe_creator = self.sanitize_filename(creator)
        safe_date = self.sanitize_filename(date_str)
        safe_title = self.sanitize_filename(title)
        
        output_dir = self.project_root / "videos" / safe_creator / safe_date / safe_title
        # output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir