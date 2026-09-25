"""
Customer support response demo — Retrieval-Augmented Generation (RAG).

Instead of passing the entire policy document to the model on every request,
we embed the complaint and retrieve only the most relevant policy sections.
This keeps prompt size small and focused regardless of how large the policy grows.

Flow for each complaint:
  1. Chunk policy.md into sections at startup and index them in ChromaDB
  2. Embed the complaint text and retrieve the top-3 most relevant chunks
  3. Pass only those chunks — not the full policy — to the response drafter

Usage: python app.py [complaint_id]   (default: runs all complaints)

Env vars:
  AWS_REGION   e.g. us-east-2

Requires:
  pip install chromadb
  (ChromaDB downloads a small embedding model on first run — ~80 MB)
"""

import json
import pathlib
import sys

import chromadb
from openai import OpenAI
from aws_bedrock_token_generator import provide_token

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HERE  = pathlib.Path(__file__).parent
MODEL = "openai.gpt-oss-120b"

# Cosine distance threshold for retrieval. Chunks with a distance above this
# value are dropped. Cosine distance runs from 0 (identical meaning) to 1
# (completely unrelated), so 0.5 keeps only chunks that are at least loosely
# relevant to the query.
RETRIEVAL_THRESHOLD = 0.5

SYSTEM_PROMPT = """\
You are a senior customer support agent. Write a detailed, personalised response to the customer's complaint.

Use only the policy sections provided — do not invent remedies or timeframes that are not in the policy.
Address the customer by name. Be specific about what action is being taken and when.
Write in flowing prose, no bullet points or headers.\
"""

# ---------------------------------------------------------------------------
# OpenAI client — pointed at AWS Bedrock via the compatibility layer
# ---------------------------------------------------------------------------
client = OpenAI(
    api_key=provide_token(),
    base_url="https://bedrock-mantle.us-east-2.api.aws/v1",
    project="default",
)

# ---------------------------------------------------------------------------
# Build the policy index
#
# ChromaDB runs entirely in-memory here (no server, no disk). On first run it
# downloads a small sentence-transformer model (~80 MB) to generate embeddings.
# Subsequent runs use the cached model.
#
# We split policy.md into one chunk per ## section. Each chunk gets a stable ID
# (the section title, lowercased) so re-indexing the same document is idempotent.
# ---------------------------------------------------------------------------
def _build_index(policy_path: pathlib.Path) -> chromadb.Collection:
    chroma   = chromadb.Client()
    collection = chroma.create_collection(
        "policy",
        metadata={"hnsw:space": "cosine"},
    )

    text     = policy_path.read_text()
    chunks   = _chunk_by_section(text)

    collection.add(
        ids       = [c["id"]       for c in chunks],
        documents = [c["text"]     for c in chunks],
        metadatas = [{"section": c["section"]} for c in chunks],
    )

    print(f"  Indexed {len(chunks)} policy sections into ChromaDB")
    return collection


def _chunk_by_section(text: str) -> list[dict]:
    # Split on ## headings so each policy section becomes one retrievable chunk.
    # A chunk is the heading text plus all the lines that follow it, up to the
    # next heading.
    chunks: list[dict] = []
    section: str | None = None
    lines:   list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if section and lines:
                chunks.append({
                    "id":      section.lower().replace(" ", "_"),
                    "section": section,
                    "text":    f"{section}\n" + "\n".join(lines).strip(),
                })
            section = line[3:].strip()
            lines   = []
        elif section is not None:
            lines.append(line)

    if section and lines:
        chunks.append({
            "id":      section.lower().replace(" ", "_"),
            "section": section,
            "text":    f"{section}\n" + "\n".join(lines).strip(),
        })

    return chunks


# ---------------------------------------------------------------------------
# Retrieval
#
# ChromaDB embeds the query with the same model used at index time and returns
# the n most similar chunks ranked by cosine distance (configured above).
# ---------------------------------------------------------------------------
def _retrieve(collection: chromadb.Collection, query: str, n: int = 3) -> list[str]:
    results   = collection.query(query_texts=[query], n_results=n)
    chunks    = results["documents"][0]
    distances = results["distances"][0]
    return [c for c, d in zip(chunks, distances) if d <= RETRIEVAL_THRESHOLD]


# ---------------------------------------------------------------------------
# Triage — retrieve relevant policy sections, then draft a response
# ---------------------------------------------------------------------------
def triage(complaint: dict, collection: chromadb.Collection) -> None:
    cid      = complaint["id"]
    customer = complaint["customer"]
    message  = complaint["message"]

    print(f"\n{'='*60}")
    print(f"Complaint {cid} — {customer}")
    print(f"  \"{message}\"")

    # Step 1: retrieve the policy sections most relevant to this complaint.
    # The complaint text is the query — ChromaDB embeds it and finds the
    # closest policy chunks by meaning, not keyword matching.
    relevant_chunks = _retrieve(collection, message)
    print(f"\n  Retrieved sections: {[c.split(chr(10))[0] for c in relevant_chunks]}")

    # Step 2: build a prompt with only the retrieved policy sections.
    # The model never sees the full policy — only what's relevant.
    policy_context = "\n\n---\n\n".join(relevant_chunks)
    user_message   = (
        f"Customer name: {customer}\n"
        f"Complaint: {message}\n\n"
        f"Relevant policy sections:\n{policy_context}"
    )

    # Step 3: draft the response using the retrieved context.
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_message},
    ]

    response = client.chat.completions.create(model=MODEL, messages=messages)
    draft    = response.choices[0].message.content or ""

    print(f"\n  Draft response:\n\n  {draft.replace(chr(10), chr(10) + '  ')}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
collection = _build_index(HERE / "policy.md")

complaints = json.loads((HERE / "complaints.json").read_text())

if len(sys.argv) > 1:
    target_id = sys.argv[1].upper()
    complaints = [c for c in complaints if c["id"] == target_id]
    if not complaints:
        print(f"Complaint {target_id} not found.")
        sys.exit(1)

for complaint in complaints:
    triage(complaint, collection)
