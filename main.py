from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq()
completion = client.chat.completions.create(
    model="meta-llama/llama-4-maverick-17b-128e-instruct",
    messages=[
      {
        "role": "user",
        "content": "Preten that you are a debt collector from a credit card company. And you are calling me to collect a debt. What questions will you ask me?"
      }
    ],
    temperature=1,
    max_completion_tokens=1024,
    top_p=1,
    stream=True,
    stop=None
)

for chunk in completion:
    print(chunk.choices[0].delta.content or "", end="")