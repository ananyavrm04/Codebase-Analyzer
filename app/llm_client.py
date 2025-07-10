import os
import together

together.api_key = os.environ.get("TOGETHER_API_KEY")

def summarize_code(code: str) -> str:
    prompt = f"""
You're reviewing the following Python code. Summarize what it does and optionally suggest any improvements:

{code}
"""
    try:
        res = together.Complete.create(
            prompt=prompt,
            model="mistralai/Mistral-7B-Instruct-v0.1",
            max_tokens=300,
            temperature=0.5,
        )
        return res.get("output", "No summary returned.")
    except Exception as err:
        return f"LLM request failed: {str(err)}"

