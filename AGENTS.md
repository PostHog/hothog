# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`hothog` ranks which imports to defer off a Python process's hot path. See `README.md` for the
full "why" and the four-signal science — this file is the operational shortcut.

## Commands

```bash
uv run --extra dev pytest                              # all tests
uv run --no-project --with pytest pytest               # pure cores only, fast (no grimp install)
uv run --extra dev pytest tests/test_dominators.py::test_diamond_idom_is_shared_entry   # single test
uvx ruff check . && uvx ruff format --check .          # lint + format (CI gates on both)
uv run --extra dev mypy                                # types
uv build                                               # sdist + wheel
```

CI (`.github/workflows/ci.yml`) runs ruff + mypy + a pytest matrix (3.10–3.13). Publishing is
tag-driven via `publish.yml` (PyPI trusted publishing / OIDC, no tokens) — see `README.md` → reserve/publish steps.

## Architecture

The engine is `analysis.Triage.run()`, which joins four signals (detailed in `README.md` → "How it works"):

- **Two runs of the same entry.** Cost comes from a separately-captured `-X importtime` log (passed as
  the positional arg); the runtime import graph comes from re-running the entry **in-process** under a
  `builtins.__import__` hook. The CLI/`Config.entry` is a `"module:callable"` string (default `django:setup`).
- **Two graphs, used for different things.** `graph` (real edges **plus** package→submodule edges) drives
  reachability and `removable` cost. `imp_graph` (real import-statement edges **only**) drives the dominator
  tree. Never feed package edges to dominators — they create phantom dominators and hide the real cut-point.
- **`removable` is the trustworthy metric** — self-time that becomes unreachable when a node is deleted, *not*
  cumulative cost (which mis-attributes shared subtrees).

### Module split is load-bearing for tests

The pure cores — `importtime`, `dominators`, `deferability` — are deliberately free of any live-import or
grimp dependency, so they're unit-tested on synthetic inputs without Django/grimp. The live path
(`analysis`, the hook + entry + join) is covered by `tests/test_end_to_end.py` against a synthetic app in
`tests/fixtures/` (a first-party package + two fake SDKs). Keep that boundary when adding code: anything
that needs `sys.modules`/grimp lives in `analysis`, anything graph- or AST-pure stays in its own module.

### No codebase-specific hardcodes

Everything project-specific (entry, first-party packages, test-only libs, env) lives in `Config`. The tool
must stay framework-agnostic — don't reintroduce hardcoded settings modules or package names.
