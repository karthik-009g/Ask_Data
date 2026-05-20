# Enterprise AI Data Analytics Platform

FastAPI + Next.js analytics platform where MongoDB Atlas is the only internal application store.

The app supports secure, role-based access to external databases (MySQL, PostgreSQL, MongoDB), natural-language querying, analysis, and export.

## 1) What this project is about

This project solves a common enterprise problem:
- Admin teams connect approved data sources.
- Employees get access only to assigned sources.
- Users ask business questions in plain English.
- The system executes safe reads, returns rows/insights, and supports export.

Core goals:
- Centralized access control by organisation.
- Safe query generation (SELECT-only for SQL).
- One internal persistence layer (Mongo Atlas via `MONGO_URL`).

## 2) Current architecture

- Frontend: Next.js (`frontend/`)
- Backend: FastAPI (`backend/`)
- Internal app/state store: MongoDB Atlas (`MONGO_URL`)
- External data sources (admin-managed):
  - `mysql`
  - `postgresql`
  - `mongodb`

No Docker files and no CI pipeline files are used in this repository now.

## 3) Internal data model (Mongo)

Main collections used by backend services:
- `users`: admin/employee identities, org, hashed password, role
- `connections`: external DB connections (encrypted secrets)
- `permissions`: per-employee, per-connection capability flags
- `metadata_catalog`: discovered schema/field metadata for each connection
- `query_logs`: prompt/query execution logs
- `counters`: sequence IDs for connection records

## 4) Complete end-to-end workflow

### A. Organisation onboarding
1. Admin registers with `/api/v1/auth/register`.
2. Admin logs in with `/api/v1/auth/login`.
3. JWT token is returned and used for protected routes.

Login organisation behavior:
- If the email exists in only one organisation, organisation can be omitted at login.
- If the same email exists in multiple organisations, organisation is required.

### B. Employee provisioning
1. Admin creates employee via `/api/v1/admin/employees`.
2. Employee logs in with `/api/v1/auth/login`.
3. Employee token carries role-based access context.

### C. Data source onboarding by admin
1. Admin creates connection via `/api/v1/admin/connections` (form or URL method).
2. Connection is tested immediately.
3. Credentials are encrypted before storage.
4. Metadata extraction runs and writes into `metadata_catalog`.

### D. Permission assignment
1. Admin assigns allowed connections with `/api/v1/admin/permissions`.
2. Flags include `can_read`, `can_query`, `can_visualize`, `can_export`.
3. Employee-visible connections are filtered strictly by these permissions.

### E. Employee analytics/query usage
1. Employee fetches assigned connections: `/api/v1/employee/connections`.
2. Employee runs analysis/query:
	- `/api/v1/employee/query`
	- `/api/v1/employee/analyse`
3. Employee exports result sets:
	- `/api/v1/employee/export/{csv|excel|pdf}`
	- `/api/v1/employee/analyse/export/{csv|excel|pdf}`

## 5) AI workflow (with and without API keys)

### Provider selection order
1. If `GROQ_API_KEY` exists -> Groq OpenAI-compatible client is used.
2. Else if `OPENAI_API_KEY` exists -> OpenAI client is used.
3. Else -> deterministic fallback mode is used.

### With AI keys present
- SQL generation uses LLM prompts + metadata context.
- Insight summaries (`overview`) are LLM-generated.
- Generation metadata marks mode as `llm` with provider/model.

### Without AI keys
- SQL generation fallback uses heuristic (`SELECT * FROM <first_table> LIMIT 100`).
- Summary fallback computes lightweight numeric statistics and text summary.
- Generation metadata marks mode as `fallback`.

### Safety behavior
- SQL is validated to allow only `SELECT`.
- Unsafe verbs (drop/delete/update/insert/alter/...) are rejected.

## 6) Important endpoint behavior note

For `/api/v1/employee/query`:
- If `connection_ids` are provided, analysis executes against selected permitted sources (includes Mongo).
- If `connection_ids` are omitted, SQL-only path is used and expects at least one permitted SQL source.
- In Mongo-only permission setups, this SQL-only path can return expected `400`.

## 7) Environment setup

Copy environment template:

```bash
copy .env.example .env
```

Required values:
- `MONGO_URL` (Atlas URI; include default DB, e.g. `/auth_db`)
- `JWT_SECRET_KEY`
- `ENCRYPTION_KEY`

Optional AI values:
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default: `gpt-4o-mini`)
- `GROQ_API_KEY`
- `GROQ_MODEL` (default: `llama-3.1-70b-versatile`)

Generate encryption key example:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 8) Run locally (Windows, no Docker)

### First-time setup (one-time)

From project root:

```bash
python -m venv .venv
```

Install backend dependencies:

```bash
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Install frontend dependencies:

```bash
cd frontend
npm install
cd ..
```

Create env file (if missing):

```bash
copy .env.example .env
```

Fill required values in `.env`:
- `MONGO_URL`
- `JWT_SECRET_KEY`
- `ENCRYPTION_KEY`

### Start the project (every run)

Open terminal 1 (backend):

```bash
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open terminal 2 (frontend):

```bash
cd frontend
npm run dev -- --port 3000
```

### Quick health check

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## 9) URLs

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/health
- OpenAPI: http://localhost:8000/docs

## 10) What is already done

- Migrated internal persistence to Mongo-only.
- Removed local system DB dependency for app state.
- Removed Docker setup and CI pipeline files.
- Verified core auth/admin/employee + export flows at runtime.

## 11) What is yet to be done (recommended next)

### Security & production readiness
- Rotate strong secrets for `JWT_SECRET_KEY` and `ENCRYPTION_KEY`.
- Restrict CORS origins from `*` to allowed frontend domains.
- Add structured error masking/log policy for production.

### AI quality and governance
- Add prompt/version tracking for LLM prompts.
- Add response caching and token/cost tracking.
- Add guardrails/validation for generated SQL complexity and table scope.

### Reliability and operations
- Add automated test suite for critical flows (auth, permissions, query/analyse/export).
- Add health checks for external connection latency and failure diagnostics.
- Add backup/retention policy for Mongo collections.

### Product improvements
- Improve NL-to-query routing for multi-source disambiguation.
- Add richer visual analytics and saved dashboard/report objects.
- Add audit UI for permission history and query history.

## 12) Quick checklist before first real use

- Configure `.env` with valid Atlas URI + secrets.
- Start backend and confirm `/health` is OK.
- Start frontend and login as admin.
- Create employee and at least one external connection.
- Assign permissions.
- Verify employee can run query/analyse and export.
