"""
Customer support response demo — RAG with OpenTelemetry.

The trace structure for each complaint looks like this:

  triage {complaint_id}                   ← root span, covers the full complaint
    retrieval                             ← ChromaDB similarity search
    chat {MODEL}                          ← LLM call with retrieved context only

The retrieval span is the new element vs earlier examples. It carries:
  - gen_ai.operation.name = "retrieval"  (OTel GenAI semconv operation type)
  - retrieval.query                       the complaint text used as the search query
  - retrieval.n_results                   how many chunks were requested
  - retrieval.matched_sections            which policy sections were returned

This makes it possible to answer "what context did the model actually see?"
directly from the trace, without re-running the query.

Usage: python app-instrumented.py [complaint_id]   (default: runs all)

Env vars:
  AWS_REGION                    e.g. us-east-2
  OTEL_EXPORTER_OTLP_ENDPOINT   e.g. http://localhost:4318

Requires:
  pip install chromadb
"""

import json
import pathlib
import sys

import chromadb
from openai import OpenAI
from aws_bedrock_token_generator import provide_token

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

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
# OTel setup
# ---------------------------------------------------------------------------
resource = Resource.create({"service.name": "support-rag"})

_trace_provider = TracerProvider(resource=resource)
_trace_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(_trace_provider)

_meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
)
metrics.set_meter_provider(_meter_provider)

tracer = trace.get_tracer("support-rag", "1.0.0")
meter  = metrics.get_meter("support-rag", "1.0.0")

token_usage = meter.create_histogram(
    name="gen_ai.client.token.usage",
    unit="{token}",
    description="Number of tokens used in a GenAI request",
)

# Tracks how many policy chunks were retrieved per complaint.
# Low values mean the retrieval is focused; high values suggest the query
# is too broad or the policy chunks are not semantically distinct enough.
retrieval_results = meter.create_histogram(
    name="rag.retrieval.chunk_count",
    unit="{chunk}",
    description="Number of policy chunks retrieved per complaint",
)

# ---------------------------------------------------------------------------
# OpenAI client
# ---------------------------------------------------------------------------
client = OpenAI(
    api_key=provide_token(),
    base_url="https://bedrock-mantle.us-east-2.api.aws/v1",
    project="default",
)

# ---------------------------------------------------------------------------
# Build the policy index
# ---------------------------------------------------------------------------
def _build_index(policy_path: pathlib.Path) -> chromadb.Collection:
    with tracer.start_as_current_span("index policy") as span:
        span.set_attribute("gen_ai.operation.name", "index")
        span.set_attribute("db.system.name",        "chroma")
        span.set_attribute("db.operation.name",     "upsert")
        span.set_attribute("db.collection.name",    "policy")
        span.set_attribute("policy.file", policy_path.name)

        chroma     = chromadb.Client()
        collection = chroma.create_collection(
            "policy",
            metadata={"hnsw:space": "cosine"},
        )
        text       = policy_path.read_text()
        chunks     = _chunk_by_section(text)

        collection.add(
            ids       = [c["id"]       for c in chunks],
            documents = [c["text"]     for c in chunks],
            metadatas = [{"section": c["section"]} for c in chunks],
        )

        span.set_attribute("policy.section_count", len(chunks))
        print(f"  Indexed {len(chunks)} policy sections")
        return collection


