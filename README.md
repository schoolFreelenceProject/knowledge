# Company Knowledge Base

Company Knowledge Base သည် company documents နှင့် code sources ကို ingest,
index, retrieve, inspect, and expose through REST/MCP APIs အဖြစ်ထားသည့်
retrieval-first service ဖြစ်သည်။ Codex, Claude Code, သို့မဟုတ် အခြား MCP
clients များသည် reasoning/generation agents အဖြစ် Knowledge Base ကို context
service အနေနဲ့အသုံးပြုနိုင်သည်။

## Current Scope

Current platform သည် Company Knowledge Base RAG foundation ကို production
deployment အတွက် hardening လုပ်ထားသည်။

- FastAPI backend
- Qdrant vector database
- PostgreSQL metadata database
- sentence-transformers local embeddings
- Docker Compose based local runtime
- PDF, Markdown, DOCX, XLSX, and PPTX document ingestion
- Git repository Code RAG ingestion
- local document/code folder ingestion
- JWT authentication
- Admin Control Panel user creation, listing, and activation
- user-document and user-repository ACL
- Vector, BM25, Hybrid Search, and optional Reranker
- Knowledge Explorer with source inspection
- Trace, Feedback, Evaluation, and Analytics Dashboard
- read-only MCP server for vendor-neutral Codex / Claude Code integration
- optional Ollama internal answer generation provider
- Alembic migrations, backup/restore scripts, health checks, and benchmarks

Current scope တွင် အောက်ပါတို့ကို မထည့်သေးပါ။

- Agent System
- Database RAG
- Multimodal RAG
- Multi-tenant isolation

## Architecture

RAG system ၏အဓိက data flow သည် အောက်ပါအတိုင်းဖြစ်သည်။

```text
Company Documents
  -> Document Loader / Parser
  -> Text Chunker
  -> Embedding Model
  -> Qdrant Vector Store
  -> PostgreSQL Metadata Store
  -> Retriever / Knowledge Explorer / MCP Search Tools
```

### Component Responsibilities

- **FastAPI**: HTTP API entrypoint ဖြစ်ပြီး ingestion, retrieval, ACL, metadata, source inspection endpoints ကို expose လုပ်မည်။
- **Document Loader / Parser**: PDF, Markdown, DOCX, XLSX, and PPTX မှ text ထုတ်ယူမည်။
- **Text Chunker**: ရှည်လျားသော document text ကို retrieval အတွက်သင့်တော်သော chunk များအဖြစ်ခွဲမည်။
- **Embedding Model**: sentence-transformers ဖြင့် chunk တစ်ခုချင်းစီကို vector embedding အဖြစ်ပြောင်းမည်။
- **Qdrant**: embeddings နှင့် metadata များကိုသိမ်းပြီး semantic search ပြန်ပေးမည်။
- **PostgreSQL**: uploaded documents နှင့် generated chunks metadata များကိုသိမ်းမည်။
- **Retriever**: user query အတွက်သက်ဆိုင်ရာ chunks များကို vector, BM25, hybrid, reranker stack ဖြင့်ရှာမည်။
- **MCP Server**: Codex, Claude Code, and other MCP clients အတွက် vendor-neutral read-only retrieval tools ကို expose လုပ်မည်။
- **Ollama**: optional internal answer generation provider ဖြစ်ပြီး default runtime အတွက်မလိုအပ်ပါ။

## Folder Structure

```text
company-document-rag/
  app/
    main.py
    api/
    core/
      config.py
    db/
      models.py
      session.py
    services/
      document_loader.py
      text_chunker.py
      embedding_service.py
      vector_store.py
      ingestion_service.py
      metadata_service.py
      retrieval_service.py
      generation_service.py
      knowledge_tool_service.py
    mcp/
      server.py
      auth.py
    schemas/
      documents.py
      mcp.py
  data/
    documents/
  scripts/
    inspect_documents.py
    inspect_chunks.py
    inspect_embeddings.py
    store_vectors.py
    inspect_vector_store.py
    query_vectors.py
    answer_question.py
  tests/
  docker-compose.yml
  requirements.txt
  README.md
```

### Folder Responsibilities

