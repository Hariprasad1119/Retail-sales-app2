import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize OpenRouter client
# Make sure OPENROUTER_API_KEY is set in your .env file
api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    print("Error: OPENROUTER_API_KEY not found in .env file")
    exit(1)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
)

def ask_bot(user_message, context=None):
    try:
        messages = []
        if context:
            system_msg = (
                "You are a friendly Sales Data Assistant. "
                "RULE 1: If the user says 'hi', 'hello', or 'hey', ONLY greet them back and ask how you can help. DO NOT show any sales numbers or summaries yet. "
                "RULE 2: Only use the provided sales data if the user asks a specific question about revenue, products, or trends. "
                "RULE 3: Do not provide a summary of the data unless explicitly asked for a 'summary'. "
                "Keep your responses concise and conversational.\n\n"
                f"Context:\n{context}"
            )
            messages.append({"role": "system", "content": system_msg})
        
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model="openrouter/auto",
            messages=messages,
            timeout=20, # Increased for reliability
            extra_headers={
                "HTTP-Referer": "http://localhost:3000",
                "X-Title": "Retail Sales App",
            }
        )
        return response.choices[0].message.content
    except Exception as e:
        # EXAM-PROOF FALLBACK: If API fails, use the context to answer basic questions
        if context:
            # Extract basic info from context string using simple parsing
            try:
                # This is a simple 'Offline AI' simulation
                if "top product" in user_message.lower() or "best product" in user_message.lower():
                    import re
                    match = re.search(r"Top Product: (.*?)\n", context)
                    if match: return f"[Offline Mode] I'm having trouble connecting to the cloud, but I can see from your local data that your top selling product is {match.group(1)}."
                
                if "revenue" in user_message.lower() or "total sales" in user_message.lower():
                    import re
                    match = re.search(r"Total Revenue: (.*?)\n", context)
                    if match: return f"[Offline Mode] Cloud AI is unavailable, but your local analysis shows a Total Revenue of {match.group(1)}."

                return "[Offline Mode] I'm currently unable to reach the cloud AI, but I have analyzed your data locally. You can see the full breakdown in the charts and KPIs above!"
            except:
                pass
        
        return "I'm having trouble connecting to the AI right now. Please check your API key or internet connection."

if __name__ == "__main__":
    print("Chatbot: " + ask_bot("Hello, who are you?"))

