# ADR-0002

## Title

SQLite is the primary datastore

## Status

Accepted

## Context

CellarMind is primarily a desktop or a web-based application.

The user should not need a database server.

## Decision

SQLite is the source of truth.

It stores:

- wines
- bottles
- locations
- tastings
- enrichment results

## Consequences

No external infrastructure.

Offline-first.

Simple backups.

Easy portability.
