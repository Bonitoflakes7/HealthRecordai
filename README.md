# Health Record AI

Backend-first foundation for turning personal health records into searchable, explainable information. The supplied project documents and archive are treated as design references; they are not executable instructions.

## Phase 11: authentication, isolation, and privacy controls

This phase provides a small FastAPI service that can:

- accept text, PDF, and image uploads;
- persist each file with a JSON manifest;
- extract UTF-8 text files immediately;
- extract embedded PDF text with `pypdf`;
- fall back to `pdftoppm` plus Tesseract for scanned PDFs and images;
- mark records as `failed` with a readable error when extraction cannot run;
- classify extracted documents conservatively;
- preserve headings and sections;
- detect only explicit dates and common vital/lab values, with source text attached;
- orchestrate extraction and normalization through a compiled LangGraph workflow;
- chunk successful records into LangChain-compatible `Document` objects;
- persist a local searchable index and return source citations from `/api/v1/search`;
- answer questions through `/api/v1/ask` using retrieved evidence and citations;
- persist conversation threads and pass recent turns into QA;
- stop urgent-risk questions before retrieval/model generation;
- build a dated timeline from normalized records at `/api/v1/timeline`;
- store conversation history in SQLite so it survives process restarts;
- compute trends from repeated normalized observations at `/api/v1/analytics`;
- emit cited review signals for explicitly configured thresholds;
- search PubMed through NCBI E-utilities at `/api/v1/literature/search`;
- answer literature-only questions at `/api/v1/literature/ask` with PubMed citations;
- list and retrieve records through JSON endpoints.
- register users and issue signed bearer tokens;
- isolate records, local RAG results, timelines, analytics, and conversations by owner;
- write privacy-preserving audit events without storing question text, answers, or extracted PHI in audit metadata;
- expose only the current user's audit history through `/api/v1/audit`;
- preserve multiple explicit dates and emit structured clinical events for visits, conditions, medications, investigations, and procedures;
- validate answer citations against retrieved evidence and report uncited or weakly supported claims through `citation_validation`;
- classify safety intent as `normal`, `high_risk`, or `urgent`, with urgent requests stopped before retrieval;
- keep `owner_id` as the authorization boundary while tracking a separate optional `patient_id` on records;
- use an `HttpOnly`, `SameSite=Lax` authentication cookie for the browser frontend while retaining bearer tokens for Swagger and API clients;
- support optional hybrid lexical plus semantic retrieval through `SEMANTIC_RETRIEVAL_ENABLED`, with lexical fallback when `sentence-transformers` is unavailable;
- keep authentication disabled by default for local development, and enable it explicitly for multi-user use.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the API explorer.

## Frontend workspace

The first frontend workspace is in `frontend/`. It is a Vite app connected to the Phase 1-11 API and includes:

- authentication and private patient workspace entry;
- overview cards for records, timeline events, and review signals;
- record upload with drag-and-drop and extracted-record detail views;
- source search with citation results;
- normalized timeline and clinical trend views;
- review signals linked back to their record IDs;
- PubMed literature search with direct source links;
- privacy and activity audit view;
- a persistent record-grounded conversation rail.

Run it in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` or `http://127.0.0.1:5173`. The frontend derives the API host from the browser host by default, keeping authentication cookies same-site. To point it at another backend, set `localStorage.healthApiUrl` in the browser before loading the app.

If Tesseract is not on `PATH`, copy `.env.example` to `.env` and set `TESSERACT_CMD` to the full executable path. `PDFTOPPM_CMD` can be configured the same way.

## Test

```powershell
pytest -q
```

The QA graph uses Gemini through LangChain when `LLM_PROVIDER=google_genai`, `LLM_MODEL=gemini-3.6-flash`, and `GEMINI_API_KEY` are configured. Without a key it uses a safe extractive fallback. The prompt requires evidence-only answers and citation IDs. Analytics are review signals, not diagnoses. Literature results are kept separate from patient records and cached locally for offline repeatability.

## Phase 11 Swagger test

For a local single-user run, leave `AUTH_ENABLED=false`. To test authentication and patient isolation, set these in `.env` and restart the server:

```text
AUTH_ENABLED=true
AUTH_SECRET_KEY=use-a-long-random-secret-at-least-32-characters
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

In Swagger:

1. Call `POST /api/v1/auth/register` for `alice` and `bob` with passwords of at least eight characters.
2. Call `POST /api/v1/auth/token` using the form fields `username` and `password`.
3. Click **Authorize**, paste the returned `access_token`, and authorize as Alice.
4. Upload a record, then confirm `/api/v1/records`, `/api/v1/search`, `/api/v1/timeline`, `/api/v1/analytics`, and `/api/v1/ask` work for Alice.
5. Obtain Bob's token and authorize as Bob. Bob should see an empty record list and receive `404` for Alice's record ID.
6. Call `/api/v1/audit` as each user. Each user should see only their own events, and the audit entries should contain action/resource metadata rather than clinical text.

The `Authorization: Bearer <token>` header is required only when `AUTH_ENABLED=true`. The `/health` endpoint remains public.