- `app/`: FastAPI application source code အားလုံးထားမည့် root package။
- `app/main.py`: FastAPI app ကို initialize လုပ်မည့် entrypoint။
- `app/api/`: HTTP API route modules များထားမည့်နေရာ။
- `app/core/`: app settings, environment variables, shared configuration များထားမည့်နေရာ။
- `app/core/config.py`: chunk size နှင့် overlap ကဲ့သို့ configurable settings များထားမည့်နေရာ။
- `app/db/`: SQLAlchemy models နှင့် PostgreSQL connection/session setup များထားမည့်နေရာ။
- `app/services/`: document loading, chunking, embedding, vector store, retrieval, generation စသည့် RAG business logic များထားမည့်နေရာ။
- `app/services/document_loader.py`: `data/documents/` ထဲမှ PDF, Markdown, DOCX, XLSX, and PPTX files များကိုရှာပြီး text extraction လုပ်မည့် service။
- `app/services/text_chunker.py`: extracted text ကို configurable size/overlap ဖြင့် chunks ခွဲမည့် service။
- `app/services/embedding_service.py`: chunks များကို sentence-transformers local model ဖြင့် dense vectors အဖြစ်ပြောင်းမည့် service။
- `app/services/vector_store.py`: embedded chunks များကို Qdrant collection ထဲသို့သိမ်းရန်နှင့် collection status စစ်ရန် service။
- `app/services/ingestion_service.py`: uploaded document ကို save, parse, chunk, embed, vector store, metadata store flow အဖြစ် run မည့် service။
- `app/services/metadata_service.py`: document နှင့် chunk metadata ကို PostgreSQL ထဲသိမ်းမည့် service။
- `app/services/retrieval_service.py`: user query ကို embedding ပြောင်းပြီး Qdrant မှ relevant chunks များရှာမည့် retrieval service။
- `app/services/generation_service.py`: optional internal answer generation provider integration များထားမည့် service။
- `app/services/knowledge_tool_service.py`: MCP read-only tools အတွက် existing services များကို orchestration လုပ်မည့် service။
- `app/mcp/`: Codex က Streamable HTTP ဖြင့်ချိတ်မည့် MCP server process နှင့် service-account auth code များထားမည့်နေရာ။
- `app/schemas/`: API request/response Pydantic models များထားမည့်နေရာ။
- `app/schemas/documents.py`: extracted text, chunk text, embedded chunk, retrieval result, generated answer နှင့် metadata models များထားမည့်နေရာ။
- `app/schemas/mcp.py`: MCP tool response schemas များထားမည့်နေရာ။
- `data/documents/`: MVP တွင် ingest လုပ်မည့် company documents များကို local ထားမည့်နေရာ။
- `scripts/`: one-off helper scripts များထားမည့်နေရာ။ ဥပမာ document ingestion script။
- `scripts/inspect_documents.py`: extracted document text နှင့် metadata ကို CLI မှကြည့်ရန် script။
- `scripts/inspect_chunks.py`: generated chunks နှင့် preserved metadata ကို CLI မှကြည့်ရန် script။
- `scripts/inspect_embeddings.py`: generated vectors, original text နှင့် preserved metadata ကို CLI မှကြည့်ရန် script။
- `scripts/store_vectors.py`: generated embeddings များကို Qdrant collection ထဲသို့ upsert လုပ်ရန် script။
- `scripts/inspect_vector_store.py`: Qdrant collection status နှင့် stored payload samples ကို CLI မှကြည့်ရန် script။
- `scripts/query_vectors.py`: user query ဖြင့် Qdrant similarity search စမ်းရန် script။
- `scripts/answer_question.py`: optional Ollama provider ဖြင့် simple generated answer စမ်းရန် script။
- `tests/`: unit tests နှင့် API tests များထားမည့်နေရာ။

## Document Ingestion Pipeline

အခုအဆင့်တွင် pipeline သည် loading, parsing, chunking, embedding generation,
Qdrant vector storage, PostgreSQL metadata storage, retrieval, ACL filtering,
and source inspection ကိုလုပ်သည်။ Agent logic နှင့် Memory ကို Knowledge Base
ထဲတွင်မထည့်ထားပါ။

```text
data/documents/
  -> discover PDF, Markdown, DOCX, XLSX, and PPTX files
  -> parse file text
  -> attach metadata
  -> return extracted document blocks
  -> split into chunks
  -> generate local embeddings
  -> store vectors and payloads in Qdrant
  -> store document and chunk metadata in PostgreSQL
  -> embed user query
  -> search similar vectors in Qdrant
  -> return retrieved sources through REST / Knowledge Explorer / MCP
  -> inspect extracted documents, chunks, embeddings, vector store, or retrieval results with CLI
```

### Metadata

Extracted block တစ်ခုချင်းစီတွင် အောက်ပါ metadata ပါသည်။

- `filename`: original file name
- `source_path`: `data/documents/` အောက်ရှိ relative path
- `file_type`: `pdf`, `markdown`, `docx`, `xlsx`, or `pptx`
- `page_number`: PDF အတွက် one-based page number, non-PDF အတွက် `null`
- DOCX fields: `section_heading`, `heading_path`, `block_kind`
- XLSX fields: `workbook`, `sheet_name`, `cell_range`, `row_start`, `row_end`
- PPTX fields: `slide_number`, `slide_title`

Chunk တစ်ခုချင်းစီတွင် original metadata မပျောက်အောင်သိမ်းထားပြီး အောက်ပါ fields များထပ်ပါသည်။

- `chunk_index`: source block တစ်ခုအတွင်း one-based chunk number
- `start_char`: extracted text ထဲရှိ chunk start offset
- `end_char`: extracted text ထဲရှိ chunk exclusive end offset

Embedded chunk တစ်ခုချင်းစီတွင် အောက်ပါ output ပါသည်။

- `vector`: sentence-transformers မှထုတ်ထားသော dense vector
- `text`: original chunk text
- `metadata`: original chunk metadata

Qdrant payload တစ်ခုချင်းစီတွင် အောက်ပါ fields များပါသည်။

- `text`: original chunk text
- `filename`: original file name
- `source_path`: `data/documents/` အောက်ရှိ relative path
- `file_type`: `pdf`, `markdown`, `docx`, `xlsx`, or `pptx`
- `page_number`: PDF page number or `null`
- `chunk_index`: source block အတွင်း chunk number
- `start_char`: extracted text ထဲရှိ chunk start offset
- `end_char`: extracted text ထဲရှိ chunk exclusive end offset

Retrieval result တစ်ခုချင်းစီတွင် အောက်ပါ fields များပါသည်။

- `text`: retrieved chunk text
- `filename`: original file name
- `page_number`: PDF page number or `null`
- `score`: Qdrant similarity score
- `metadata`: chunk metadata အပြည့်အစုံ

Optional generated answer response တွင် အောက်ပါ fields များပါသည်။ ဒီ endpoint
သည် `INTERNAL_GENERATION_ENABLED=true` နှင့် provider dependency များရှိမှ
အသုံးပြုနိုင်သည်။

