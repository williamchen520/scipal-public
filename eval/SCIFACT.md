# SciFact evaluation notes

This repository does **not** redistribute the SciFact dataset. Download it from
the official source and cite the original paper.

## Dataset

- Paper: Wadden et al., "Fact or Fiction: Verifying Scientific Claims", EMNLP 2020.
- Dataset: https://github.com/allenai/scifact
- Dataset card / license: https://huggingface.co/datasets/allenai/scifact
- License: **CC BY-NC 2.0** (dataset); the repository code remains AGPL-3.0-or-later.

The dataset license is not replaced by the repository's code license. Do not
use the SciFact data commercially without checking its terms.

## What is retained

Only aggregate metrics and identifier-level rows remain:

```text
eval/results/scifact_300_backends.json   qid + retrieval metrics
eval/results/scifact_systems_300.json    claim_id + first-rank metrics
```

Raw claims, abstracts, gold evidence text, per-claim predictions, and the
SciFact archive are intentionally not included.

## Results (300 claims, abstract-level retrieval)

```text
PG / Chroma / exact recall@10: 0.8669
PG nDCG@10: 0.7458
Chroma nDCG@10: 0.7473
Exact nDCG@10: 0.7458
```

System comparison:

```text
BM25   hit@10 0.8433  nDCG@10 0.7005
Dense  hit@10 0.9500  nDCG@10 0.7901
Hybrid hit@10 0.9167  nDCG@10 0.7612
```

These are abstract-level retrieval numbers, not claim-verification accuracy.

## Reproduction

Use the scripts in `eval/` with a local SciFact download. The exact command and
configuration must be recorded with any reported number; do not infer results
from the retained JSON alone.

## Attribution

If you reuse these results, cite SciFact and this repository. Do not describe
the retained metrics as a redistribution of the SciFact dataset.
