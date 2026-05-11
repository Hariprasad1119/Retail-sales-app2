import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
)

model = "meta-llama/llama-3.2-3b-instruct:free"

try:
    print(f"Testing {model}...")
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "hi"}],
        timeout=10
    )
    print("SUCCESS!")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"FAILED: {e}")
