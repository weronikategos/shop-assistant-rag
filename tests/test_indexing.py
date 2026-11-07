from assistant import config
from assistant.chunking import MAX_CHARS, load_chunks, split_markdown
from assistant.embeddings import GeminiEmbedder
from tests.fakes import FakeEmbeddingClient


def test_one_chunk_per_section():
    chunks = split_markdown("doc.md", "# Title\n\n## First\nOne.\n\n## Second\nTwo.\n")
    assert [(c.section, c.id) for c in chunks] == [("First", "doc.md#first-0"), ("Second", "doc.md#second-0")]
    assert chunks[0].text == "First\nOne."  # the heading stays with its text


def test_title_section_without_subsections():
    chunks = split_markdown("doc.md", "# Sweets\nWe sell chocolate.\n")
    assert chunks[0].section == "Sweets"


def test_long_section_is_split_by_paragraphs():
    long_text = "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(10))
    chunks = split_markdown("doc.md", f"## Long\n{long_text}")
    assert len(chunks) > 1
    assert all(len(c.text) <= MAX_CHARS + len("Long\n") for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)


def test_help_pages_load_with_unique_ids():
    chunks = load_chunks(config.DOCS_DIR)
    assert len(chunks) >= 20
    assert len({c.id for c in chunks}) == len(chunks)
    assert {c.source for c in chunks} >= {"shipping.md", "returns.md", "accessories.md"}


def test_index_contains_every_chunk(store):
    assert store.count() == len(load_chunks(config.DOCS_DIR))


def test_search_finds_the_right_page(store, embedder):
    hits = store.search(embedder.embed_query("How long does delivery to a parcel locker take?"), k=3)
    assert hits[0][0].source == "shipping.md"
    assert hits[0][1] >= hits[-1][1]  # sorted by similarity


def test_rebuilding_the_index_does_not_duplicate(store, embedder):
    from assistant.ingest import build_index
    before = store.count()
    build_index(store, embedder)
    assert store.count() == before


def test_gemini_embedder_uses_task_prefixes_and_batches():
    client = FakeEmbeddingClient()
    embedder = GeminiEmbedder(client=client)
    chunks = load_chunks(config.DOCS_DIR)
    vectors = embedder.embed_documents(chunks)
    assert len(vectors) == len(chunks)
    assert all(len(call["contents"]) <= 20 for call in client.calls)
    assert client.calls[0]["contents"][0].parts[0].text.startswith("title: ")
    assert client.calls[0]["config"].output_dimensionality == 768
    embedder.embed_query("Do you ship abroad?")
    assert client.calls[-1]["contents"][0].parts[0].text == "task: question answering | query: Do you ship abroad?"
