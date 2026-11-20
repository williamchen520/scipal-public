# SciPal

> Public code snapshot of an auditable scientific RAG and agent platform.  
> Research preview, not production.  
> License: AGPL-3.0-or-later.

## What it is

SciPal combines:

```text
scientific retrieval
evidence ledger (claim -> evidence)
human review actions
error lifecycle + outbox worker
PostgreSQL audit storage
MCP / plugin boundaries
local-only deployment
```

The core principle:

```text
machine retrieves and organizes
human judges and takes responsibility
system records, verifies, and reproduces
```

## Quickstart

```bash
cp deploy/.env.example deploy/.env
# edit DSNs and secrets
docker compose -f deploy/docker-compose.yml up -d --build
curl http://127.0.0.1:5000/api/health
```

## Tests

```bash
python -m unittest discover -s tests -p "test_*.py"
```

The full suite requires the local PostgreSQL DSNs and test fixtures. A code-only mirror is not a complete data distribution.

## Audit loop

```text
answer
  -> ledger
  -> human review
  -> action + error + outbox (one transaction)
  -> worker rewrite
  -> new ledger version
  -> server-side verification + diff
  -> closed / unresolved
```

Start with:

```text
examples/audit-ledger-sample.json
docs/architecture/Evidence-Ledger-Schema.md
docs/architecture/Routing-and-Data-Flow.md
```

## Repository layout

```text
routes/              Flask blueprints
services/            search, QA, audit, tenancy, review
plugins/             optional plugin SDK packages
frontend/            static UI
deploy/              compose and SQL migrations
tests/               unit/integration tests
examples/            synthetic audit/polish samples
contract/            executable contract spec + generated artifacts
docs/architecture/   selected public design notes
```

## Status

```text
v0.1.4-research-preview
1496 tests OK on the private development tree
316 route+method
61 migrations
contract app / runtime route gate
```

## Limits

```text
not production
S1 benchmark is small
no external user study
no manuscript, private corpus, or SciFact dataset in this repository
```

See `CITATION.cff`, `LICENSE`, `PUBLIC-MIRROR.md`, `THIRD_PARTY_NOTICES.md`, and `docs/releases/v0.1.4.md`.

SciFact results are metrics-only; see `eval/SCIFACT.md`.
