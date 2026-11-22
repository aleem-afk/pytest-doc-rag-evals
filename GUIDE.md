# Build Guide: Ask the pytest docs

A step-by-step guide to building this project yourself, from an empty folder to a live app.
Each step tells you what to run, what it does, and how to check it worked.

## What we're building

You ask a question about pytest, like "how do fixtures work?". The app finds the most relevant
parts of the pytest docs and sends them to an LLM, which writes an answer based only on those parts.
This pattern is called **RAG** (Retrieval-Augmented Generation).

Then we write **evals**: pytest tests that check whether the answers are actually correct.

```
question → search the doc chunks → top matches + question → LLM → answer
```

## Before you start

- **Python 3.10 or newer.** Check with `python --version`.
- **Git.** Check with `git --version`.
- **A terminal.** This guide uses PowerShell on Windows. On Mac/Linux, the activate command is different (noted below).

---

## Step 1: Project setup

**Goal:** a project folder with its own private Python environment.

**1. Create the folder and go into it**
```
mkdir ask-pytest-docs
cd ask-pytest-docs
```

**2. Create a virtual environment**
```
python -m venv .venv
```
This creates a `.venv` folder containing a private copy of Python just for this project.
Why bother? This project installs big packages (PyTorch alone is over 1 GB). Keeping them in
a venv means they can't clash with your other projects. Later, when we deploy, only the packages
listed in `requirements.txt` get installed. A clean venv helps you catch a missing one early.

**3. Activate it**
```
.venv\Scripts\Activate.ps1
```
(Mac/Linux: `source .venv/bin/activate`)

You'll see `(.venv)` at the start of your prompt. Do this **every time you open a new terminal** for this project.

> **Error: "running scripts is disabled on this system"?**
> Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, answer `Y`, then try again.
> This allows local scripts to run for your Windows user only.

**4. Turn the folder into a git repo**
```
git init
```
Git will now track changes to your files, so you can save snapshots (commits) and push to GitHub later.

**5. Create three starter files**

`.gitignore`: tells git which files to never save:
```
.venv/
.env
chroma_db/
__pycache__/
*.pyc
.pytest_cache/
```
- `.venv/`: anyone can recreate it, and it's huge.
- `.env`: this will hold your API key. **Never commit secrets.**
- `chroma_db/`: the database we build in Step 3. It can be rebuilt from the docs.
- The rest are Python's cache files.

`requirements.txt`: the list of packages this project needs. Start it with just a comment:
```
# Packages this project needs. We add to this list step by step.
```

`.env.example`: a template showing which secrets are needed, without the real values:
```
LLM_API_KEY=
```
In Step 4 you'll copy this to `.env` and paste your real key there.

**✅ Check it worked:** run `git status`. You should see your three files, plus this guide if you've
saved it in the folder, but **not** `.venv`, because git is ignoring it.

---

## Step 2: Download the docs and split them into chunks

**Goal:** turn a few pytest doc pages into small, clean text pieces ("chunks") saved in a file.

Why chunks? An LLM can't read the whole documentation for every question. So we cut the
docs into small pieces, and later we search for the 3 or 4 pieces that best match the question.

**1. Install two packages** (with your venv activated)
```
pip install requests beautifulsoup4
```
- `requests` downloads web pages from Python.
- `beautifulsoup4` reads a page's HTML so we can pull out just the text, skipping menus and footers.

Then add them to `requirements.txt`:
```
requests
beautifulsoup4
```

**2. Write `ingest.py`**

Create `ingest.py` in the project folder:

