# App Factory Design (proposal)

> Status: design only. No `api_server.py` change in this document's PR.  
> Goal: make the real Flask app importable without deployment DSNs, so the
> runtime contract can run in CI.

---

## 1. Problem

`api_server.py` currently creates `app` at import time and performs side effects
before any request:

```text
app = Flask(...)                       line 71
check_env()                            line 75
bootstrap_default_workspace(...)       line 88 (DB)
_load_plugins(app)                     line 516
register_blueprint(...)                many lines
@app.before_request                    line 102
```

`validate_arch.py` imports `api_server:app`. In a CI runner without
`SCIPAL_AUTH_DSN` / `SCIPAL_CORE_DSN`, the import can fail before route
comparison. The current workaround is the manual release gate:

```text
python scripts/runtime_contract_check.py
```

That is correct for releases, but it cannot protect normal PRs.

## 2. Target interface

```python
@dataclass(frozen=True)
class AppConfig:
    db_path: Path = DB_PATH
    strict_env: bool = True
    bootstrap_tenancy: bool = True
    load_plugins: bool = True
    static_folder: Path = FRONTEND_DIR

def create_app(config: AppConfig | None = None) -> Flask: ...
```

Default behavior must stay exactly the current production behavior:

```python
app = create_app()  # api_server:app remains a valid WSGI target
```

A contract-only app:

```python
# contract_app.py
from api_server_factory import AppConfig, create_app
app = create_app(AppConfig(
    strict_env=False,
    bootstrap_tenancy=False,
    load_plugins=True,
))
```

Step 3 finding: `data_sandbox` contributes 12 routes, so the contract app must
load plugins to match the 316-route architecture. Plugin loading is currently
DSN-free; if a future plugin needs DSN, exclude its routes explicitly instead
of hidden-skipping them.

Then CI can run:

```bash
python scripts/validate_arch.py --app contract_app:app
```

with no DSN.

## 3. Separation of concerns

| Concern | Current | Factory |
|---|---|---|
| Flask object | module global | `create_app()` |
| Env guard | import-time | `config.strict_env` |
| Tenancy bootstrap | import-time | `config.bootstrap_tenancy` |
| Plugin loading | import-time | `config.load_plugins` |
| Blueprint registration | import-time | `register_blueprints(app)` |
| Auth hook | import-time decorator | `register_hooks(app)` |
| DB migrations | `__main__` | unchanged, not factory |
| Model warmup | `__main__` | unchanged, not factory |
| Lazy retrievers | module globals | keep for first refactor |

The first factory must **not** attempt multi-app isolation. The lazy singleton
getters (`_retriever`, `_llm_client`, etc.) remain process-global. The factory
only separates construction and side effects.

## 4. Import-time side-effect inventory

Must be removed from import or made conditional:

```text
check_env()
bootstrap_default_workspace(db_path=DB_PATH)
_load_plugins(app)
```

Must move inside `create_app()` / `register_blueprints()`:

```text
app = Flask(...)
app.config.update(...)
@app.before_request
app.register_blueprint(...)
```

Must stay outside the factory:

```text
run_db_migrations()
reconcile_stale_review_tasks()
model warmup in __main__
```

## 5. Route parity gate

Before refactor, capture:

```text
json_routes = 316
app_routes  = 316
```

After each step, compare:

```text
set(rule, method) before == after
```

Acceptance requires exactly 316, with no new wild routes.

## 6. Contract mode

Contract mode must:

```text
not read DSNs
not bootstrap tenancy
not load plugins
not connect to PostgreSQL
still register all routes and hooks
```

If a route or hook imports a service that needs DSN at import, that is a
blocker to report, not something to hide with fake DSNs.

## 7. CI change after factory

Default CI gains:

```bash
python scripts/validate_arch.py --app contract_app:app
```

No secrets. The release-time check remains:

```bash
python scripts/runtime_contract_check.py
```

for the full app with real DSNs.

## 8. Migration plan

### Step 0 — this document

No code change.

### Step 1 — extract factory, no behavior change

```text
api_server_factory.py
  AppConfig
  create_app()

api_server.py
  app = create_app()
```

Expected: default behavior identical; 1494 tests pass; 316 routes.

### Step 2 — move hooks/blueprints

```text
register_hooks(app)
register_blueprints(app)
```

Keep registration order; compare route set after each move.

### Step 3 — add contract_app.py

```text
app = create_app(contract config)
```

CI route check passes with no DSN.

### Step 4 — full runtime in CI (optional)

Only after a Postgres service or a truly dependency-free app factory is proven.
Do not put production DSNs in CI.

## 9. Risks

```text
plugins may import DB-backed services at import
tenancy bootstrap may be required by auth routes at import
module-level globals mean multiple app instances share state
before_request closure captures env at import
route order and static routes must remain identical
```

Each risk needs a test, not a comment.

## 10. Non-goals

```text
no multi-tenant multi-app runtime
no DSN in GitHub Actions
no behavior change to production startup
no route changes
no business logic changes
```

## 11. Acceptance criteria

```text
import contract_app with no DSN: succeeds
contract_app url_map: 316 routes
api_server:app with deployment env: 316 routes
full test suite: 1494 tests OK
runtime contract: RUNTIME_CONTRACT_OK 316/316
no secrets in CI
```


## Step 3 dependency note

The DSN-free contract app imports the same route modules as the production app.
The minimal import set is recorded in `requirements-contract.txt`; CI installs
only that set, not torch/docling/embedding dependencies. Contract mode also
loads `data_sandbox` because its 12 routes are part of the 316-route contract.