- `answer`: configured internal generation provider မှ generate လုပ်ထားသော answer
- `sources`: answer အတွက်သုံးခဲ့သော retrieved chunks source list
- `sources[].filename`: source file name
- `sources[].page_number`: PDF page number or `null`
- `sources[].score`: retrieval similarity score

## Local Setup

Default Docker stack သည် PostgreSQL, Qdrant, API, MCP, and frontend ကိုတင်သည်။
Ollama မလိုအပ်ပါ။ First run အတွက် local secrets, admin login, and MCP service
token ကို `./start.sh` က generate/bootstrap လုပ်ပေးသည်။

```bash
cd company-document-rag
./start.sh
```

Manual Compose path ကိုသုံးချင်ရင် `.env` ကို `./start.sh` ဖြင့်တစ်ခါ
bootstrap လုပ်ပြီးနောက် အောက်ပါ command ဖြင့် restart လုပ်နိုင်သည်။

```bash
docker compose up -d --build
```

Normal restart သည် persistent volumes ကိုမဖျက်ပါ။

```bash
docker compose down
docker compose up -d
```

Clean reset သည် explicit destructive command သီးသန့်ဖြစ်သည်။

```bash
./reset.sh --yes-delete-all-data
```

Optional internal answer generation လိုအပ်မှသာ Ollama profile ကိုသုံးပါ။
Python client ကို install လုပ်ရန် image ကို `INSTALL_OLLAMA_CLIENT=true` ဖြင့်
rebuild လုပ်ပြီး `INTERNAL_GENERATION_ENABLED=true` ထားရမည်။

```bash
INSTALL_OLLAMA_CLIENT=true INTERNAL_GENERATION_ENABLED=true \
  docker compose --profile ollama up -d --build
```

Ollama container တက်ပြီးနောက် model ကို pull လုပ်ရန်:

```bash
docker compose exec ollama ollama pull llama3.1:8b
```

API health check:

```bash
curl http://localhost:8000/health/ready
```

Admin UI ကို browser မှဖွင့်ရန်:

```text
http://localhost:5173
```

Release deployment details, MCP setup, backup/restore, update procedure, and
verification checklist ကို [docs/release.md](docs/release.md) တွင်ကြည့်ပါ။

Document upload ingestion endpoint:

```bash
curl -F "file=@data/documents/company_policy.md" \
  -H "Authorization: Bearer <access_token>" \
  http://localhost:8000/api/ingest
```

### Docker Dependency Notes

- `api` service သည် local `Dockerfile` မှ build လုပ်သည်။
- `requirements.txt` သည် CPU-only PyTorch wheel index ကိုသုံးပြီး
  `torch==2.7.1+cpu` ကို pin လုပ်ထားသည်။
- CUDA-related PyTorch packages မဆွဲရန် `torch` ကို CPU-only version အဖြစ်
  explicit ထည့်ထားသည်။
- `requirements.txt` ပြောင်းပြီးနောက် `docker compose build api` ကိုပြန် run ရမည်။

## Inspect Extracted Documents

PDF, Markdown, DOCX, XLSX, or PPTX files များကို `data/documents/` ထဲသို့ထည့်ပြီး အောက်ပါ command ဖြင့် extracted result ကိုကြည့်နိုင်သည်။

```bash
python scripts/inspect_documents.py
```

Preview length ကိုပြောင်းချင်လျှင်:

```bash
python scripts/inspect_documents.py --max-chars 1200
```

JSON output လိုချင်လျှင်:

```bash
python scripts/inspect_documents.py --format json
```

## Inspect Chunks

Extracted documents ကို chunks ခွဲထားတဲ့ result ကိုကြည့်ရန်:

```bash
python scripts/inspect_chunks.py
```

Chunk size နှင့် overlap ကို command line မှ override လုပ်နိုင်သည်။

```bash
python scripts/inspect_chunks.py --chunk-size 800 --chunk-overlap 120
```

JSON output လိုချင်လျှင်:

```bash
python scripts/inspect_chunks.py --format json
```

## Inspect Embeddings

Chunks များကို local sentence-transformers model ဖြင့် vector ပြောင်းထားတဲ့ result ကိုကြည့်ရန်:

```bash
python scripts/inspect_embeddings.py
```

Chunk setting နှင့် embedding model ကို command line မှ override လုပ်နိုင်သည်။

```bash
python scripts/inspect_embeddings.py --chunk-size 800 --chunk-overlap 120 --model-name sentence-transformers/all-MiniLM-L6-v2
```

JSON output လိုချင်လျှင်:

```bash
python scripts/inspect_embeddings.py --format json
```

## Store Vectors in Qdrant

Qdrant ကိုအရင်တင်ရန်:

```bash
docker compose up qdrant
```

Documents များကို load, chunk, embed လုပ်ပြီး Qdrant ထဲသိမ်းရန်:

```bash
python scripts/store_vectors.py
```

Qdrant URL, collection name, chunk settings, embedding model ကို command line မှ override လုပ်နိုင်သည်။

```bash
python scripts/store_vectors.py --qdrant-url http://localhost:6333 --collection-name company_documents
```

Collection မရှိသေးလျှင် first embedding vector dimension နှင့် `Cosine` distance ဖြင့် create လုပ်မည်။ Collection ရှိပြီး vector dimension မကိုက်လျှင် error ပြပြီး overwrite မလုပ်ပါ။

## Inspect Vector Store

