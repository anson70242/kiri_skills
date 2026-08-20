# downloader/base.py
import os
import re
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional

class BaseDownloader(ABC):
    """所有平台下载器的抽象基类 (支持视频与聊天室弹幕分离下载)"""
    
    def __init__(self, project_root: Path, metadata: Dict, output_dir: Path, tools_paths: Dict, download_settings: Dict = None, config_dir: Path = None):
        """
        初始化下载器
        :param project_root: 项目根目录 Path (下面是 assets/ 与 videos/)
        :param metadata: 由 MetadataManager 获取到的元数据字典
        :param output_dir: 文件保存的输出目录 Path
        :param tools_paths: config.yaml 中的 tools_paths 字典
        :param download_settings: config.yaml 中的 download_settings 字典 (新增)
        :param config_dir: 配置文件目录 (config.yaml / .env 所在的 scripts/)，默认自动推断
        """
        self.project_root = project_root
        self.metadata = metadata
        self.output_dir = output_dir
        self.tools_paths = tools_paths
        self.download_settings = download_settings or {} # 保存下载设置
        # downloader/base.py -> 上级(downloader) 的 上级(scripts)
        self.config_dir = config_dir or Path(__file__).resolve().parents[1]

        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def download_video(self) -> Optional[Path]:
        """
        下载视频文件的核心方法。
        子类必须实现此方法。
        :return: 下载成功返回视频文件的完整 Path，失败返回 None
        """
        pass

    @abstractmethod
    def download_chat(self) -> Optional[Path]:
        """
        下载聊天室/弹幕的核心方法。
        子类必须实现此方法。
        :return: 下载成功返回弹幕文件的完整 Path，失败返回 None
        """
        pass

    def download_all(self) -> Dict[str, Optional[Path]]:
        """
        一键调度：依次下载视频和聊天室记录
        :return: 包含 video 和 chat 路径的字典
        """
        print(f"Processing: {self.metadata.get('title')}")
        
        video_path = self.download_video()
        chat_path = self.download_chat()
        
        return {
            "video": video_path,
            "chat": chat_path
        }

    def get_tool_path(self, tool_key: str) -> Path:
        """
        获取内置工具的绝对路径并验证文件是否存在。
        例如: self.get_tool_path("yt_dlp")
        """
        tool_rel_path = self.tools_paths.get(tool_key)
        if not tool_rel_path:
            raise ValueError(f"Tool path not found in config: {tool_key}")

        tool_path = self.project_root / "assets" / tool_rel_path
        if not tool_path.exists():
            raise FileNotFoundError(f"Tool executable does not exist: {tool_path}")
            
        return tool_path

    def generate_output_path(self, suffix: str = "", ext: str = "mp4") -> Path:
        """
        根据 metadata 统一生成标准化的输出文件路径。
        :param suffix: 文件名后缀，例如 "_chat"
        :param ext: 文件副档名，例如 "mp4" 或 "json"
        
        示例输出: 
        - 视频: [youtube][20250109][Yuka] 直播标题.mp4
        - 弹幕: [twitch][20250109][Yuka] 直播标题_chat.json
        """
        date_str = self.metadata.get("date", "19700101")
        creator = self.metadata.get("creator", "Unknown")
        title = self.metadata.get("title", "No Title")
        
        # 清理 Windows/Linux 文件名中的非法字符
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
        # 去除多余空格
        safe_title = " ".join(safe_title.split())
        
        platform = self.metadata.get("platform", "unknown")
        filename = f"[{platform}][{date_str}][{creator}] {safe_title}{suffix}.{ext}"
        
        return self.output_dir / filename
    
    def _get_node_env(self) -> dict:
        """
        共用：构造包含内置 Node.js 路径的临时环境变量
        供 yt-dlp 和 TwitchDownloaderCLI 解析和抓取时使用
        """
        env = os.environ.copy()
        try:
            # 这里调用你写好的 get_tool_path，自带异常检查
            node_exe = self.get_tool_path("node") 
            node_dir = os.path.dirname(str(node_exe))
            env["PATH"] = f"{node_dir}{os.pathsep}{env.get('PATH', '')}"
        except Exception:
            # 如果没配置 Node.js 路径，静默跳过
            pass 
        return env

    def run_command(self, command: list, env: Optional[dict] = None) -> bool:
        """
        公共的命令行执行辅助方法
        :param command: 命令列表
        :param env: 临时环境变量字典 (可选)
        """
        try:
            print(f"[Exec] Running: {' '.join(str(c) for c in command)}")
            # 关键修改：如果没有传入专属 env，就默认带上 Node.js 环境
            exec_env = env if env else self._get_node_env()
            subprocess.run(command, check=True, env=exec_env)
            return True
        except subprocess.CalledProcessError as e:
            print(f"[Error] Command failed with return code: {e.returncode}")
            return False