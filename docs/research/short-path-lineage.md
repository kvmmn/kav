# Short-Path Web Search and v0.1 Lineage

_Method note — research craft, not a contract change. Date: 2026-08-31_

## Hypothesis

Short-path web search (keywords, posts, papers, URLs gathered before or beside a host trial) **cannot** be stored as a `ResearchFinding` under the current v0.1 contracts without fabricating lineage or smuggling unbounded fields.

This note records what was checked, what is missing, and a provisional operator shape that satisfies Law 3 without pretending to be an `ExperimentSpec`.

## Files checked (lineage)

| File | Relevant facts |
|------|----------------|
| `contracts/research-finding.schema.json` | **Required:** `finding_id`, `project_id`, `experiment_id`, `kind`, `statement`, `confidence`, `created_at`. **`additionalProperties: false`.** No `sources`, `url`, or citation property. `experiment_id` is described as “The experiment whose evidence produced this finding. Law 3: no claim without lineage.” |
| `contracts/search-space.schema.json` | Declares **typed host parameters** (`number`, `integer`, `categorical`, `boolean`) with bounded `range` or `set` domains. A point in this space is a host configuration — not a web query, keyword list, or URL. |
| `contracts/experiment-spec.schema.json` | Lineage anchor: `experiment_id` (required). Issues bounded parameter **changes** against `SearchSpace`; requires `hypothesis_id`, `changes`, `budget`, `reproducibility`. |
| `contracts/experiment-result.schema.json` | Lineage anchor: `experiment_id` (required). Host-measured `evidence`; artifact refs are host storage URIs, not bibliographic citations. |
| `contracts/project-manifest.schema.json` | Host introduction only; no research-craft or citation fields. |

No file under `contracts/` defines `url`, `source`, or `citation` (grep over the directory, 2026-08-31).

**Verdict:** The hypothesis holds. A short-path search result is not evidence from a host experiment; forcing it into `ResearchFinding` would require a synthetic `experiment_id` and would drop retrievable citations because the schema forbids extra properties.

## What is missing in v0.1

1. **A lineage anchor for pre-experiment discovery.** `ResearchFinding` binds only to `experiment_id`. Short-path search precedes or informs hypothesis formation; it is not output of a completed trial.
2. **A citation surface.** Operators need durable `{url, title, …}` records. v0.1 findings carry a textual `statement` but no structured provenance for external references.
3. **A bounded search-space analogue for the open web.** `SearchSpace` models host-config parameters. Web search is unbounded unless the host (or operator policy) caps queries, domains, and result counts — outside current contract scope.

## Proposed short-path result shape (operators, not v0.1)

Until a contract ADR exists, operators may record short-path output **outside** the five v0.1 schemas, with explicit lineage to the **files and retrieval act**, not to a fabricated experiment:

```json
{
  "short_path_id": "sp-20260831-numerai-baseline",
  "project_id": "numerai-demo",
  "query": "Numerai feature neutralization baseline 2024",
  "retrieved_at": "2026-08-31T19:00:00Z",
  "policy": {
    "max_results": 10,
    "allowed_domains": ["arxiv.org", "forum.numer.ai", "docs.numer.ai"]
  },
  "results": [
    {
      "url": "https://forum.numer.ai/t/example-thread",
      "title": "Example thread title",
      "why_it_counts": "States the platform’s correlation metric and validation split — informs hypothesis wording only.",
      "retrieved_at": "2026-08-31T19:00:05Z"
    }
  ],
  "lineage": {
    "method": "docs/research/short-path-lineage.md",
    "contracts_version": "0.1",
    "note": "Not a ResearchFinding. No experiment_id."
  }
}
```

**Law 3 compliance:** Each listed result names a retrievable URL, retrieval time, and why it matters. The record cites this method note and the contract version it was checked against — traceable without claiming host measurement.

**Not an ExperimentSpec:** No `changes`, `budget`, or host `reproducibility` block. Promotion to knowledge still requires a bounded experiment and a host `ExperimentResult`.

## Explicit non-decision

**This PR does not change any JSON Schema under `contracts/`.** A first-class short-path or citation contract belongs in a future ADR (schema version bump, validation rules, and host/operator acceptance criteria).

## How success is graded later (Law 1)

This document does not grade its own hypothesis. Under Law 1, the **host’s evaluator** (or an operator acting as sovereign reviewer for research-craft) decides whether a short-path record was useful:

- Was it accepted into project-local context before experiments were specified?
- Do cited URLs still resolve at review time?
- Did subsequent `ExperimentSpec` / `ResearchFinding` records reference real trials, not search snippets, as evidence?

Failed resolution or unused citations are operational signal, not schema errors.

## Five Laws check

| Law | This cycle |
|-----|------------|
| **L1 — Evaluator is sovereign** | Host/operator still measures; search hits are not evidence. |
| **L2 — Bounded** | Docs-only; proposed operator shape includes explicit caps (`max_results`, domain allowlist). |
| **L3 — Lineage** | This note cites contract files; proposed shape links URL + `retrieved_at` + rationale. |
| **L4 — Project-local** | `project_id` scopes short-path records; no cross-project finding export. |
| **L5 — Attachment** | No host adapter or SDK change; attachment contract untouched. |
