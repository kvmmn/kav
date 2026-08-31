# The Five Laws of KAV

> The constitution. Every design decision, contract, and line of code must be
> checkable against these. Laws are amended only by explicit ADR.

## Law 1 — The Evaluator Is Sovereign
No KAV component may create, alter, or reinterpret evidence. Measurement belongs
to the host project's evaluator alone.

## Law 2 — One Hypothesis, One Experiment, One Budget
Every experiment is bounded — in scope and cost — before it runs. No unbounded
actions exist in the system.

## Law 3 — No Claim Without Lineage
Every finding traces to specific evidence; every promotion traces to findings.
An untraceable claim is not knowledge; it is noise.

## Law 4 — Memory Is Project-Local
Findings never cross project boundaries by default. Sharing requires an explicit
future law (ADR), never a shortcut.

## Law 5 — Attachment Is Sacred
KAV attaches to any host through a minimal, well-defined adapter contract and API.
It never demands invasive changes to host code.

---
_Accepted: 2026-08-25_
