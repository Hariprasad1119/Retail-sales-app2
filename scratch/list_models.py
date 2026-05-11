import requests
import json

response = requests.get("https://openrouter.ai/api/v1/models")
models = response.json()

free_models = [m['id'] for m in models['data'] if m['id'].endswith(':free')]
print(json.dumps(free_models, indent=2))