```python
"""Download a few pytest doc pages, clean them, and split them into chunks."""

import json
import os

import requests
from bs4 import BeautifulSoup

# The pytest doc pages we use as our knowledge base
URLS = [
    "https://docs.pytest.org/en/stable/getting-started.html",
    "https://docs.pytest.org/en/stable/how-to/fixtures.html",
    "https://docs.pytest.org/en/stable/how-to/parametrize.html",
    "https://docs.pytest.org/en/stable/how-to/assert.html",
    "https://docs.pytest.org/en/stable/how-to/mark.html",
]

CHUNK_SIZE = 800  # target size of each chunk, in characters
OUTPUT_FILE = "data/chunks.json"


def download_text(url):
    """Download a page and return its main text as a list of clean lines."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()  # stop with an error if the download failed

    soup = BeautifulSoup(response.text, "html.parser")
    main = soup.find(attrs={"role": "main"}) or soup.body  # skip menus/sidebars

    # Remove the little "¶" link symbols next to headings
    for link in main.find_all("a", class_="headerlink"):
        link.decompose()

    text = main.get_text()
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return lines


def make_chunks(lines, size=CHUNK_SIZE):
    """Group lines into chunks of about `size` characters.
    Each new chunk starts with the last line of the previous one (overlap)."""
    chunks = []
    current = []
    for line in lines:
        current.append(line)
        if len("\n".join(current)) >= size:
            chunks.append("\n".join(current))
            current = [line]  # carry the last line over as overlap
    if len(current) > 1 or not chunks:  # save leftovers (not just the overlap line)
        chunks.append("\n".join(current))
    return chunks


def main():
    all_chunks = []
    for url in URLS:
        lines = download_text(url)
        chunks = make_chunks(lines)
        page_name = url.split("/")[-1]  # e.g. "fixtures.html"
        print(f"{page_name}: {len(chunks)} chunks")
        for i, text in enumerate(chunks):
            all_chunks.append({"id": f"{page_name}-{i}", "source": url, "text": text})

    os.makedirs("data", exist_ok=True)  # create the data folder if it's missing
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(all_chunks)} chunks to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
```

What the pieces do:
- **`download_text`** downloads a page, keeps only the main article (`role="main"`), removes the `¶`
  heading links and returns the non-empty lines. `rstrip()` trims only the right side, so code keeps its indentation.
