# post_process/youtube_chat_parser.py
import json
from pathlib import Path
from .base import BaseChatParser

class YoutubeChatParser(BaseChatParser):
    
    def extract_messages(self, input_path: Path) -> list:
        """实现 YouTube 特定的 JSONL 解析逻辑"""
        parsed_chat = []
        with open(input_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    actions = item.get('replayChatItemAction', {}).get('actions', [])
                    if not actions:
                        continue
                    
                    item_data = actions[0].get('addChatItemAction', {}).get('item', {}).get('liveChatTextMessageRenderer')
                    if not item_data:
                        continue
                    
                    # 获取时间
                    offset_str = item.get('videoOffsetTimeMsec')
                    if offset_str is not None:
                        offset_sec = max(0, int(offset_str) / 1000.0)
                        time_str = self._format_seconds(offset_sec)
                    else:
                        time_str = item_data.get('timestampText', {}).get('simpleText', '00:00:00')
                        parts = time_str.split(':')
                        if len(parts) == 2:
                            time_str = f"00:{int(parts[0]):02d}:{int(parts[1]):02d}"
                        elif len(parts) == 3:
                            time_str = f"{int(parts[0]):02d}:{int(parts[1]):02d}:{int(parts[2]):02d}"
                    
                    user = item_data.get('authorName', {}).get('simpleText', 'Unknown')
                    
                    # 获取消息
                    msg = ""
                    for r in item_data.get('message', {}).get('runs', []):
                        if 'text' in r:
                            msg += r['text']
                        elif 'emoji' in r:
                            shortcuts = r['emoji'].get('shortcuts', [])
                            if shortcuts:
                                msg += shortcuts[0]
                    
                    if msg.strip():
                        parsed_chat.append({"time": time_str, "user": user, "msg": msg})
                        
                except json.JSONDecodeError:
                    continue
                    
        return parsed_chat