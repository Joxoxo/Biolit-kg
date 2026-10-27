"""第 1 天目标：跑通第一次 Gemini 调用。

运行方法（在 biolit-kg 文件夹下）：
    python scripts/hello_llm.py
"""
import os

from dotenv import load_dotenv
from google import genai

# 1. 从 .env 文件读取 API Key 和模型名
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

if not api_key or "填" in api_key:
    raise SystemExit("没有找到 API Key：请把 .env.example 复制为 .env 并填入 Key")

# 2. 创建客户端并发送一个问题
client = genai.Client(api_key=api_key)
response = client.models.generate_content(
    model=model,
    contents="用一句话说明华法林为什么容易和其他药物发生相互作用。",
)

# 3. 打印模型的回答
print(f"模型：{model}")
print(response.text)