Qdrant collection status နှင့် payload samples ကိုကြည့်ရန်:

```bash
python scripts/inspect_vector_store.py
```

JSON output လိုချင်လျှင်:

```bash
python scripts/inspect_vector_store.py --format json
```

## Test Retrieval

Qdrant ထဲသို့ vectors သိမ်းပြီးနောက် user query ဖြင့် relevant chunks ရှာရန်:

```bash
python scripts/query_vectors.py "leave request policy"
```

Top K, model, Qdrant URL, collection name ကို command line မှ override လုပ်နိုင်သည်။

```bash
python scripts/query_vectors.py "security document rules" --top-k 3 --collection-name company_documents
```

JSON output လိုချင်လျှင်:

```bash
python scripts/query_vectors.py "leave request policy" --format json
```

BM25 သို့မဟုတ် Hybrid Search ကိုစမ်းရန်:

```bash
python scripts/query_vectors.py "leave request policy" --retrieval-mode bm25

python scripts/query_vectors.py "leave request policy" \
  --retrieval-mode hybrid \
  --fusion-strategy rrf

python scripts/query_vectors.py "leave request policy" \
  --retrieval-mode hybrid \
  --fusion-strategy rrf \
  --reranker-enabled
```

Hybrid Search သည် Vector Search နှင့် BM25 keyword retrieval ကိုပေါင်းပြီး
default `rrf` fusion strategy ဖြင့် top K results ပြန်ပေးသည်။ Production
default သည် `RETRIEVAL_MODE=hybrid` ဖြစ်ပြီး Japanese exact/lexical queries
အတွက် BM25 fallback ကို vector retrieval နှင့်အတူသုံးသည်။ BM25 index သည်
ဤ milestone တွင် in-memory lazy rebuild ဖြစ်သည်။ Running process အတွင်း
documents အသစ် ingest/reindex လုပ်ပြီးနောက် BM25 corpus refresh လိုပါက API
process ကို restart လုပ်ပါ။ Reranker သည် default disabled ဖြစ်ပြီး
`RERANKER_ENABLED=true` သို့မဟုတ် `--reranker-enabled` ဖြင့် enable လုပ်နိုင်သည်။
Reranking သည် retrieval candidates များကို post-process လုပ်ပြီး permission,
auth, user logic မပါဝင်ပါ။

## Optional Generate Answer

Qdrant ထဲသို့ vectors သိမ်းပြီး optional Ollama provider ကို install/configure
လုပ်ထားပြီးမှ simple generated answer ထုတ်ရန်:

```bash
python scripts/answer_question.py "How do employees request leave?"
```

Top K, embedding model, Qdrant config, and optional Ollama config ကို command
line မှ override လုပ်နိုင်သည်။

```bash
python scripts/answer_question.py "What are the document security rules?" --top-k 3 --ollama-model llama3.1:8b
```

JSON output လိုချင်လျှင်:

```bash
python scripts/answer_question.py "How do employees request leave?" --format json
```

Hybrid retrieval ဖြင့် answer generation စမ်းရန်:

```bash
python scripts/answer_question.py "How do employees request leave?" \
  --retrieval-mode hybrid \
  --fusion-strategy rrf \
  --reranker-enabled
```

## Evaluate RAG Quality

Evaluation သည် production API မှသီးသန့်ဖြစ်သည်။ `/api/chat` ကိုမခေါ်ဘဲ
existing `RetrievalService` နှင့် optional `RAGGenerationService` ကို reuse လုပ်သည်။
Hybrid Search, Reranker, Code RAG မထည့်ခင် retrieval quality နှင့် answer
quality baseline ကိုတိုင်းရန်သုံးနိုင်သည်။

Dataset example:

```json
{
  "version": 1,
  "name": "Company policy baseline",
  "metadata": {
    "description": "Initial RAG evaluation set"
  },
  "cases": [
    {
      "id": "company-remote-work-001",
      "question": "How many days per week may employees work remotely?",
      "expected_sources": [
        {
          "filename": "company_policy.md",
          "source_path": "company_policy.md",
          "page_number": null
        }
      ],
      "expected_answer_contains": ["three days per week", "manager"],
      "top_k": 5,
      "metadata": {
        "category": "company_policy"
      }
    }
  ]
}
```

Evaluation runner:

```bash
python scripts/evaluate_rag.py \
  --dataset data/evaluation/rag_eval.json \
  --output reports/rag_eval_latest.json
```

JSON output:

```bash
python scripts/evaluate_rag.py \
  --dataset data/evaluation/rag_eval.json \
  --format json
```

Vector, Hybrid, Hybrid + Reranker retrieval quality ကိုနှိုင်းယှဉ်ရန်:

```bash
python scripts/evaluate_rag.py --retrieval-mode vector \
  --output reports/rag_eval_vector.json

python scripts/evaluate_rag.py --retrieval-mode hybrid \
  --fusion-strategy rrf \
  --output reports/rag_eval_hybrid.json

python scripts/evaluate_rag.py --retrieval-mode hybrid \
  --fusion-strategy rrf \
  --reranker-enabled \
  --output reports/rag_eval_hybrid_reranker.json
```

Report summary fields:

- `total_cases`: evaluation case count
- `retrieval_hit_rate`: expected source found in retrieved results
- `average_expected_source_rank`: average rank for matched expected sources
- `average_best_source_score`: average best Qdrant score for expected sources
- `answer_keyword_coverage_rate`: average expected keyword coverage in answers

Each case records:

- `question`
- `expected_sources`
- `retrieved_documents`
- `retrieval_score`
- `answer_output`
- `answer_score`

