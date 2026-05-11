import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
)

models_to_try = [
    "google/gemini-2.0-flash-exp:free",
    "google/gemini-flash-1.5-8b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "openrouter/auto" # To see what it defaults to
]

for model in models_to_try:
    print(f"\nTesting model: {model}")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "test"}],
            timeout=10,
            extra_headers={
                "HTTP-Referer": "http://localhost:3000",
                "X-Title": "Retail Sales App Test",
            }
        )
        print(f"✅ Success with {model}!")
        print(f"Content: {response.choices[0].message.content[:50]}...")
        break
    except Exception as e:
        print(f"❌ Failed with {model}: {str(e)}")
