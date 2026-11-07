"""Test doubles: they behave like the Gemini clients without any network or API key."""
import hashlib
import math
import re
from types import SimpleNamespace

DIM = 1024


def bag_of_words_vector(text):
    """A crude but deterministic embedding: hashed word counts, normalised to length 1."""
    vector = [0.0] * DIM
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if len(word) > 2:
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class FakeEmbedder:
    def embed_documents(self, chunks):
        return [bag_of_words_vector(c.text) for c in chunks]

    def embed_query(self, question):
        return bag_of_words_vector(question)


class FakeEmbeddingClient:
    """Stands in for client.models.embed_content and records the calls."""

    def __init__(self):
        self.calls = []
        self.models = SimpleNamespace(embed_content=self.embed_content)

    def embed_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        texts = [c.parts[0].text for c in contents]
        return SimpleNamespace(embeddings=[SimpleNamespace(values=bag_of_words_vector(t)) for t in texts])
