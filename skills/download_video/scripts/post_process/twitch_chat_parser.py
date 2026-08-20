# post_process/twitch_chat_parser.py
import json
from pathlib import Path
from .base import BaseChatParser

class TwitchChatParser(BaseChatParser):
    
    def extract_messages(self, input_path: Path) -> list:
        """实现 Twitch 特定的 JSON 解析逻辑"""
        parsed_chat = []
        with open(input_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
            
        for c in json_data.get('comments', []):
            offset = c.get('content_offset_seconds', 0)
            time_str = self._format_seconds(offset)
            
            commenter = c.get('commenter') or {}
            user = commenter.get('display_name', 'Unknown')
            
            msg = c.get('message', {}).get('body', '')
            
            if msg.strip():
                parsed_chat.append({"time": time_str, "user": user, "msg": msg})
                
        return parsed_chat