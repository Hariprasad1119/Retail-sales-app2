import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
)

models = [
    "google/gemini-2.0-flash-exp:free",
    "google/gemini-flash-1.5-8b:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "mistralai/mistral-7b-instruct:free"
]

for model in models:
    try:
        print(f"Testing {model}...", end=" ")
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            timeout=10
        )
        print("WORKS")
    except Exception as e:
        print(f"FAILED: {e}")