`retrieved_documents` includes debug scores when available:

- `vector_score`
- `bm25_score`
- `fusion_score`
- `reranker_score`

Feedback-aware evaluation metrics can be included without changing retrieval or
answer behavior:

```bash
python scripts/evaluate_rag.py \
  --dataset data/evaluation/rag_eval.json \
  --include-feedback-metrics \
  --output reports/rag_eval_with_feedback.json
```

Optional feedback metric filters:

- `--feedback-user-id`
- `--feedback-retrieval-mode vector|bm25|hybrid`
- `--feedback-status PROCESSING|SUCCESS|ERROR`
- `--feedback-created-from`
- `--feedback-created-to`

Feedback metrics added to the report summary when enabled:

- `feedback_count`
- `average_user_rating`
- `bad_answer_rate`: rating `<= 2`
- `good_answer_rate`: rating `>= 4`

Export low-rated feedback queries into the existing evaluation dataset format:

```bash
python scripts/export_failed_queries.py \
  --max-rating 2 \
  --output data/evaluation/failed_queries.json
```

The exported dataset can be evaluated with the existing runner:

```bash
python scripts/evaluate_rag.py \
  --dataset data/evaluation/failed_queries.json \
  --output reports/rag_eval_failed_queries.json
```

## RAG Observability

When optional internal generation is enabled, `/api/chat` requests create a
best-effort trace record in PostgreSQL without changing answer behavior. Trace
persistence failure is logged and does not break the chat response. In the
default retrieval-first stack, `/api/chat` returns
`Internal answer generation is not configured.`

Trace flow:

```text
/api/chat
  -> resolve X-Request-ID or generate a UUID
  -> set request-scoped TraceContext using ContextVar
  -> PermissionService ACL lookup
  -> RetrievalService timing
  -> optional RerankerService timing
  -> optional GenerationService timing
  -> save rag_traces row
```

Request ID handling:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: req-demo-001" \
  -d '{"question":"What is the remote work policy?","top_k":5}' \
  -i
```

The response includes the same `X-Request-ID` header. If the request header is
missing, the API generates one.

`rag_traces` fields:

- `request_id`
- `user_id`
- `question`
- `retrieval_mode`
- `retrieval_time_ms`
- `reranker_time_ms`
- `generation_time_ms`
- `total_time_ms`
- `model_name`
- `retrieved_count`
- `status`
- `error_message`
- `prompt_tokens`
- `completion_tokens`
- `retrieved_sources`
- `created_at`

`retrieved_sources` preserves source debug information when available:

- `filename`
- `source_path`
- `page_number`
- `chunk_index`
- `score`
- `vector_score`
- `bm25_score`
- `fusion_score`
- `reranker_score`

### Trace Analytics API

Trace analytics endpoints are read-only and protected by the existing JWT
authentication dependency. RBAC is not included yet.

List traces:

```bash
curl "http://localhost:8000/api/traces?limit=50&offset=0&status=SUCCESS&retrieval_mode=hybrid" \
  -H "Authorization: Bearer <access_token>"
```

Supported filters:

- `limit`: page size, default `50`, max `200`
- `offset`: pagination offset, default `0`
- `user_id`: trace user id
- `status`: `PROCESSING`, `SUCCESS`, or `ERROR`
- `retrieval_mode`: `vector`, `bm25`, or `hybrid`
- `created_from`: ISO datetime lower bound
- `created_to`: ISO datetime upper bound

Get one trace by request id:

```bash
curl http://localhost:8000/api/traces/req-demo-001 \
  -H "Authorization: Bearer <access_token>"
```

If duplicate `request_id` rows exist, the API returns the newest trace by
`created_at DESC, id DESC`.

### RAG Feedback API

Feedback is stored separately from the chat pipeline. Submitting feedback does
not re-run retrieval, generation, reranking, or ACL checks.

Submit feedback for a generated answer:

```bash
curl -X POST http://localhost:8000/api/traces/req-demo-001/feedback \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"rating":5,"comment":"The answer cited the correct policy."}'
```

`rating` must be an integer from `1` to `5`. Feedback rows are append-only;
there are no update or delete endpoints in this milestone. If duplicate
`request_id` trace rows exist, feedback links to the newest trace by
`created_at DESC, id DESC`.

List feedback for analytics:

```bash
curl "http://localhost:8000/api/feedback?limit=50&offset=0&rating=5&request_id=req-demo-001" \
  -H "Authorization: Bearer <access_token>"
```

Supported filters:

- `limit`: page size, default `50`, max `200`
- `offset`: pagination offset, default `0`
- `user_id`: feedback submitter user id
- `rating`: integer from `1` to `5`
- `request_id`: associated trace request id
- `created_from`: ISO datetime lower bound
- `created_to`: ISO datetime upper bound

`rag_feedback` fields:

- `id`
- `trace_id`
- `user_id`
- `rating`
- `comment`
- `created_at`

### RAG Analytics Dashboard API

Dashboard analytics endpoints are read-only, JWT protected, and query the
existing `rag_traces` and `rag_feedback` tables only. They do not change chat,
retrieval, ACL, hybrid search, reranker, or generation behavior.

Summary metrics:

```bash
curl "http://localhost:8000/api/analytics/summary?status=SUCCESS&retrieval_mode=hybrid" \
  -H "Authorization: Bearer <access_token>"
```

Feedback metrics:

```bash
curl "http://localhost:8000/api/analytics/feedback?created_from=2026-08-01T00:00:00Z&created_to=2026-08-09T23:59:59Z" \
  -H "Authorization: Bearer <access_token>"