- **`make_chunks`** adds lines until a chunk reaches about 800 characters, then starts a new one (I started
  with 500; Step 5's evals showed 800 retrieves better).
  Each new chunk repeats the last line of the previous one (**overlap**), so an idea that crosses
  a chunk boundary isn't lost.
- **`main`** runs everything, gives each chunk an `id` (like `fixtures.html-3`) and its `source` URL,
  and saves it all to `data/chunks.json`. The source lets the app show where an answer came from later.
- **`if __name__ == "__main__":`** runs `main()` only when you run the file directly, not when another file imports it.

**3. Run it**
```
python ingest.py
```
It prints a summary per page and saves the real output to `data/chunks.json`. Running it again
overwrites the file.

**✅ Check it worked:** don't stop at "no errors". **Open `data/chunks.json` and read a few chunks.**
They should read like normal sentences, and code examples should look like real Python.
I got 195 chunks of roughly 300–750 characters each. Your numbers may differ slightly if the docs have changed.

> **Lesson learned: inspect your data.** My first version used `main.get_text(separator="\n")`.
> It ran fine, but the text came out shredded: one word per line (`Install` / `pytest` / `into a...`),
> because the separator adds a line break between *every* HTML tag, including inline ones.
> About 77% of lines were a single word. Plain `get_text()` keeps the page's own line breaks and fixed it.
> Bad chunks mean bad search and bad answers later, so always look at what your pipeline actually produces.

> **Tip:** when pasting code, make sure no stray characters (like `│` box borders copied from a
> terminal) came along. If an editor tab shows a broken version, close it **without saving**
> so it doesn't overwrite the good file.

---

## Step 3: Store the chunks in Chroma and test search

**Goal:** type a question and get back the doc chunks that best match it **by meaning**, not just by matching words.

**How it works:** we turn every chunk into an **embedding**, a list of 384 numbers that captures what
the text is about. Texts with similar meaning get similar numbers. **Chroma** is a database that stores
these embeddings and quickly finds the ones closest to a question's embedding.
So "how do I share setup code?" can find fixture chunks even if they never use the word "share".

**1. Install two packages** (venv activated!)
```
pip install chromadb sentence-transformers
```
- `chromadb` is the vector database. It saves to a local folder (`chroma_db/`, already in `.gitignore`).
- `sentence-transformers` runs the embedding model **on your own computer**: free, private, no API key.
- This is a big download (1–2 GB, mostly PyTorch). It can take several minutes.

Add both to `requirements.txt`.

> **Pitfall: make sure it goes into the venv.** I once ran `pip install` in a terminal *without*
> the venv activated, and everything went into my main Python instead. The venv stayed empty,
> and the install even changed versions of packages my main Python already had.
> Check with `python -m pip list`, run from your activated terminal. The safest form is to call
> the venv's Python directly: `.venv\Scripts\python.exe -m pip install ...`

**2. Write `build_index.py`** (run once, and again whenever the chunks change)

```python
"""Turn each chunk into an embedding and store it in a Chroma database."""

import json

import chromadb
from sentence_transformers import SentenceTransformer

CHUNKS_FILE = "data/chunks.json"
DB_PATH = "chroma_db"
COLLECTION_NAME = "pytest_docs"
MODEL_NAME = "all-MiniLM-L6-v2"


def main():
    with open(CHUNKS_FILE, encoding="utf-8") as f:
        chunks = json.load(f)
    print(f"Loaded {len(chunks)} chunks")

    # Load the embedding model (downloads ~90 MB the first time, then it's cached)
    model = SentenceTransformer(MODEL_NAME)
    texts = [c["text"] for c in chunks]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)

    # Open (or create) the database folder on disk
    client = chromadb.PersistentClient(path=DB_PATH)

    # Start fresh each run, so re-running doesn't create duplicates
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass  # it didn't exist yet - that's fine
    collection = client.create_collection(COLLECTION_NAME)

    collection.add(
        ids=[c["id"] for c in chunks],
        documents=texts,
        embeddings=embeddings.tolist(),
        metadatas=[{"source": c["source"]} for c in chunks],
    )
    print(f"Stored {collection.count()} chunks in {DB_PATH}/")


if __name__ == "__main__":
    main()
```
- **`all-MiniLM-L6-v2`** is a small (~90 MB), fast, popular embedding model. It downloads automatically the first time.
- **`model.encode(...)`** turns each text into 384 numbers. `normalize_embeddings=True` scales them all
  to the same length, so the distance between two embeddings reflects only similarity in meaning.
- **`PersistentClient`** saves the database to disk, so search can reuse it without re-embedding.
- **Delete, then create the collection:** a collection is like a table. Wiping it first means re-running never stores duplicates.
- **`collection.add`** stores the id, text, embedding and source URL of every chunk, so results can show *what* matched and *where it came from*.

Run it:
```
python build_index.py
```
**✅ Check:** it ends with `Stored <N> chunks in chroma_db/`, where N matches the number of chunks from Step 2.

> **Harmless warnings you'll see:** "unauthenticated requests to the HF Hub" (no token is needed for a
> public model) and "symlinks not supported" (Windows just uses a bit more disk space for the cache).

**3. Write `search.py`**

```python
"""Search the Chroma database for the chunks that best match a question."""

import sys

import chromadb
from sentence_transformers import SentenceTransformer

from build_index import COLLECTION_NAME, DB_PATH, MODEL_NAME

# Load the model and open the database once, when this file is imported
model = SentenceTransformer(MODEL_NAME)
collection = chromadb.PersistentClient(path=DB_PATH).get_collection(COLLECTION_NAME)


def search(question, k=5):
    """Return the k chunks closest in meaning to the question."""
    query_embedding = model.encode([question], normalize_embeddings=True).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=k)

    # Chroma returns lists-of-lists (one list per question); we asked one question, so take [0]
    matches = []
    for chunk_id, text, meta, distance in zip(
        results["ids"][0], results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        matches.append({"id": chunk_id, "text": text, "source": meta["source"], "distance": distance})
    return matches


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "How do I share a fixture across multiple test files?"
    print(f"Question: {question}\n")
    for m in search(question):
        print(f"--- {m['id']}  (distance {m['distance']:.3f})")
        print(m["text"][:300] + "...\n")
```
- **`from build_index import ...`** reuses the same settings, so search can never use a different model or database by accident.
- **The question must be embedded with the same model** as the chunks, or the numbers can't be compared.
- **`collection.query`** returns the `k` closest chunks. **Distance:** lower means closer (0 = same meaning, 2 = opposite).
  Around 0.7–1.0 is a solid match here.
- `sys.argv[1:]` holds the words typed after the filename, so you can pass a question on the command line.

