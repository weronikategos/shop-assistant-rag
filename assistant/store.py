"""The vector database: chunks and their embeddings stored in Chroma, searched by cosine similarity."""
import chromadb

from . import config
from .chunking import Chunk


class VectorStore:
    def __init__(self, path=config.INDEX_DIR, collection=config.COLLECTION):
        self.client = chromadb.PersistentClient(path=str(path))
        self.name = collection
        self.collection = self._open()

    def _open(self):
        # we pass our own embeddings, so Chroma's built-in embedding function is switched off
        return self.client.get_or_create_collection(self.name, metadata={"hnsw:space": "cosine"},
                                                    embedding_function=None)

    def reset(self):
        self.client.delete_collection(self.name)
        self.collection = self._open()

    def add(self, chunks, vectors):
        self.collection.add(
            ids=[c.id for c in chunks],
            embeddings=vectors,
            documents=[c.text for c in chunks],
            metadatas=[{"source": c.source, "section": c.section} for c in chunks],
        )

    def count(self):
        return self.collection.count()

    def search(self, vector, k=config.TOP_K):
        """Returns [(chunk, similarity)] with the most similar chunk first."""
        if self.count() == 0:
            return []
        result = self.collection.query(query_embeddings=[vector], n_results=min(k, self.count()))
        hits = []
        for chunk_id, text, meta, distance in zip(result["ids"][0], result["documents"][0],
                                                  result["metadatas"][0], result["distances"][0]):
            chunk = Chunk(id=chunk_id, source=meta["source"], section=meta["section"], text=text)
            hits.append((chunk, round(1 - distance, 4)))  # cosine distance -> similarity
        return hits