```

Retrieval metrics and top failed documents:

```bash
curl "http://localhost:8000/api/analytics/retrieval?top_failed_limit=10" \
  -H "Authorization: Bearer <access_token>"
```

Supported filters:

- `user_id`
- `status`: `PROCESSING`, `SUCCESS`, or `ERROR`
- `retrieval_mode`: `vector`, `bm25`, or `hybrid`
- `created_from`: ISO datetime lower bound
- `created_to`: ISO datetime upper bound
- `top_failed_limit`: `/api/analytics/retrieval` only, default `10`, max `100`

Dashboard metrics include:

- `total_questions`: count of matching trace rows
- `average_latency_ms`: average `rag_traces.total_time_ms`
- `average_user_rating`: average feedback rating
- `bad_answer_rate`: feedback rating `<= 2`
- `good_answer_rate`: feedback rating `>= 4`
- `retrieval_mode_distribution`: trace count and rate by retrieval mode
- `top_failed_documents`: filenames from low-rated feedback traces with
  failure count and average retrieval score when source scores are available

## Code RAG

Code RAG indexes Git repositories into the same Qdrant collection as company
documents, then reuses the existing ACL, retrieval, hybrid search, reranker,
trace, feedback, evaluation, and analytics flow.

Code ingestion flow:

```text
Git repository
  -> clone selected branch
  -> discover supported source files
  -> tree-sitter parser
  -> AST-based code chunker
  -> existing embedding service
  -> Qdrant code vectors
  -> PostgreSQL code metadata
  -> grant repository ACL to uploader
```

Ingest a repository:

```bash
curl -X POST http://localhost:8000/api/code/ingest \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url":"https://github.com/company/app.git",
    "branch":"main",
    "include_globs":["**/*.py","**/*.ts"],
    "exclude_globs":["**/node_modules/**","**/dist/**"]
  }'
```

Code chunks preserve document-compatible source fields and add code metadata:

- `content_type`: `code`
- `filename`: repository-relative file path
- `source_path`: `<repo_name>@<commit_sha>/<file_path>`
- `file_type`: `code`
- `language`
- `symbol_name`
- `symbol_kind`
- `start_line`
- `end_line`
- `commit_sha`

When optional internal generation is enabled, code sources are returned through
the existing `/api/chat` source list with `page_number=null`. In the default
retrieval-first stack, use Knowledge Explorer or MCP retrieval tools for code
source inspection.

Repository management endpoints:

```bash
# list accessible repositories for current user
curl -H "Authorization: Bearer <access_token>" \
  http://localhost:8000/api/code/repositories

# repository detail with files and chunks
curl -H "Authorization: Bearer <access_token>" \
  http://localhost:8000/api/code/repositories/1

# reindex the stored repository clone at the same branch/commit
curl -X POST http://localhost:8000/api/code/repositories/1/reindex \
  -H "Authorization: Bearer <access_token>"

# delete repository metadata, code files/chunks, Qdrant points, and stored clone
curl -X DELETE http://localhost:8000/api/code/repositories/1 \
  -H "Authorization: Bearer <access_token>"
```

Repository list/detail responses expose `status`, `branch`, `commit_sha`,
`file_count`, `chunk_count`, `created_at`, and `updated_at`. Reindex preserves
the existing repository ACL row target and replaces files/chunks without
leaving old Qdrant points referenced by PostgreSQL.

Code RAG evaluation dataset example:

```bash
python scripts/evaluate_rag.py \
  --dataset data/evaluation/code_rag_eval.json \
  --output reports/code_rag_eval_latest.json
```

### Code Metadata Tables

Code RAG adds these PostgreSQL tables:

- `code_repositories`
- `code_files`
- `code_chunks`
- `code_repository_permissions`

For local development after pulling this milestone, recreate or reset the
PostgreSQL metadata database if existing containers were created before these
tables existed:

```bash
docker compose down
docker volume rm company-document-rag_postgres_storage
docker compose up
```

## Environment Defaults

Docker Compose တွင် default values များကိုသတ်မှတ်ထားသည်။

- `APP_ENV=development`
- `DATABASE_AUTO_CREATE=true`
- `QDRANT_URL=http://qdrant:6333`
- `QDRANT_COLLECTION_NAME=company_documents`
- `DATABASE_URL=postgresql+psycopg://rag:rag_password@postgres:5432/company_rag`
- `JWT_SECRET_KEY=dev-only-change-this-secret-change-me`
- `JWT_ALGORITHM=HS256`
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60`
- `RETRIEVAL_MODE=hybrid`
- `HYBRID_FUSION_STRATEGY=rrf`
- `HYBRID_VECTOR_WEIGHT=0.6`
- `HYBRID_BM25_WEIGHT=0.4`
- `HYBRID_CANDIDATE_MULTIPLIER=4`
- `BM25_K1=1.5`
- `BM25_B=0.75`
- `RERANKER_ENABLED=false`
- `RERANKER_MODEL_NAME=cross-encoder/ms-marco-MiniLM-L-6-v2`
- `RERANKER_CANDIDATE_SIZE=20`
- `RERANKER_BATCH_SIZE=16`
- `INTERNAL_GENERATION_ENABLED=false`
- `OLLAMA_BASE_URL=http://ollama:11434` optional, used only when internal generation is enabled
- `OLLAMA_MODEL=llama3.1:8b` optional, used only when internal generation is enabled
- `EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2`
- `DOCUMENT_CHUNK_SIZE=1000`
- `DOCUMENT_CHUNK_OVERLAP=150`
- `MAX_REQUEST_BODY_BYTES=26214400`
- `MAX_UPLOAD_FILE_SIZE=26214400`
- `MAX_UPLOAD_BYTES=26214400` backward-compatible alias for `MAX_UPLOAD_FILE_SIZE`
- `MAX_BULK_UPLOAD_SIZE=268435456`
- `MAX_BULK_FILE_COUNT=100`
- `NGINX_CLIENT_MAX_BODY_SIZE=256m`
- `NGINX_PROXY_READ_TIMEOUT=1800s`
- `NGINX_PROXY_SEND_TIMEOUT=1800s`
- `VITE_API_TIMEOUT_MS=1800000`
- `PDF_MIN_TEXT_CHARS=20`
- `PDF_OCR_ENABLED=true`
- `PDF_OCR_LANGUAGES=jpn+eng`
- `PDF_OCR_DPI=200`
- `PDF_OCR_TIMEOUT_SECONDS=120`
- `PDF_OCR_MAX_PAGES=100`
- `PDF_TEXT_EXTRACTION_TIMEOUT_SECONDS=30`
- `SECURITY_HEADERS_ENABLED=true`
- `RATE_LIMIT_ENABLED=true`
- `RATE_LIMIT_REQUESTS=120`
- `RATE_LIMIT_WINDOW_SECONDS=60`
- `CODE_REPOSITORY_ALLOWED_HOSTS=*`
- `AUDIT_LOG_ENABLED=true`
- `LOG_LEVEL=INFO`
- `MCP_HOST=0.0.0.0`
- `MCP_PORT=8001`
- `MCP_PATH=/mcp`
- `MCP_PUBLIC_URL=http://localhost:8001/mcp`
- `MCP_SERVICE_ACCOUNT_EMAIL=` blank until MCP service account is configured
- `MCP_SERVICE_TOKEN_SHA256=` blank until MCP bearer token digest is configured

