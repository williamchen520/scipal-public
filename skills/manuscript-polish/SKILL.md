---
name: manuscript-polish
description: Evidence-safe manuscript language polishing. Rewrites one section at a time without changing claims, numbers, citations, or causal strength; returns a diff and a claim/citation risk report.
---

# Manuscript Polish

## When to use

Use when the user asks to:

```text
润色 / polish / edit language
improve clarity or flow
make the writing more concise
adapt a section to a journal's style
```

Do **not** use for:

```text
writing a new paper from scratch
inventing references
changing the scientific claim
re-analysis or re-interpretation
peer-review response letters (separate skill)
```

First version scope:

```text
one section at a time
language_only mode by default
English or Chinese output, following the manuscript
```

## Required inputs

Ask for, or confirm:

```text
manuscript text
target journal / style (optional)
language
mode: language_only | clarity
paper_id (optional, for evidence lookup)
```

If the manuscript text is missing, stop and ask for it. Never polish from memory.

## Hard guardrails

These are non-negotiable:

```text
1. Do not add a citation.
2. Do not remove a citation.
3. Do not renumber citations.
4. Do not change any number, unit, p-value, sample size, or effect size.
5. Do not strengthen causal language.
   associated -> causes        FORBIDDEN
   may -> does                 FORBIDDEN
   preliminary -> demonstrates FORBIDDEN
6. Do not add methods, results, datasets, or limitations.
7. Do not change gene/protein/drug names or abbreviations.
8. Do not silently merge or split claims.
9. Do not "fix" a result you think is wrong; flag it.
10. Do not rewrite text that has no source text.
```

If a requested edit would violate one of these, refuse that edit and explain why.

## Workflow

### 1. Segment

Split the section into paragraphs and sentences. Keep an index for every sentence.

### 2. Protect spans

Before editing, extract and freeze:

```text
citations        [1], [2-4], (Smith et al., 2020), \cite{...}
numbers          integers, decimals, percentages, CIs, p-values
units            mg, mL, μM, kb, Da, hours, etc.
entities         gene/protein/drug/dataset names
hedges           may, might, suggest, associated with, consistent with
```

### 3. Extract claims

For each sentence, record:

```text
claim_id
text
type: observation | method | interpretation | limitation
needs_evidence: true/false
```

### 4. Evidence check

If `paper_id` is available:

```text
mcp__scipal-paper__paper_evidence(paper_id, query)
```

If searching a library:

```text
mcp__scipal-search__search_evidence(query)
```

Use evidence only to check whether the claim is supported.  
Do not paste evidence into the manuscript unless the author asks.

If no evidence is available:

```text
mark the claim as "unverified"
still allow language-only edits
but do not add or strengthen content
```

### 5. Edit

Edit one paragraph at a time.

Allowed:

```text
grammar
word choice
sentence length
transition
redundancy
parallel structure
clarity
```

Not allowed:

```text
new facts
new citations
new numbers
new causal direction
new scope
```

Prefer minimal edits. Do not rewrite for the sake of rewriting.

### 6. Verify

After editing, check:

```text
citation set unchanged
citation order unchanged
numbers unchanged
units unchanged
entities unchanged
hedges preserved
no new claim
no removed limitation
```

If any check fails, revert that paragraph and report it.

## Output contract

Return exactly these sections:

```markdown
## Polished text

<the edited text>

## Edit log

| # | Original | Revised | Type | Reason |
|---|---|---|---|---|

## Claim checks

| Claim | Status | Evidence | Note |
|---|---|---|---|

Status: supported | unverified | contradicted

## Protected spans

- citations: unchanged / changed (explain)
- numbers: unchanged / changed (explain)
- entities: unchanged / changed (explain)

## Risks / questions for author

- ...
```

If nothing needs changing, say so and return the original text unchanged.

## Tool usage

Prefer:

```text
mcp__scipal-paper__paper_evidence
mcp__scipal-search__search_evidence
mcp__scipal-search__verify_answer
```

Rules:

```text
do not cite a paper that is not in the evidence result
do not treat retrieval as proof
do not merge evidence across libraries
```

## Failure behavior

Stop and ask the author when:

```text
the text is missing
the target journal/style is required but unknown
the requested edit changes a claim
the citation set would change
a number looks wrong
the manuscript contains a claim that contradicts its evidence
```

## Mechanical check

Before accepting a polished section, run:

```bash
python scripts/manuscript_polish_check.py --original old.txt --polished new.txt
```

Exit `1` means:

```text
citations changed or reordered
numbers/units changed
hedges removed
causal language strengthened
```

Do not ignore a failed check. Revert the paragraph or ask the author.

This check is language-policing, not evidence audit.  
It does **not** write to the evidence ledger.

## Self-check before final answer

```text
[ ] every edit is in the edit log
[ ] citations unchanged
[ ] numbers unchanged
[ ] no new claim
[ ] no stronger causality
[ ] hedges preserved
[ ] unsupported claims flagged, not rewritten
```

## Example refusal

```text
Requested: "Change 'associated with' to 'causes'."
Response: "That changes causal strength, so I won't make that edit.
I can instead make the surrounding sentence clearer while keeping
'associated with'."
```

---

Example: [Manuscript-Polish-Example.md](../../docs/architecture/Manuscript-Polish-Example.md)
