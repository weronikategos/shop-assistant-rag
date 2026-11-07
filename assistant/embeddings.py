"""Turns text into vectors with the Gemini embedding model."""
from google import genai
from google.genai import types

from . import config

BATCH_SIZE = 20


class GeminiEmbedder:
    """gemini-embedding-2 has no task_type option; the task goes into the text as a prefix instead."""

    def __init__(self, client=None, model=config.EMBEDDING_MODEL, dim=config.EMBEDDING_DIM):
        self.client = client or genai.Client()  # reads the API key from GEMINI_API_KEY
        self.model = model
        self.dim = dim

    def _embed(self, texts):
        vectors = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = texts[start:start + BATCH_SIZE]
            # one Content per text, so each text gets its own embedding
            response = self.client.models.embed_content(
                model=self.model,
                contents=[types.Content(parts=[types.Part(text=t)]) for t in batch],
                config=types.EmbedContentConfig(output_dimensionality=self.dim),
            )
            vectors.extend(list(e.values) for e in response.embeddings)
        return vectors

    def embed_documents(self, chunks):
        return self._embed([f"title: {c.section} | text: {c.text}" for c in chunks])

    def embed_query(self, question):
        return self._embed([f"task: question answering | query: {question}"])[0]