def _chunk_by_section(text: str) -> list[dict]:
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
# Retrieval — with its own span
# ---------------------------------------------------------------------------
def _retrieve(collection: chromadb.Collection, query: str, n: int = 3) -> list[str]:
    # gen_ai.operation.name="retrieval" is the OTel GenAI semconv value for
    # vector search operations. The span duration covers the embedding of the
    # query and the similarity search — useful for spotting ChromaDB latency
    # separately from LLM latency in the trace waterfall.
    with tracer.start_as_current_span("retrieval") as span:
        span.set_attribute("gen_ai.operation.name", "retrieval")
        span.set_attribute("db.system.name",        "chroma")
        span.set_attribute("db.operation.name",     "query")
        span.set_attribute("db.collection.name",    "policy")
        span.set_attribute("retrieval.query",        query)
        span.set_attribute("retrieval.n_results",    n)

        results    = collection.query(query_texts=[query], n_results=n)
        chunks     = results["documents"][0]
        metas      = results["metadatas"][0]
        distances  = results["distances"][0]

        # Drop chunks that are too dissimilar to the query.
        chunks = [c for c, d in zip(chunks, distances) if d <= RETRIEVAL_THRESHOLD]
        metas  = [m for m, d in zip(metas,  distances) if d <= RETRIEVAL_THRESHOLD]

        matched = [m["section"] for m in metas]
        span.set_attribute("retrieval.matched_sections", json.dumps(matched))
        span.set_attribute("retrieval.chunk_count",      len(chunks))
        span.set_attribute("retrieval.threshold",        RETRIEVAL_THRESHOLD)

        retrieval_results.record(len(chunks), {
            "gen_ai.operation.name": "retrieval",
        })

    return chunks


# ---------------------------------------------------------------------------
# Triage — retrieve, then generate
# ---------------------------------------------------------------------------
def triage(complaint: dict, collection: chromadb.Collection) -> None:
    cid      = complaint["id"]
    customer = complaint["customer"]
    message  = complaint["message"]

    print(f"\n{'='*60}")
    print(f"Complaint {cid} — {customer}")
    print(f"  \"{message}\"")

    # The root span covers the full complaint lifecycle — retrieval + generation.
    # This lets you see total latency and both child operations in one trace.
    with tracer.start_as_current_span(f"triage {cid}") as root:
        root.set_attribute("complaint.id",       cid)
        root.set_attribute("complaint.customer", customer)

        # --- Step 1: retrieve relevant policy sections ---
        # The retrieval span is a child of the triage root span.
        relevant_chunks = _retrieve(collection, message)
        print(f"\n  Retrieved: {[c.split(chr(10))[0] for c in relevant_chunks]}")

        # Record which sections were retrieved on the root span too, so you
        # can filter complaints by the policy sections they triggered without
        # having to drill into child spans.
        root.set_attribute("retrieval.matched_sections",
                           json.dumps([c.split("\n")[0] for c in relevant_chunks]))

        # --- Step 2: generate a response using retrieved context only ---
        policy_context = "\n\n---\n\n".join(relevant_chunks)
        user_message   = (
            f"Customer name: {customer}\n"
            f"Complaint: {message}\n\n"
            f"Relevant policy sections:\n{policy_context}"
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ]

        # The chat span is a sibling of the retrieval span under the triage root.
        # Its duration covers only the LLM call — not the retrieval — so you can
        # compare retrieval latency vs generation latency in the waterfall.
        with tracer.start_as_current_span(f"chat {MODEL}") as span:
            span.set_attribute("gen_ai.provider.name",  "aws.bedrock")
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.request.model",  MODEL)
            span.set_attribute("gen_ai.input.messages",
                               json.dumps([{"role": "user", "content": user_message}]))

            response = client.chat.completions.create(model=MODEL, messages=messages)
            draft    = response.choices[0].message.content or ""

            span.set_attribute("gen_ai.response.model",          response.model)
            span.set_attribute("gen_ai.response.finish_reasons",
                               [c.finish_reason for c in response.choices])
            span.set_attribute("gen_ai.output.messages",
                               json.dumps([{
                                   "role":         "assistant",
                                   "content":      draft,
                                   "finish_reason": response.choices[0].finish_reason,
                               }]))

            if response.usage:
                span.set_attribute("gen_ai.usage.input_tokens",  response.usage.prompt_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", response.usage.completion_tokens)
                attrs = {
                    "gen_ai.provider.name":  "aws.bedrock",
                    "gen_ai.operation.name": "chat",
                    "gen_ai.request.model":  MODEL,
                    "gen_ai.response.model": response.model,
                }
                token_usage.record(response.usage.prompt_tokens,
                                   {**attrs, "gen_ai.token.type": "input"})
                token_usage.record(response.usage.completion_tokens,
                                   {**attrs, "gen_ai.token.type": "output"})

        root.set_attribute("triage.outcome", "responded")
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

_trace_provider.shutdown()
_meter_provider.shutdown()
