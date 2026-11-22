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