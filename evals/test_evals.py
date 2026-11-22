"""Eval suite: run each question in cases.json through the RAG app and check the answer."""

import json
from functools import lru_cache
from pathlib import Path

import pytest

from answer import ask

IDK = "I don't know based on the provided pytest docs."

CASES = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))
ANSWERABLE = [c for c in CASES if c["expected_page"]]
UNANSWERABLE = [c for c in CASES if not c["expected_page"]]


@lru_cache(maxsize=None)
def cached_ask(question):
    """Ask each question only once, even when several tests check the same answer."""
    return ask(question)


def case_ids(cases):
    return [c["id"] for c in cases]


@pytest.mark.parametrize("case", ANSWERABLE, ids=case_ids(ANSWERABLE))
def test_retrieval_has_key_facts(case):
    """Context recall: did search hand the LLM the chunks it needs to answer?"""
    _, chunks = cached_ask(case["question"])
    sources = [c["source"] for c in chunks]
    retrieved = " ".join(c["text"] for c in chunks).lower()
    missing = [f for f in case["must_include"] if f.lower() not in retrieved]
    assert any(case["expected_page"] in s for s in sources), (
        f"Expected a chunk from {case['expected_page']}, got: {sources}"
    )
    assert not missing, f"Key facts not in any retrieved chunk: {missing}\nChunks: {[c['id'] for c in chunks]}"


@pytest.mark.parametrize("case", ANSWERABLE, ids=case_ids(ANSWERABLE))
def test_answer_has_key_facts(case):
    answer, _ = cached_ask(case["question"])
    text = answer.lower()
    missing = [f for f in case["must_include"] if f.lower() not in text]
    wrong = [w for w in case["must_not_include"] if w.lower() in text]
    assert IDK.lower() not in text, f"Refused an answerable question.\nAnswer:\n{answer}"
    assert not missing, f"Missing key facts: {missing}\nAnswer:\n{answer}"
    assert not wrong, f"Contains wrong claims: {wrong}\nAnswer:\n{answer}"


@pytest.mark.parametrize("case", UNANSWERABLE, ids=case_ids(UNANSWERABLE))
def test_says_i_dont_know(case):
    answer, _ = cached_ask(case["question"])
    assert answer.strip() == IDK, f"Expected the 'I don't know' reply.\nAnswer:\n{answer}"
