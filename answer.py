"""RAG: find the best doc chunks for a question, then ask the LLM to answer from them."""

import sys

from llm import generate
from search import search

SYSTEM_PROMPT = """You answer questions about pytest using ONLY the documentation excerpts provided.
Rules:
- Base your answer only on the excerpts. Do not use outside knowledge.
- If the excerpts do not contain the answer, reply exactly: "I don't know based on the provided pytest docs." and nothing else.
- Keep answers short and practical. Include a small code example when the excerpts show one.
- Only when you answered from the excerpts, end with "Sources:" and the excerpt numbers you used, like [1], [3]."""


def build_prompt(question, chunks):
    """Put the numbered excerpts and the question into one prompt."""
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        parts.append(f"[{i}] (source: {chunk['source']})\n{chunk['text']}")
    excerpts = "\n\n".join(parts)
    return f"Documentation excerpts:\n\n{excerpts}\n\nQuestion: {question}"


def ask(question):
    """Answer a question from the pytest docs. Returns the answer and the chunks it was given."""
    chunks = search(question)
    answer = generate(SYSTEM_PROMPT, build_prompt(question, chunks))
    return answer, chunks


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "How do I skip a test?"
    answer, chunks = ask(question)
    print(f"Question: {question}\n")
    print(answer)
    print("\nRetrieved chunks:")
    for i, c in enumerate(chunks, start=1):
        print(f"  [{i}] {c['id']}  (distance {c['distance']:.3f})")