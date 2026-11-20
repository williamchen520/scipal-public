# SciPal executable contract (pilot)

Static contract only. It does not import the Flask app and does not modify
`ARCHITECTURE.json`.

```bash
python scripts/spec_compile.py --write
python scripts/spec_check.py --check
python -m unittest tests.test_spec_contract
```

The runtime app check is intentionally deferred: importing `api_server` needs
the deployment DSN environment.
