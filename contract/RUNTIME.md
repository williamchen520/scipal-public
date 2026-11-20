# Runtime contract gate (release only)

Default CI runs the static contract only. Before tagging a release, run the real
Flask app contract in the deployment environment:

```bash
python scripts/runtime_contract_check.py
```

Required env:

```text
SCIPAL_AUTH_DSN
SCIPAL_CORE_DSN
SCIPAL_PG_DSN
```

Exit codes:

```text
0  app routes match ARCHITECTURE.json
1  app/contract mismatch or validator failure
2  required DSNs are missing (not a pass)
```

Do not put deployment DSNs into GitHub Actions for this check. The gate is
manual by design until a dependency-free app factory exists.
