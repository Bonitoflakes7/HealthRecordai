# Health Record AI

Health Record AI is a backend-first application for turning a person's scattered health documents into a private, searchable, chronological workspace. It accepts text files, PDFs, scanned PDFs, and images; extracts their content; creates conservative structured records; indexes the source text; and answers questions with evidence and page-level provenance.

This is an information organization and retrieval system. It is not a diagnostic system, a replacement for a clinician, or a source of emergency medical advice.

## Problem Statement

Personal medical information is commonly distributed across consultation notes, prescriptions, lab reports, discharge summaries, scans, and image-based documents. That creates several practical problems:

- Important facts are difficult to find across many files.
- Dates, diagnoses, medications, investigations, procedures, and measurements are not consistently organized.
- A user may remember a later diagnosis but need to know what was documented first.
- Medication history can be confused with current medication use.
- Trends such as glucose, HbA1c, LDL, or blood pressure are hard to compare manually.
- AI answers can be unsafe when they invent facts, confuse temporal sequence with causation, or omit their sources.
- Health records require owner isolation, controlled access, upload validation, and privacy-aware audit logging.

The project addresses these problems with a staged pipeline that keeps the original document, extracted text, normalized data, retrieved evidence, and generated answer as separate layers.

## Current Capabilities

- Upload PDF, TXT, Markdown, CSV, PNG, JPEG, and WEBP files.
- Validate file extension, declared MIME type, byte signature, size, PDF structure, UTF-8 encoding, and binary content.
- Extract embedded PDF text with `pypdf`.
- Fall back to `pdftoppm` and Tesseract OCR for scanned PDFs and images.
- Preserve page boundaries so evidence can be traced to a source page.
- Classify documents conservatively as clinical notes, prescriptions, lab reports, imaging reports, discharge summaries, or unknown.
- Normalize conditions, medications, investigations, procedures, observations, dates, sections, and clinical events.
- Track an optional `patient_id` separately from the authenticated record owner.
- Build a chronological patient timeline.
- Compute transparent clinical trends and configured review signals.
- Search local evidence with lexical retrieval and optional semantic reranking.
- Route questions by intent, including medications, conditions, investigations, procedures, longitudinal history, and first-documented questions.
- Use a LangGraph QA workflow with safety assessment, retrieval, grounded answering, and citation validation.
- Use Gemini through LangChain when configured, with an extractive fallback when no LLM key is available.
- Preserve conversation history in SQLite.
- Search PubMed separately from personal records and return literature citations.
- Provide clickable source links that open the original record at the cited page.
- Support authentication, owner-level patient-record isolation, HttpOnly cookies, bearer tokens for Swagger, and privacy-preserving audit events.
- Provide a Vite frontend with upload, records, timeline, clinical insights, literature search, privacy activity, and a scrollable chat rail.

## Architecture

```text
                         +----------------------+
                         | Vite frontend        |
                         | upload, timeline, QA |
                         +----------+-----------+
                                    |
                                    | HTTP / JSON
                                    v
                         +----------+-----------+
                         | FastAPI API          |
                         | auth, records, ask  |
                         +----+-----------+-----+
                              |           |
              upload         |           | question
                              v           v
                 +------------+--+   +---+----------------+
                 | LangGraph     |   | LangGraph QA       |
                 | ingestion     |   | safety -> route -> |
                 | extract ->    |   | retrieve -> answer |
                 | normalize     |   +---+----------------+
                 +-------+-------+       |
                         |               v
                         v       +-------+--------+
                 +-------+------+| Local RAG index|
                 | records store || chunks.json     |
                 | raw + text +  |+----------------+
                 | structured JSON|
                 +-------+-------+
                         |
                         v
                 +-------+--------+
                 | timeline and   |
                 | clinical trends|
                 +----------------+
```

## End-to-End Workflow

### 1. Upload and ownership

The client sends a document to `POST /api/v1/records`. The API assigns a random record ID and stores the upload under `data/records/<record_id>/`.

Every record has an `owner_id`. When authentication is enabled, this is the authenticated user. An optional `patient_id` identifies the person described by the document, which is intentionally separate from the account owner.

The upload layer checks file size, safe filename extraction, allowed extension, byte-level signature, declared MIME type, PDF readability, UTF-8 validity, and binary null bytes for text files. Invalid files are rejected before ingestion.

