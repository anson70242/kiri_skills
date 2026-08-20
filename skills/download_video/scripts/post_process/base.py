# post_process/base.py
import json
import math
from abc import ABC, abstractmethod
from pathlib import Path

class BaseChatParser(ABC):
    """弹幕解析器的抽象基类"""

    def _format_seconds(self, total_seconds: float) -> str:
        """共用：将秒数转换为 HH:MM:SS 格式"""
        h = math.floor(total_seconds / 3600)
        m = math.floor((total_seconds % 3600) / 60)
        s = math.floor(total_seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    @abstractmethod
    def extract_messages(self, input_path: Path) -> list:
        """
        核心抽象方法：子类必须实现此方法。
        负责读取特定平台的原始文件，并返回格式化后的字典列表：
        [{"time": "00:00:00", "user": "name", "msg": "text"}, ...]
        """
        pass

    def parse(self, input_path: Path, output_path: Path) -> bool:
        """模板方法：控制清洗的整体流程（读取 -> 提取 -> 保存 -> 删除原档）"""
        if not input_path.exists():
            print(f"[Error] Input file not found: {input_path}")
            return False

        try:
            # 1. 调用子类各自的提取逻辑
            parsed_chat = self.extract_messages(input_path)

            if not parsed_chat:
                print(f"[Warning] No valid chat messages were extracted from: {input_path.name}")
                return False

            # 2. 共用的写入逻辑
            lines = [f'  {json.dumps(c, ensure_ascii=False)}' for c in parsed_chat]
            custom_json_output = "[\n" + ",\n".join(lines) + "\n]"

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(custom_json_output)

            print(f"[Success] Chat cleaning finished, {len(parsed_chat)} messages extracted")

            # 3. 共用的删除原始文件逻辑
            try:
                input_path.unlink()
                print(f"[Info] Removed the raw unprocessed chat file: {input_path.name}")
            except Exception as e:
                print(f"[Warning] Failed to remove the raw chat file: {e}")

            return True

        except Exception as e:
            print(f"[Error] Fatal error while cleaning the chat: {e}")
            return False