## Production Hardening

Production deployment keeps the existing Document RAG, Code RAG, ACL, Hybrid
Search, Reranker, Trace, Feedback, Evaluation, and Analytics behavior unchanged.

Production architecture:

```text
Browser
  -> FastAPI
  -> Auth / ACL / Retrieval Services
  -> PostgreSQL metadata
  -> Qdrant vector store

Codex / Claude Code
  -> MCP streamable HTTP
  -> Auth / ACL / Retrieval Services
  -> PostgreSQL metadata
  -> Qdrant vector store
```

Operational hardening added:

- Alembic migration version control
- production startup through `alembic upgrade head`
- PostgreSQL backup/restore scripts
- Qdrant snapshot workflow
- stored file backup/restore scripts
- dependency readiness endpoint for PostgreSQL and Qdrant by default
- Docker health checks and restart policies
- request size limit, upload size validation, security headers, rate limiting
- text-first PDF extraction with optional Japanese OCR fallback for scanned PDFs
- Office document extraction for DOCX, XLSX, and PPTX without Microsoft Office
- NFKC text normalization and Japanese-capable BM25 tokenization for document retrieval
- production JWT secret validation and code repository host allowlist
- audit logs for auth, ingestion, document management, and ACL changes
- benchmark and vector consistency audit scripts

Production startup:

```bash
cp .env.production.example .env.production
# edit all secrets and repository allowlist first
docker compose \
  --env-file .env.production \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  up -d --build
```

Manual migration commands:

```bash
DATABASE_URL=postgresql+psycopg://... alembic upgrade head
DATABASE_URL=postgresql+psycopg://... alembic downgrade -1
```

For an existing local/prototype database created with SQLAlchemy `create_all()`,
verify the schema and then mark it as migrated:

```bash
DATABASE_URL=postgresql+psycopg://... alembic stamp head
```

Backup commands:

```bash
DATABASE_URL=postgresql+psycopg://... scripts/backup_postgres.sh
python scripts/qdrant_snapshot.py create
scripts/backup_stored_files.sh
```

Restore procedures and lifecycle details:

- [Production Deployment](docs/production.md)
- [Backup And Restore](docs/backup_restore.md)
- [Data Lifecycle Management](docs/data_lifecycle.md)

Benchmark examples:

```bash
python scripts/benchmark_rag.py chat \
  --token <access_token> \
  --requests 20 \
  --concurrency 4 \
  --question "What is the remote work policy?"

python scripts/benchmark_rag.py retrieval \
  --requests 20 \
  --retrieval-mode hybrid \
  --reranker-enabled
```

Vector consistency audit:

```bash
python scripts/audit_vector_consistency.py --output reports/vector_audit.json
```

## Authentication Notes

Authentication is kept separate from RAG business logic. User registration stores
Argon2 password hashes in PostgreSQL, login returns a JWT bearer token, and
protected APIs validate the token before calling RAG services.

Register and login:

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"strong-password"}'

curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"strong-password"}'
```

Admin user management is available through JWT-protected endpoints. RBAC is not
included yet, so any active authenticated user can call this admin API until a
future role model is added.

```bash
curl -H "Authorization: Bearer <access_token>" \
  http://localhost:8000/api/admin/users

curl -X POST http://localhost:8000/api/admin/users \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"email":"analyst@example.com","password":"strong-password","is_active":true}'

