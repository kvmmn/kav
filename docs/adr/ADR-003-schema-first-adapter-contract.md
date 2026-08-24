# ADR-003: Schema-First Adapter Contract

**Status:** Accepted · **Date:** 2026-08-25

## Context
KAV must attach to any host product regardless of language or runtime (Law 5, D-004).
Defining the adapter as native Python interfaces would be faster but limits hosts to Python.

## Decision
The Adapter Contract is defined **first as a language-neutral schema** (JSON Schema,
OpenAPI-describable). Python bindings are generated/implemented second. The four
operations — manifest, search space, run experiment, report result — exist in one
canonical schema; all SDKs are projections of it.

## Consequences
- (+) Any language can implement an adapter; HTTP/gRPC/library transports all possible.
- (+) Single source of truth prevents drift between SDKs.
- (−) Slightly more upfront work than Python-native interfaces.
