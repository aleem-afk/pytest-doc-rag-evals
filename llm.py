import os 
from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "openai")
MODEL = os.getenv("LLM_MODEL")

def generate(system, prompt):
    """Send instructions + a prompt to the configured LLM and return its text answer."""
    if not MODEL:
        raise ValueError("LLM_MODEL is not set in .env")
    if PROVIDER == "openai":
        return _generate_openai(system, prompt)
    raise ValueError(f"Unknown LLM_PROVIDER '{PROVIDER}'. Supported: openai")


def _generate_openai(system, prompt):
    from openai import OpenAI  # imported here, so other providers don't need this package

    client = OpenAI()  # automatically reads OPENAI_API_KEY from the environment
    response = client.responses.create(model=MODEL, instructions=system, input=prompt)
    return response.output_text


if __name__ == "__main__":
    print(f"Provider: {PROVIDER} | Model: {MODEL}")
    print(generate("You are a helpful assistant. Reply in one short sentence.", "Say hello!"))