"""Builds the vector index from the help pages: python -m assistant.ingest"""
from . import config
from .chunking import load_chunks


def build_index(store, embedder, docs_dir=config.DOCS_DIR):
    """Rebuilds the index from scratch and returns the number of chunks."""
    chunks = load_chunks(docs_dir)
    store.reset()
    store.add(chunks, embedder.embed_documents(chunks))
    return len(chunks)


def main():
    from .embeddings import GeminiEmbedder
    from .store import VectorStore

    count = build_index(VectorStore(), GeminiEmbedder())
    print(f"Indexed {count} chunks from {config.DOCS_DIR} into {config.INDEX_DIR}")


if __name__ == "__main__":
    main()