### 2. Text extraction

The LangGraph ingestion workflow starts with the `extract` node.

- Text-like files are decoded as UTF-8.
- Text PDFs are read page by page with `pypdf`.
- If a PDF has no usable embedded text, each page is rendered to an image with `pdftoppm` and OCR is run with Tesseract.
- Image uploads are sent directly to Tesseract.

The extractor returns combined text plus a `page_texts` list. If extraction fails, the record is marked `failed` and the readable error is saved instead of sending incomplete content to the model.

### 3. Conservative normalization

The `normalize` node creates a Pydantic `NormalizedDocument`. It does not ask the LLM to invent a clinical interpretation. Deterministic parsing identifies:

- document type, title, explicit date candidates, and selected document date;
- headings and section bodies;
- blood pressure, heart rate, temperature, glucose, and HbA1c observations;
- conditions from assessment, diagnosis, problem, or impression sections;
- medications with dose, frequency, action, and status when stated;
- investigations and procedures with their documented status;
- clinical events for visits, conditions, medications, investigations, and procedures;
- a patient ID only when explicitly present in the source.

Each item keeps `source_text`. When page text is available, that text is matched back to its source page and stored as `source_page`.

The stored record normally contains:

```text
data/records/<record_id>/
  original-file.pdf       # or the uploaded text/image filename
  manifest.json            # ownership, status, type, size, timestamps
  extracted.txt            # extracted combined text
  structured.json          # normalized Pydantic document
```

### 4. Indexing and retrieval

After normalization, extracted text is split into chunks. Each chunk carries `record_id`, filename, chunk index, owner ID, document date, document type, and source page. The local index is persisted in `data/rag/chunks.json`.

Default retrieval is lexical. When `SEMANTIC_RETRIEVAL_ENABLED=true` and the sentence-transformers model is available, semantic similarity is combined with lexical ranking. If the semantic model is unavailable, lexical retrieval remains the fallback.

Normal questions retrieve the most relevant chunks. Longitudinal and first-documented questions retrieve the complete available dated evidence set, so an early or later record is not omitted merely because it has a weaker keyword score.

### 5. Query routing

Before retrieval, the QA graph classifies the question as `medications`, `conditions`, `investigations`, `procedures`, `longitudinal`, `first_documented`, or `general`.

The `first_documented` route is designed for questions such as:

> When was hyperlipidemia first documented?

It retrieves the full record set, identifies the earliest dated evidence, preserves its exact early wording, and presents later terminology chronologically. It must not turn an early finding such as “borderline elevated cholesterol” into a later diagnosis retroactively.

### 6. Safety assessment

The safety node classifies a request as `normal`, `high_risk`, or `urgent`. Normal questions continue. High-risk questions receive an additional safety note. Urgent questions stop before retrieval or model generation and return an emergency-oriented response. This is an interaction safeguard, not a clinical triage service.

### 7. Grounded answer generation

The answerer receives the question, recent conversation history, query intent, evidence metadata, and retrieved chunks. Each chunk is presented with its internal citation ID, page, date, type, and content.

When configured, the LLM is Gemini through `langchain-google-genai` and LangChain's chat interface:

```text
LLM_PROVIDER=google_genai
LLM_MODEL=gemini-3.6-flash
GEMINI_API_KEY=...
```

The prompt requires evidence-only answers, source citations, natural complete sentences, cautious medication-status language, and restraint around causation. For example, an LDL decrease after atorvastatin begins is described as an improvement after treatment initiation unless the record explicitly proves causation.

Without a Gemini key, the system uses an extractive fallback that returns relevant retrieved excerpts with citation IDs.

### 8. Citation validation and presentation

The backend validates citation IDs in the generated answer against the actual retrieved evidence. It reports valid citations, invalid citations, uncited claims, weak lexical support, warnings, and an overall validation status.

The frontend receives the complete retrieved result list. Known internal markers are converted into clickable human-readable links beside the claim, for example:

```text
18 June 2024: “Hyperlipidemia”
Synthetic Patient Record 02.pdf · 18 Jun 2024 · Page 1
```

