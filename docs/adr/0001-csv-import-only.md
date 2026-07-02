# ADR-0001

## Title

CSV is an import/export basic format, the only import/export format supported so far

## Status

Accepted

## Context

Many users already maintain their cellar in CSV or Excel.

CSV is convenient for exchanging data.

However it is not suitable as the application's primary storage.

## Decision

CSV will only be used for:

- import
- export

The source of truth is the SQLite database.

## Consequences

CSV files remain simple.

The application can evolve independently from the CSV format.
