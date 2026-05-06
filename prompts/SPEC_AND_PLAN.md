# IMS build — spec traceability

This file satisfies the assignment requirement to check in prompts/spec/plan material used to create the repository.

## Source specification

- Engineering assignment: **Incident Management System (IMS)** — mission-critical monitoring and failure mediation workflow (PDF: Engineering_Assignment__Incident_Management_System.pdf).

## Design decisions (summary)

| Requirement | Approach |
|-------------|----------|
| High-throughput ingestion | `asyncio` bounded queue + pool of workers; HTTP accepts fast and returns 503 when queue full |
| Debouncing (same component, 10s window) | Redis key `debounce:wi:{component_id}` → active `work_item_id` with TTL |
| Raw signal audit (NoSQL) | MongoDB collection `raw_signals`, indexed by `work_item_id` |
| Source of truth (transactional) | PostgreSQL: `work_items`, `rca_records`, `signal_aggregates` |
| Hot-path dashboard cache | Redis key `cache:incidents:active` with short TTL; invalidated on writes |
| Timeseries aggregations | Per-minute buckets in `signal_aggregates` |
| Alerting by component type | **Strategy** pattern in `app/workflow/alerting.py` |
| Lifecycle | **State machine** in `app/workflow/state_machine.py` |
| RCA before CLOSED | Validation in service layer + guard on transition to `CLOSED` |
| MTTR | `(rca.incident_end - work_item.first_signal_at)` stored on RCA row |
| Rate limiting | Redis INCR per minute window on ingestion route |
| Observability | `GET /health`; throughput log every 5s from `metrics_loop` |
| Resilience | `retry_async` for Mongo/Postgres writes |

## LLM prompts (representative)

User/architect prompts used during implementation included:

1. *Implement IMS per PDF: backend `/backend`, frontend `/frontend`, Docker Compose, README with architecture and backpressure, sample data, tests for RCA validation, GitHub-ready layout.*
2. *Use Strategy for alerting tiers and State pattern for work item transitions; reject CLOSED without complete RCA.*