The link opens `GET /api/v1/records/<record_id>/source#page=<page>`. Internal chunk IDs are not displayed as user-facing text. If an answer contains no usable inline citation, the UI shows a fallback source list.

### 9. Conversation memory

The API creates a conversation ID on the first question. Subsequent questions send that ID back to `POST /api/v1/ask`. Messages and citation IDs are stored in `data/health_record.db`, and recent history is passed into the QA graph so follow-up questions can refer to the previous exchange. Conversation ownership is enforced.

### 10. Timeline and clinical insights

`GET /api/v1/timeline` reads normalized records, assembles dates, source pages, observations, conditions, medications, investigations, procedures, and clinical events, then sorts events chronologically.

`GET /api/v1/analytics` converts numeric observations into dated trend points. It reports directions such as increasing, decreasing, stable, or insufficient data. Configured blood-pressure thresholds produce transparent review signals with record references. These are review signals, not diagnoses, and temporal correlation is not treated as causation.

### 11. External medical literature

PubMed is intentionally separate from personal records. `GET /api/v1/literature/search` searches NCBI E-utilities, while `POST /api/v1/literature/ask` retrieves PubMed results and answers using those results. Literature citations use PubMed URLs and are not mixed into the local patient-record index.

## API Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service health check |
| `POST` | `/api/v1/auth/register` | Create a user |
| `POST` | `/api/v1/auth/token` | Issue a token and browser cookie |
| `POST` | `/api/v1/auth/logout` | Clear the browser cookie |
| `GET` | `/api/v1/auth/me` | Read the current user |
| `POST` | `/api/v1/records` | Upload and ingest a document |
| `GET` | `/api/v1/records` | List visible records |
| `GET` | `/api/v1/records/{record_id}` | Read extracted and normalized data |
| `GET` | `/api/v1/records/{record_id}/source` | Open the original upload |
| `GET` | `/api/v1/search?q=...` | Search local source chunks |
| `POST` | `/api/v1/ask` | Ask a grounded question |
| `GET` | `/api/v1/timeline` | Read the normalized timeline |
| `GET` | `/api/v1/analytics` | Read trends and review signals |
| `GET` | `/api/v1/audit` | Read the owner's audit events |
| `GET` | `/api/v1/literature/search?q=...` | Search PubMed |
| `POST` | `/api/v1/literature/ask` | Ask a literature-only question |

Swagger is available at `http://127.0.0.1:8000/docs`.

## Setup

### Backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn backend.app.main:app --reload
```

The project expects `pdftoppm` and `tesseract` on `PATH` for scanned PDFs and images. Configure their paths with `PDFTOPPM_CMD` and `TESSERACT_CMD` if needed.

### Gemini

Set the key only in the local `.env` file:

```text
LLM_PROVIDER=google_genai
LLM_MODEL=gemini-3.6-flash
GEMINI_API_KEY=your-key
```

Do not commit `.env` or expose the key in frontend code. Rotate a key if it is ever exposed in a chat, terminal log, screenshot, or repository.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The frontend derives the backend host from the browser host. To point it at another backend, set `localStorage.healthApiUrl` before loading the app.

## Configuration

The main settings are loaded from `.env`:

| Setting | Meaning | Default |
| --- | --- | --- |
| `DATA_DIR` | Records, RAG index, database, and literature cache | `./data` |
| `MAX_UPLOAD_MB` | Maximum upload size | `25` |
| `PDFTOPPM_CMD` | PDF renderer | `pdftoppm` |
| `TESSERACT_CMD` | OCR executable | `tesseract` |
| `LLM_PROVIDER` | LLM provider | `google_genai` |
| `LLM_MODEL` | Gemini model name | unset unless configured |
| `GEMINI_API_KEY` | Gemini credential | unset |
| `AUTH_ENABLED` | Enable authentication and isolation | `false` |
| `AUTH_SECRET_KEY` | HMAC signing key | development placeholder |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime | `60` |
| `AUTH_COOKIE_SECURE` | Require HTTPS for cookie | `false` locally |
| `SEMANTIC_RETRIEVAL_ENABLED` | Enable semantic reranking | `false` |
| `SEMANTIC_RETRIEVAL_WEIGHT` | Semantic score contribution | `0.35` |
| `SEMANTIC_MODEL_NAME` | Sentence-transformers model | `all-MiniLM-L6-v2` |

For an authenticated run, set `AUTH_ENABLED=true` and use an `AUTH_SECRET_KEY` of at least 32 bytes. The browser uses an HttpOnly SameSite cookie; Swagger and API clients can use the bearer token returned by `/api/v1/auth/token`.

## Swagger Smoke Test

For the easiest local development run, leave `AUTH_ENABLED=false`:

1. Open `/docs` and call `GET /health`.
2. Upload a small text or PDF file with `POST /api/v1/records`.
3. Confirm the response contains `status`, extracted text, and `structured` data.
4. Call `GET /api/v1/records` and `GET /api/v1/records/{id}`.
5. Call `GET /api/v1/search?q=...` using a phrase from the document.
6. Call `POST /api/v1/ask` with a question grounded in that document.
7. Reuse the returned `conversation_id` for a follow-up question.
8. Check `/api/v1/timeline`, `/api/v1/analytics`, and `/api/v1/records/{id}/source`.

For isolation testing, set `AUTH_ENABLED=true` and a strong secret, register Alice and Bob, upload as Alice, then confirm Bob cannot list, retrieve, search, or ask about Alice's record. Check `/api/v1/audit` as each user; each account should see only its own events.

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest
cd frontend
npm run build
```

