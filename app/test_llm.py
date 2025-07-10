import os
import together

together.api_key = os.environ.get("TOGETHER_API_KEY")

response = together.chat.completions.create(
    model="meta-llama/Llama-3-8b-chat-hf",
    messages=[
        {"role": "user", "content": "Summarize what this code does:\ndef hello(): print('Hello')"}
    ]
)

print(response.choices[0].message.content)


