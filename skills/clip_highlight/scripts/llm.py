# clip_highlight/scripts/llm.py
"""LLM 层：只负责跟 Gemini 打交道，不认识字幕、分片这些业务概念"""
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors

# 显式指向 scripts/.env —— load_dotenv() 默认从 CWD 往上找，
# 从仓库根目录跑脚本时会找不到这份 .env。
load_dotenv(Path(__file__).resolve().parent / ".env")

# 用 `or` 兜底：变量缺失时 os.getenv 返回 None，
# int(None) 会在 import 阶段就抛 TypeError，让整个模块直接没法被导入。
MODEL = os.getenv("model") or ""
WAITING_TIME = int(os.getenv("waiting_time") or 60)
MAX_RETRY = int(os.getenv("max_retry") or 3)

# 429 是配额，5xx 是服务端瞬时故障，两类都值得重试；
# 4xx 里除 429 外(400 参数错、401 密钥错、404 模型名错)重试多少次都是一样的结果。
RETRYABLE_CODES = (429, 500, 502, 503, 504)
SERVER_ERROR_BACKOFF = 5

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def call_llm(client, model, system_prompt, user_prompt, session_id=None):
    """发一轮对话。session_id 为 None 时开新会话，否则接在上一轮后面

    只做被动重试，不做主动限流。实测一场 2 小时直播按 800 块切只有 2 个分片、
    单轮约 33k token，离 RPM=15 / TPM=2.5M / RPD=500 都差一个数量级；
    而且响应里 total_thought_tokens 能占到 90% 以上且无法从输入长度预估，
    本地记账算不准配额。真正会遇到的只有共享容量导致的偶发 429/5xx。
    """
    for attempt in range(MAX_RETRY + 1):
        try:
            interaction = client.interactions.create(
                model=model,
                system_instruction=system_prompt,
                input=user_prompt,
                previous_interaction_id=session_id,
            )
            return interaction.output_text, interaction.id

        except errors.APIError as exc:
            if exc.code not in RETRYABLE_CODES or attempt == MAX_RETRY:
                raise

            # 429 是配额窗口没过，等满一整个窗口最省事 —— 提前重试只是白白再吃一次拒绝；
            # 5xx 是瞬时容量问题，指数退避通常几秒内就恢复。
            if exc.code == 429:
                delay = WAITING_TIME
            else:
                delay = SERVER_ERROR_BACKOFF * (2 ** attempt)

            print(
                f"[Warning] API returned {exc.code}, retrying in {delay}s "
                f"(attempt {attempt + 1}/{MAX_RETRY})"
            )
            time.sleep(delay)