The backend tests cover extraction, OCR fallbacks, normalization, rich clinical schema, ingestion, retrieval, semantic fallback, query routing, first-documented retrieval, answer citation validation, safety behavior, timeline assembly, analytics, conversations, authentication, patient isolation, upload hardening, and API behavior.

## Project Layout

```text
backend/app/
  api/routes.py                    FastAPI routes and ownership checks
  core/config.py                   Environment-backed settings
  models/                          Pydantic request, response, and clinical models
  services/extraction.py           Text, PDF, and OCR extraction
  services/records.py              Upload storage and validation
  services/normalization.py        Conservative structured extraction
  services/retrieval.py            Local lexical and optional semantic RAG
  services/answering.py            Gemini/extractive grounded answerer
  services/query_router.py         Question intent routing
  services/citation_validator.py   Citation verification
  services/safety.py               Safety intent checks
  services/timeline.py             Timeline assembly
  services/analytics.py            Trends and review signals
  services/security.py             Auth, tokens, hashing, and audit events
  services/sqlite_conversations.py Conversation persistence
  services/pubmed.py               External literature retrieval
  workflows/ingestion.py           LangGraph ingestion graph
  workflows/qa.py                  LangGraph question-answer graph
frontend/
  src/main.js                      Vite frontend behavior and rendering
  src/styles.css                   Frontend styling
data/
  records/                         Per-record raw and derived files
  rag/chunks.json                  Persistent local retrieval index
  health_record.db                Users, audit events, and conversations
tests/                             Automated backend tests
```

## Design Boundaries and Known Limitations

- Normalization is conservative pattern-based extraction, not a full clinical NLP or FHIR implementation.
- The system reports what is documented; it does not prove that a patient took a medication or that one treatment caused a later measurement change.
- Missing values remain missing. The answerer is instructed not to invent results.
- OCR quality depends on scan quality, resolution, language, and the local Tesseract installation.
- The local JSON index and SQLite database are suitable for this development project, not a production multi-node deployment.
- Gemini usage, rate limits, model availability, and API pricing are controlled by the configured Google account and model service.
- PubMed availability depends on network access and NCBI service availability.
- Production use still requires encrypted storage, managed secrets, HTTPS, backups, migrations, rate limiting, monitoring, and a formal privacy/security review.

## Current Phase Status

1. File ingestion and extraction.
2. Conservative normalization.
3. Local RAG.
4. Conversation memory.
5. Timeline and clinical event assembly.
6. Clinical trend analysis and review signals.
7. External medical-literature RAG.
8. Citation and claim validation.
9. Upload signature validation and hardening.
10. Owner/patient identity separation.
11. Secure browser token storage and authentication.
12. Optional hybrid lexical plus semantic retrieval.
13. First-documented evidence routing and complete chronological retrieval.
14. Human-readable inline source-page citations in the frontend.

The next engineering priorities are production hardening, richer structured clinical interoperability, stronger evaluation datasets, and end-to-end browser tests.
