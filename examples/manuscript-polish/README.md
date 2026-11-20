# Manuscript polish examples

Synthetic examples for the `manuscript-polish` skill.

- `original.txt`
- `polished_safe.txt` -> checker exit 0
- `polished_bad_citation.txt` -> checker exit 1
- `polished_bad_causal.txt` -> checker exit 1

Run:

```bash
python scripts/manuscript_polish_check.py \
  --original examples/manuscript-polish/original.txt \
  --polished examples/manuscript-polish/polished_safe.txt
```

These files are synthetic and are not evidence-ledger entries.
