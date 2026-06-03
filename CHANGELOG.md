# Changelog

All notable changes to hothog are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [0.1.0] - 2026-06-03

Initial public release, extracted and generalized from a real `django.setup()` optimization effort.

### Added
- Ranked, verdict-annotated deferral backlog joining four signals: `-X importtime` self-cost, a
  runtime import DAG (via a `builtins.__import__` hook), removable cost (reachability under node
  deletion), and dominator-tree cut-points — plus AST deferability and a grimp static cross-check.
- Framework-agnostic entry: point at any `"module:callable"` (default `django:setup`) via `--entry`;
  configurable `--first-party` packages and `--test-only` libraries (all were hard-wired before).
- `hothog` console script, `python -m hothog`, and a `Config` / `Triage` / `Report` library API so
  agents can consume the backlog as structured rows.
- `--compare` mode for before/after importtime diffs.
- Pure-core unit tests (importtime, dominators, deferability) and a synthetic end-to-end test
  covering the live import hook, entry resolution, and the full join — no Django/SDKs required.
