"""Splits the Markdown help pages into chunks small enough to retrieve precisely."""
import re
from dataclasses import dataclass
from pathlib import Path

MAX_CHARS = 900  # long sections are split by paragraphs to stay under this size


@dataclass
class Chunk:
    id: str
    source: str  # file name, e.g. shipping.md
    section: str  # heading the text belongs to
    text: str


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def split_markdown(source, markdown):
    """One chunk per "##" section (or "#" section without subsections); long sections become several chunks."""
    chunks, title, section, lines = [], "", "", []

    def flush():
        body = "\n".join(lines).strip()
        if not body:
            return
        heading = section or title
        for n, part in enumerate(_split_long(body)):
            chunks.append(Chunk(id=f"{source}#{_slug(heading)}-{n}", source=source, section=heading,
                                text=f"{heading}\n{part}"))

    for line in markdown.splitlines():
        if line.startswith("## "):
            flush()
            section, lines = line[3:].strip(), []
        elif line.startswith("# "):
            flush()
            title, section, lines = line[2:].strip(), "", []
        else:
            lines.append(line)
    flush()
    return chunks


def _split_long(body):
    if len(body) <= MAX_CHARS:
        return [body]
    parts, current = [], ""
    for paragraph in body.split("\n\n"):
        if current and len(current) + len(paragraph) > MAX_CHARS:
            parts.append(current.strip())
            current = ""
        current += paragraph + "\n\n"
    if current.strip():
        parts.append(current.strip())
    return parts


def load_chunks(docs_dir):
    chunks = []
    for path in sorted(Path(docs_dir).glob("*.md")):
        chunks.extend(split_markdown(path.name, path.read_text(encoding="utf-8")))
    return chunks