Run it:
```
python search.py How do I run the same test with different inputs?
```

**4. Test the search with real questions**

Pick questions where you *know* which page should answer them, and check two things:
**is it the right page**, and **does the text actually answer the question?**

My first results (with `k=3` and 5 pages):

| Question | Right page? | Answer in results? |
|---|---|---|
| Share a fixture across files | ✅ fixtures | ⚠️ the `conftest.py` chunks ranked #4–5, just outside the top 3 |
| Same test, different inputs | ✅ parametrize | ✅ shows `@pytest.mark.parametrize` |
| Check a function raises | ✅ assert | ✅ shows `pytest.raises` (one chunk was the legacy style) |
| Skip a test | ❌ | ❌ unrelated chunks, best distance jumped to 1.29 |

**Two fixes, and why:**
- **The skip question failed because skipping has its own docs page, which we hadn't downloaded.**
  Search can only find what's in the database. Fix: add
  `https://docs.pytest.org/en/stable/how-to/skipping.html` to `URLS` in `ingest.py`, then re-run
  `ingest.py` **and then** `build_index.py` (the order matters: the second reads what the first writes).
  Result: 217 chunks, and 4 of the top 5 matches now come from the skipping page, including `@pytest.mark.skip`.
- **The fixture answer was just outside the top 3.** Fix: return 5 chunks instead of 3 (`k=5` in `search.py`).
  It costs a slightly longer prompt to the LLM later, which is cheap, and gives it a better chance of seeing the real answer.
  Result: two chunks that mention `conftest.py` now appear (#4 and #5). But they only use it *in examples*.
  None of our chunks plainly says "put it in conftest.py to share it across files", because that explanation
  seems to live on another page (the fixtures reference). **Partly fixed.** Rather than guess, we turn this
  question into an eval in Step 5, and add the page only if the answers actually come out wrong.

> **Lessons learned**
> - **Code that runs isn't the same as good results.** Every search "worked", but only checking the content showed the problems.
> - **Retrieval quality is limited by data coverage.** No clever code can find a missing document.
> - **A high distance is a warning sign** that the database may not contain the answer. That's the
>   dangerous case where an LLM might make something up, so it's worth testing in the evals.

> **Tip: running commands from Bash (e.g. Git Bash) instead of PowerShell.** Use forward slashes, and if the
> venv isn't activated in that shell, call its Python directly:
> `.venv/Scripts/python.exe search.py ...`

---

## Step 4: Send the question and the chunks to an LLM

**Goal:** ask a question and get a real answer, written by an LLM **only from the retrieved doc chunks**, with sources.
This is the "G" in RAG: **R**etrieve (Step 3) → **A**ugment the prompt with the chunks → **G**enerate the answer.

**Design choice: keep the LLM provider swappable.** All provider-specific code lives in one small file
(`llm.py`). The rest of the app only calls `generate()`. The provider and model are settings in `.env`,
so switching (for example to Gemini later) means a new branch in `llm.py` and a changed setting, nothing else.
I used **OpenAI** because I already had API credits. A small model costs a fraction of a cent per question.

**1. Install two packages**
```
pip install openai python-dotenv
```
- `openai` is OpenAI's official Python package.
- `python-dotenv` loads settings and secrets from a `.env` file, so they never appear in the code.

Add both to `requirements.txt`.

**2. Create `.env` with your key**

Update `.env.example` (the template, safe to commit, **no real key**):
```
OPENAI_API_KEY=
LLM_PROVIDER=openai
LLM_MODEL=gpt-5.4-mini
```
Copy it to a new file named exactly `.env`, and paste your key (platform.openai.com → API keys) after `OPENAI_API_KEY=`.
No quotes and no spaces. For the model, pick a small, cheap one from OpenAI's pricing page.

> **Keep the name `.env`.** `.gitignore` only ignores that exact name. A file like `cred.env` would be
> committed, key and all. Check with `git check-ignore -v .env`: it should print the matching `.gitignore` line.

**3. Write `llm.py`: the swappable LLM call**

```python
"""One function to call an LLM. The provider and model come from .env, so they're easy to swap."""

import os

from dotenv import load_dotenv

load_dotenv()  # reads the settings in .env into environment variables

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
```
- **`generate(system, prompt)`** is the only function the app calls. `system` holds the instructions (how to behave),
  and `prompt` holds the content (chunks + question).
- **`OpenAI()`** finds the key in the environment by itself, so the code never touches it.
- **`client.responses.create(...)`** sends the request. `response.output_text` is the answer as plain text.
- **The bottom part is a smoke test.** Check that the key, model and connection work *before* building on top:
  ```
  python llm.py
  ```
  **✅ Check:** it prints the provider and model, then a short hello.

**4. Write `answer.py`: the RAG logic**

```python
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
```
- **`SYSTEM_PROMPT`** is the heart of a RAG app:
  - "ONLY the excerpts" keeps answers **grounded** in the docs, not in the model's memory.
  - A **fixed "I don't know" sentence** is easy to check automatically in the evals.
  - **"Sources: [1], [3]"** shows which excerpts the answer came from, so you can verify it.
- **`build_prompt`** numbers each chunk and labels its source, then adds the question.
- **`ask()`** is the whole RAG flow: **search → build the prompt → generate**. It returns the chunks too,
  because the evals and the web page will need them.

Run it:
```
python answer.py How do I skip a test?
```

**5. Check the answers critically.** For each answer, check: **is it correct**, **is it grounded** (can every
claim be found in a retrieved chunk?), and **do the cited sources make sense?** Include an **off-topic question**
to check that it admits it doesn't know.

| Question | Result |
|---|---|
| Skip a test | ✅ `@pytest.mark.skip` with an example, correct sources |
| Same test, different inputs | ✅ `@pytest.mark.parametrize` with a full example |
| Check a function raises | ✅ modern `with pytest.raises(...)`, even though a legacy-style chunk was retrieved too |
| Share a fixture across files | ⚠️ mentions `conftest.py`, but wrongly claims `scope` shares fixtures across files |
| Deploy a Django app (off-topic) | ✅ "I don't know..." (after a prompt fix, see below) |

**Fix: "I don't know" came with fake sources.** The first version answered the off-topic question correctly,
but still added `Sources: [1], [2], [3], [4], [5]`. The cause was **two conflicting rules**: "say I don't know"
and "*always* end with Sources". The fix was to make them agree: "...and nothing else" on the first, and
"*Only when you answered from the excerpts*, end with Sources" on the second.
Then **re-run a question that passed before** (a regression test) to check that normal answers still have sources.

> **Lessons learned**
> - **The system prompt is code.** Vague or conflicting rules make the model guess. Remove conflicts instead of adding emphasis.
> - **Re-test after every prompt change.** A fix for one case can break another.
> - **An answer can sound grounded and still be wrong.** The fixture answer used real doc wording
>   ("Scope: sharing fixtures across... modules"), but the docs meant sharing *one instance*, not making a
>   fixture visible to other files. That's what `conftest.py` does. Checks need to look at **content**, not just format.
> - **LLMs aren't deterministic.** The same question can get differently worded answers, and even a missing `?`
>   can change which chunks are retrieved. So evals must check **key facts** (for example "mentions `pytest.raises`"),
>   never exact text.
> - **Distance tells you a lot.** Real pytest questions matched at 0.7–1.0, while the off-topic question was around 1.5.

> **Check your spending:** the Usage page on platform.openai.com shows what each day's calls cost.

---

## Step 5: Evals (score the app with pytest)

**Goal:** a repeatable test suite that scores whether the app retrieves the right chunks and gives correct,
grounded answers. This is what turns "it seems to work" into a number.

**1. Install pytest** (and add `pytest` to `requirements.txt`)
```
python -m pip install pytest
```

**2. Write the eval cases: `evals/cases.json`.** One entry per question:
```json
{
  "id": "skipif-windows",
  "question": "How do I skip a test only when running on Windows?",
  "expected_page": "skipping.html",
  "must_include": ["skipif", "sys.platform"],
  "must_not_include": []
}
```
- **`must_include`** are **key facts**, not exact text, because LLM wording changes from run to run.
- **`expected_page: null`** means the right answer is the exact "I don't know..." sentence.
- I wrote 20 cases: 17 answerable ones across all 6 pages, plus 3 that must be refused:
  - 2 off-topic (deploying Django, centering a div in CSS)
  - 1 **trap**: a real pytest topic (`monkeypatch`) that's simply **not in our 6 pages**. The app must not
    answer from the model's memory.
- **Check that each key fact really exists in the docs before using it.** A quick script that counts how many
  chunks contain each term saves you from writing a test that can never pass.

**3. Tell pytest where things are: `pytest.ini`**
```ini
[pytest]
testpaths = evals
pythonpath = .
```
`testpaths` makes a plain `pytest` run only the evals. `pythonpath = .` lets the tests `import answer` from the project root.

**4. Write the tests: `evals/test_evals.py`**
```python
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
```
- **`@pytest.mark.parametrize`** turns each case into its own test, and `ids=` names it (`[skipif-windows]`)
  so a failure tells you exactly which question broke.
- **`lru_cache`** remembers each answer, so the retrieval test and the answer test share **one** LLM call per question.
  20 questions = 20 calls, a fraction of a cent.
- **Three kinds of test**, so a failure points at the right part of the app:
  - `test_retrieval_has_key_facts`: did **search** find chunks that contain the facts? (This is called **context recall**.)
  - `test_answer_has_key_facts`: did the **LLM** use them, without refusing or making wrong claims?
  - `test_says_i_dont_know`: does it **refuse** questions the docs can't answer?

**5. Run it**
```
python -m pytest -v
```
`-v` lists every test by name. It takes about a minute: loading the embedding model plus 20 API calls.

**✅ Check it worked:** a summary line like `37 passed`. For any failure, read the printed answer and decide:
**is the app wrong, or is the test wrong?**

**My results**

| Run | Score | What changed |
|---|---|---|
| Baseline | 35/37 | 500-character chunks, retrieval test only checked the page |
| Final | **37/37** | 800-character chunks, retrieval test checks the key facts |

**Debugging the 2 baseline failures.** Both were answer failures, but the real cause was **retrieval**:
- *"Expensive fixture, run once per file"*: the answer was "I don't know". That's **correct behaviour**, because none
  of the top 10 chunks mentioned `scope="module"`. The question's wording ("once for all tests in a file") was too
  far from the docs' wording ("invoked once per test module") for the 500-character chunks to match.
- *"Which files contain tests"*: the only chunk with `test_*.py` ranked **#6**, just outside the top 5.

And the retrieval test **passed both**, because it only checked that *some* chunk came from the right page
(the fixtures page alone had 113 chunks). So I made it stricter: the key facts must appear in the retrieved chunks.

**Fixing retrieval, measured instead of guessed.** Search is local and free, so I tried settings in memory and
counted how many of the 17 cases got their key facts into the retrieved chunks:

| Chunk size | k=5 | k=8 |
|---|---|---|
| 500 | 15/17 | 16/17 |
| **800** | **17/17** | 17/17 |
| 1000 | 16/17 | 17/17 |
| 1500 | 16/17 | 16/17 |

Too small, and a chunk loses the context around a fact. Too big, and it mixes several topics, so its meaning
gets blurry. So I set `CHUNK_SIZE = 800` in `ingest.py` and re-ran the pipeline:
```
python ingest.py          # about 134 chunks now
python build_index.py     # rebuild the database, or search keeps using the old chunks
python -m pytest -v
```

> **Lessons learned**
> - **Split your tests by pipeline stage.** A failed answer can be a retrieval problem. Separate retrieval and answer
>   tests tell you where to look.
> - **A test that's too lenient hides bugs.** "Right page" passed while retrieval was actually failing.
> - **"I don't know" can be the app working correctly.** The prompt did its job; search didn't give it the facts.
> - **Change one thing, then measure.** Every tweak (chunk size, `k`, the prompt) gets checked against the whole suite.
> - **Beware of overfitting.** I tuned the chunk size on the same 17 questions I score with, so 37/37 is a bit
>   optimistic. A real project keeps some questions back as a separate test set.
> - **Keyword checks have limits.** They catch missing facts, but not a wrong explanation that uses the right words
>   (like the Step 4 fixture answer). A next step could be **LLM-as-judge**: a second LLM call that grades each answer.