curl -X PATCH http://localhost:8000/api/admin/users/2/activation \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"is_active":false}'
```

Future auth work:

1. Add refresh tokens.
2. Add password reset.
3. Add email verification.

## Permission Notes

Access control is user-document and user-repository ACL v1 only. There are no
roles, departments, tenants, or document ownership rules yet.

PostgreSQL is the source of truth for permissions. Qdrant remains vector storage
only. At query time the API asks PostgreSQL for the current user's accessible
Qdrant point IDs, then passes those IDs to retrieval as a generic
`allowed_point_ids` filter.

New document uploads automatically grant document access to the uploader. New
repository ingestion automatically grants repository access to the uploader.

Grant/revoke document access:

```bash
curl -X POST http://localhost:8000/api/documents/1/permissions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"user_id":2}'

curl -X DELETE http://localhost:8000/api/documents/1/permissions/2 \
  -H "Authorization: Bearer <access_token>"
```

List accessible documents for the current user:

```bash
curl -H "Authorization: Bearer <access_token>" \
  http://localhost:8000/api/documents
```

Grant/revoke code repository access:

```bash
curl -X POST http://localhost:8000/api/admin/permissions/code-repositories/1/users \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"user_id":2}'

curl -X DELETE http://localhost:8000/api/admin/permissions/code-repositories/1/users/2 \
  -H "Authorization: Bearer <access_token>"
```

Admin permission lookup endpoints:

- `GET /api/admin/permissions/users/{user_id}/documents`
- `POST /api/admin/permissions/users/{user_id}/documents`
- `DELETE /api/admin/permissions/users/{user_id}/documents/{document_id}`
- `GET /api/admin/permissions/users/{user_id}/code-repositories`
- `POST /api/admin/permissions/users/{user_id}/code-repositories`
- `DELETE /api/admin/permissions/users/{user_id}/code-repositories/{repository_id}`
- `GET /api/admin/permissions/documents/{document_id}/users`
- `POST /api/admin/permissions/documents/{document_id}/users`
- `DELETE /api/admin/permissions/documents/{document_id}/users/{user_id}`
- `GET /api/admin/permissions/code-repositories/{repository_id}/users`
- `POST /api/admin/permissions/code-repositories/{repository_id}/users`
- `DELETE /api/admin/permissions/code-repositories/{repository_id}/users/{user_id}`

List accessible code repositories for the current user:

```bash
curl -H "Authorization: Bearer <access_token>" \
  http://localhost:8000/api/code/repositories
```

### Permission Backfill

Existing documents created before ACL support will not have
`document_permissions` rows. Existing repositories created before repository ACL
support will not have `code_repository_permissions` rows. Register or choose an
initial admin user, then grant that user access to existing resources:

```bash
docker compose exec postgres psql -U rag -d company_rag -c "
INSERT INTO document_permissions (document_id, user_id, created_at, updated_at)
SELECT d.id, u.id, NOW(), NOW()
FROM documents d
JOIN users u ON u.email = 'admin@example.com'
ON CONFLICT (document_id, user_id) DO NOTHING;

INSERT INTO code_repository_permissions (repository_id, user_id, created_at, updated_at)
SELECT r.id, u.id, NOW(), NOW()
FROM code_repositories r
JOIN users u ON u.email = 'admin@example.com'
ON CONFLICT (repository_id, user_id) DO NOTHING;
"
```

To reset ACL rows in local development:

```bash
docker compose exec postgres psql -U rag -d company_rag -c \
  "TRUNCATE TABLE document_permissions, code_repository_permissions RESTART IDENTITY;"
```

## MCP Server

The MCP layer lets Codex, Claude Code, and other Streamable HTTP MCP clients use
the Knowledge Base as read-only retrieval tools while the Knowledge Base stays a
standalone backend/service. Agent logic remains outside this project.

MCP architecture:

```text
Codex / Claude Code / MCP Client
  -> MCP streamable HTTP
  -> Company Knowledge Base MCP Server
  -> existing KB service layer
  -> PermissionService / RetrievalService
  -> PostgreSQL / Qdrant
```

MCP v1 tools:

- `search_knowledge`: search accessible Document RAG and Code RAG chunks without
  final answer generation.
- `ask_knowledge`: backward-compatible optional internal generation tool. When
  no generation provider is configured, it returns a clear unavailable response
  and callers should use retrieval tools instead.
- `get_document`: return accessible document metadata/details after ACL check.
- `search_code`: search only accessible Code RAG chunks, with optional language
  filtering.

MCP v1 authentication uses one model: a dedicated MCP service account mapped to
an existing KB user. Codex sends `Authorization: Bearer <mcp-service-token>`.
The MCP server stores only `MCP_SERVICE_TOKEN_SHA256`, resolves
`MCP_SERVICE_ACCOUNT_EMAIL` to an existing active KB user, and reuses normal KB
ACL rows for every retrieval/document operation.

Codex Streamable HTTP config:

```toml
[mcp_servers.company_knowledge_base]
url = "http://<knowledge-base-host>:8001/mcp"
bearer_token_env_var = "COMPANY_KB_MCP_TOKEN"
enabled = true
required = true
enabled_tools = [
  "search_knowledge",
  "get_document",
  "search_code",
]
default_tools_approval_mode = "writes"
startup_timeout_sec = 10
tool_timeout_sec = 60
```

Claude Code can use the same Streamable HTTP endpoint and bearer token. No
client-specific MCP behavior is required.

Run the MCP service:

```bash
docker compose --profile mcp up -d --build mcp
```

See [MCP Server](docs/mcp.md) for schemas, deployment, Codex App and CLI
configuration, and the test plan.

## Next Milestones

1. Run target-host Codex App/CLI smoke verification against the production MCP URL.
2. Run production backup and recovery drills.
3. Add document versioning as a dedicated schema migration.
4. Move rate limiting to Redis before running multiple API replicas.
