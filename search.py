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
