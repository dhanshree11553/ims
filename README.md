# Incident Management System (IMS)

Mission-critical style incident pipeline: ingest high-volume **signals**, debounce by component, store raw audit in **MongoDB**, transactional **work items** and **RCA** in **PostgreSQL**, hot-path **Redis** cache, and a **React** dashboard for lifecycle + RCA.

**Repository (submit this URL in your PDF):** `https://github.com/dhanshree11553/ims`

## Architecture

```mermaid
flowchart LR
  subgraph ingest[Ingestion]
    API[FastAPI /ingest/signals]
    RL[Redis rate limit]
    Q[asyncio.Queue bounded]
    W[Worker pool]
  end
  subgraph storage[Storage]
    M[(MongoDB raw_signals)]
    P[(PostgreSQL work_items + rca + aggregates)]
    R[(Redis debounce + dashboard cache)]
  end
  subgraph ui[UI]
    FE[React dashboard]
  end
  API --> RL --> Q --> W
  W --> M
  W --> P
  W --> R
  FE --> API
  FE --> P
```

- **Producer / backpressure:** HTTP handlers only validate and enqueue. A bounded queue (`SIGNAL_QUEUE_MAX`, default 100k) prevents unbounded memory growth if Postgres/Mongo slow down; when full, ingestion returns **503** so clients can retry with jitter.
- **Debouncing:** Redis key `debounce:wi:{component_id}` maps to the active work item for `DEBOUNCE_WINDOW_SEC` (10s). Bursts (e.g. 100 signals in 10s for the same component) attach to **one** work item; each raw document still lands in Mongo.
- **Alerting:** **Strategy** pattern (`app/workflow/alerting.py`) maps `component_type` → alert tier (e.g. RDBMS → P0, CACHE → P2).
- **Lifecycle:** **State machine** (`app/workflow/state_machine.py`) enforces transitions; **CLOSED** requires a complete RCA (guard + API validation).
- **MTTR:** Computed on RCA save as `incident_end - work_item.first_signal_at` (seconds), persisted on the RCA row.
- **Timeseries:** Minute buckets in `signal_aggregates` (Postgres); `GET /metrics/aggregates`.

## Quick start (Docker Compose)

Requires Docker Desktop (or compatible engine) running.

```bash
docker compose up --build
```

- **API:** http://localhost:8000 — OpenAPI: http://localhost:8000/docs
- **UI:** http://localhost:5173 (nginx serves the built SPA; API is proxied under `/api/`)

Health: `GET http://localhost:8000/health` (Postgres, Mongo, Redis).

### Local development (without full compose)

1. Start Postgres, MongoDB, and Redis (or `docker compose up postgres mongo redis`).
2. Backend:

   ```bash
   cd backend
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   set POSTGRES_DSN=postgresql+asyncpg://ims:ims@localhost:5432/ims
   set MONGO_URI=mongodb://localhost:27017
   set REDIS_URL=redis://localhost:6379/0
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

3. Frontend:

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

   Vite dev server proxies API calls to `http://127.0.0.1:8000`.

## Sample data

With the API up:

```bash
python scripts/push_sample.py --base http://127.0.0.1:8000
```

Optional burst (debounce stress):

```bash
python scripts/push_sample.py --repeat 30
```

Fixture: `scripts/sample_stack_failure.json`.

## Tests

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

Includes unit tests for **RCA completeness** and **CLOSED** transition rules.

## API highlights

| Method | Path                     | Purpose                                             |
| ------ | ------------------------ | --------------------------------------------------- |
| POST   | `/ingest/signals`        | Accept signal (rate-limited; may 503 if queue full) |
| GET    | `/incidents/sorted`      | Active incidents sorted by severity                 |
| GET    | `/incidents/{id}`        | Detail + raw signals from Mongo                     |
| PUT    | `/incidents/{id}/rca`    | Create/update RCA (validates fields, sets MTTR)     |
| PATCH  | `/incidents/{id}/status` | State transition (CLOSED blocked without RCA)       |
| GET    | `/health`                | Liveness + dependency checks                        |
| GET    | `/metrics/aggregates`    | Time buckets                                        |

## Observability

- Structured log line every **5 seconds** with accepted vs processed signals/sec (`app/ingestion/metrics.py`).
- **Retry** wrapper with exponential backoff for Mongo/Postgres writes (`app/util/retry.py`).

## Bonus: security & performance notes

- **Rate limiting** on ingestion (Redis fixed window per minute) to reduce cascade overload.
- **CORS** enabled for dashboard integration (tighten to known origins in production).
- **Indexes** on Mongo `work_item_id` and `received_at` for detail queries.
- **Connection pooling** for Postgres; **pipelined** acceptance path via in-memory queue + worker pool.
- **Short TTL cache** for active incident list in Redis to protect the primary DB from UI polling storms.

## Submission checklist (assignment)

- [ ] Push this repo to **GitHub** (`/backend`, `/frontend`, compose, scripts, `prompts/`).
- [ ] Replace the GitHub URL at the top of this README and in your PDF.
- [ ] Run `docker compose up --build` and smoke-test UI + `/health`.
- [ ] Export **one PDF** named: `Dhanashree Sayanekar - Infrastructure / SRE Intern Assignment` (include GitHub link).

## Prompts / spec

See `prompts/SPEC_AND_PLAN.md` for traceability to the assignment brief and design notes.
