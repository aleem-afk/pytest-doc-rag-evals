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
    "https://docs.pytest.org/en/stable/how-to/skipping.html",
]

CHUNK_SIZE = 800  # target size of each chunk, in characters (500 split answers from their context; see evals)
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
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]  # remove whitespace
    return [line for line in lines if line]  # drop empty lines


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
