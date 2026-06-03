# hothog

**Find the imports hogging your hot path — and the single best place to defer each one.**

`import` is not free. A single module-level `import` can transitively pull hundreds of modules and seconds of wall-clock, and that cost is paid by **every process that loads the importing module**, whether or not it ever uses the dependency. hothog ranks what to make lazy by the cost that would *actually* come off the path if you deferred it — not the misleading cumulative number — and tells you, per library, whether the cut is even feasible and the one upstream place to make it.

**Built for coding agents.** Cleaning up imports is mechanical, high-volume work — a perfect job for an agent — but only if something else makes the hard calls first: what's worth deferring, what *can* be deferred, and the single place to cut. hothog is that something. It emits a ranked, verdict-annotated backlog (and a structured `Report` API) an agent can execute row by row — see [For coding agents](#for-coding-agents). It was itself built with agentic coding, and generalized from a real `django.setup()` optimization effort; the entry point is configurable, so you can point it at any `"module:callable"`.

```bash
uv add --dev hothog     # then run it with: uv run hothog ...
# or
pip install hothog
```

Install it into the **same environment as the code you're analyzing** — hothog imports your project (and grimp) at runtime to trace the graph. For that reason, don't run it as an isolated tool (`uvx hothog`): the ephemeral environment wouldn't have your project to import.

## Why this exists (the "import tax")

For a web app the cost usually shows up as a slow `django.setup()` / app boot that every process pays: the web server, but also `migrate`, `manage.py shell`, Celery/Temporal workers, and every CI job. The fix is almost always the same — make the heavy import **lazy** (function-local, `TYPE_CHECKING`, a lazy facade, or [PEP 810 explicit lazy imports](https://peps.python.org/pep-0810/) in 3.15+) so it loads only when its code actually runs.

The hard part is not *fixing* a deferral. It is **deciding which imports are worth deferring**:

- A module's **cumulative** import cost is misleading — it includes shared subtrees that other code pulls anyway, so cutting it saves nothing.
- A heavy library imported in *one* place is a clean win; the same library imported in *twenty* places is whack-a-mole.
- Some imports **cannot** be deferred (used as a base class, evaluated at module scope, etc.).
- And sometimes a library used in N leaf places funnels through a **single upstream chokepoint** — one cut removes the whole subtree.

hothog answers those quantitatively instead of by hand. The visualizers (`tuna`, `importtime-waterfall`, treemaps) show you cost; none of them tell you *what to defer, whether you can, or where*.

## Quickstart

hothog runs your entry **twice**: once under `-X importtime` to capture self-cost, once under its own import hook to learn the runtime import graph. So you give it the same entry both times.

```bash
# 1. capture importtime self-cost for your entry
python -X importtime -c "import django; django.setup()" 2> /tmp/hothog.log

# 2. triage it
hothog /tmp/hothog.log --first-party myapp,myproject
```

Run both commands from your project root — hothog puts the working directory on `sys.path` (like `python -c`) so the entry can import your first-party code.

For a non-Django entry, pass `--entry "module:callable"`:

```bash
python -X importtime -c "import myapp.boot; myapp.boot.main()" 2> /tmp/hothog.log
hothog /tmp/hothog.log --entry myapp.boot:main --first-party myapp
```

## What it does

Given a process entry point (default: `django:setup`), it produces a ranked, **actionable backlog** of import deferrals:

- **`removable` ms** — the cost that would *actually* come off the hot path if the module were deferred (not its misleading cumulative cost).
- **`defer?`** — an AST verdict: `easy(N)` / `many(N)` / `BLOCKED:baseclass` / `BLOCKED:modscope` / `annot:lazy` / `TEST-only`.
- **`1-cut@X`** — the single upstream dominator: one place to defer that removes the whole subtree, even when the leaf has many sites.
- **`fanout`** — how widely the library is imported across the whole codebase (does deferring the visible sites actually contain it?).
- A running **cumulative** total, so "lots of small wins" reads as a real number.
- An **excluded** summary (cycles, shared, transitively-pulled) so nothing is silently hidden.

### Output reference

Run against the bundled synthetic app (`tests/fixtures/sample_app`), where two views import a heavy SDK at module scope but only use it inside functions:

```
hot-path self-cost: 59ms total   |   pickable (deferable) ~30ms; full addressable ~66ms
rank    ms    cum sites fanout defer?          module  →  defer at  /  upstream 1-cut
------------------------------------------------------------------------------------------------------------------------
   1    30     30     2      - easy(2)         heavy_sdk  →  sample_app.api.billing +1   ⤷ 1-cut@sample_app.api
   2    32     --     1      - ?               sample_app.api  →  sample_app.boot  ⟂
   6     1     --     1      - BLOCKED:modscope  config_sdk  →  sample_app.api.settings  ⟂

excluded (not low-hanging):
  transit    4 items  ~    0ms  (no direct defer site — defer its parent)
```

Read it: `heavy_sdk` costs 30ms, is imported in 2 places (`billing` + 1 more), is cleanly deferable (`easy(2)`), and instead of editing both sites you can make **one** cut at `sample_app.api`. `config_sdk` is used at module scope, so it's `⟂` (not cleanly deferable as-is). Columns: `*` on fanout means "imported beyond the shown sites"; `⟂` marks not-cleanly-deferable rows.

## For coding agents

Told only "make the heavy imports lazy," an agent flails: it plays whack-a-mole across dozens of call sites, tries to defer things that can't move (base classes, module-scope use), and misses the one upstream chokepoint that would cut a whole subtree in a single edit. hothog removes the judgment from the loop — it makes those decisions and hands back a deterministic worklist where every row maps to a concrete action.

| `defer?` verdict | what the agent should do |
| --- | --- |
| `easy(N)` / `many(N)` | move the import into the N function bodies that use it — or, if a `1-cut@X` is shown, into that one module instead |
| `1-cut@X` | edit **only** module `X`; deferring there disconnects the whole subtree, so leave the leaf sites alone |
| `annot:lazy` | add `from __future__ import annotations` — the uses are type-only |
| `annot:needs-str` | stringize the annotations (or add the `__future__` import) |
| `BLOCKED:baseclass` / `BLOCKED:modscope` / `⟂` | **skip** — used at class/module scope, can't be deferred as-is |

A reliable agent loop:

1. Run hothog and take the top pickable rows (`⟂` rows excluded).
2. For each, apply the deferral at `defer at` / `1-cut@X` per the verdict above.
3. Re-capture importtime and run `--compare` against the old log — the **net** drop confirms the change actually paid off (per-library deltas are noisy; the net is trustworthy).

Consume the backlog as structured data instead of scraping the table:

```python
from hothog import Config, Triage

report = Triage(Config(
    importtime_log="/tmp/hothog.log",
    entry="django:setup",
    first_party=("myapp", "myproject"),
)).run()

for row in report.rows:
    if row.blocked:
        continue  # don't touch ⟂ rows
    # row.label, row.removable (ms), row.defer, row.cut, row.importers
    ...
```

One call the agent should *not* make blindly: on a long-lived web server, don't let a deferral land on a user's request path — see [Applications](#applications) for defer-vs-warmup. hothog finds *where* a cut is possible; whether to take it is policy.

## How it works (the science)

The tool joins **four** signals, each individually incomplete. The interesting part is *why* you need all four.

### 1. Import cost — `-X importtime`

CPython's `python -X importtime` emits, for every imported module, a **self** time (time in that module's own top-level code) and a **cumulative** time (self + all children it triggered).

The catch is **first-importer attribution**: a shared leaf (e.g. `pandas`) is charged to whichever module imports it *first*. So a module can show a large `self` time that is really the first-import cost of a shared dependency — deferring that module just re-attributes the cost elsewhere and saves nothing. This is the central reason cumulative/self cost cannot be trusted on its own, and motivates signal #3.

### 2. The runtime import DAG — hooking `builtins.__import__`

To know *who imports what at this entry point*, the tool installs a hook on `builtins.__import__` for the duration of the entry call. The key trick: `__import__`'s `globals` argument **is the importing module's namespace**, so `globals["__name__"]` gives the direct importer for free — every edge, with attribution, no stack walking.

Two correctness details that matter:

- **Relative imports.** `from .sub import x` calls `__import__("sub", ..., level=1)` with the *unqualified* name, which won't match the fully-qualified module path. The hook resolves them with `importlib.util.resolve_name("." * level + name, package)`. Without this, relative-import edges are silently dropped and the graph is disconnected.
- **The `importlib.import_module` blind spot.** Dynamic imports (e.g. Django's app loading) go through `importlib._bootstrap`, *not* `builtins.__import__`, so the hook can't see them. Neither can a static parser (it's a function call, not an `import` statement). This is handled structurally in signal #4 (effective-entry rooting); it is a genuine limitation, documented in [Caveats](#caveats--limitations).

The DAG is built at **import-statement granularity** over the modules that actually loaded. A second, package-augmented copy (parent-package → submodule edges) is kept for reachability only — see why it must *not* be used for dominators in signal #4.

### 3. Removable cost — reachability under node deletion

This is the heart of the tool, and the fix for the attribution problem in #1.

> **removable(M)** = the total `self` time of every module that becomes **unreachable from the entry roots** once `M` is removed from the graph.

Concretely: do a reachability traversal from the roots; do it again with `M` blocked; the set difference is "everything that only existed because of `M`," and its summed self-cost is the true saving. Shared subtrees (reachable by another path) drop out automatically — so the "looks like 200 ms, but it's all shared `boto3`/`dns`" trap and the `pandas`-under-a-wrapper trap both resolve correctly.

This is a per-node **graph reachability** computation (`O(V + E)` per candidate); ranking by `removable` instead of cumulative is what makes the backlog trustworthy.

### 4. The single cut-point — dominator trees

"This library is imported in 6 places — is there *one* upstream place to cut instead?" is exactly the **dominator** question from compiler/flow-graph theory:

> With a single entry, module **D dominates** module **N** if every path from the entry to N passes through D.

The dominators of N form a chain from the entry down to N; each is a single module where deferring the onward import disconnects N's whole subtree. For a library that is a *set* of modules (e.g. `modal` and its submodules), the deepest common cut-point is the **lowest common ancestor (LCA)** of the importer set in the dominator tree.

The tool builds the dominator tree with **Cooper–Harvey–Kennedy** ("A Simple, Fast Dominance Algorithm") — an iterative data-flow formulation that is near-linear in practice and ~40 lines, rather than the heavier Lengauer–Tarjan. Three modelling decisions are load-bearing:

- **Real-import graph only.** Dominators are computed on the pure `__import__`-statement edges, *not* the package-augmented graph — a synthetic "package reaches all its submodules" edge creates phantom paths that make every package a false dominator and hide the real chokepoint.
- **Virtual entry.** A single virtual root is added with edges to all real roots, so dominance is well-defined for a multi-root entry.
- **Effective-entry rooting.** Because dynamic imports (signal #2's blind spot) leave some loaded modules with no captured importer, every such module is treated as an additional entry. This keeps the *static-import subgraph* connected, so dominators are well-defined over the part we can actually see — which is the part where a deferral would live anyway.

### 5. Deferability — AST classification

`removable` says *how much* a cut is worth; this says *whether it's feasible and how hard*. For each heavy library, the tool parses its importer module(s) with the `ast` module and classifies every use of the bound name by syntactic context:

| usage context | verdict | meaning |
| --- | --- | --- |
| function/method body only | `easy(N)` / `many(N)` | deferrable; N = number of call sites |
| class base list (`class X(Lib)`) | `BLOCKED:baseclass` | needed at class-definition time |
| module top-level (non-annotation) | `BLOCKED:modscope` | evaluated at import; not deferrable as-is |
| annotations only | `annot:lazy` / `annot:needs-str` | deferrable via `from __future__ import annotations` / string refs |

It also tracks `from __future__ import annotations` per file (which makes annotation uses lazy) and a configurable test-only set (`--test-only`, libraries that load only under test settings, to avoid false positives).

This is the part neither a type-checker LSP nor an import-grapher gives directly: it is an *intra-module usage* question, and `ast` answers it in one pass over the one file.

### 6. Static cross-check — `grimp`

[`grimp`](https://github.com/seddonym/grimp) builds the **static** import graph of the whole codebase (all `import` statements as written, including in code paths this run didn't take). It contributes two things the runtime view can't:

- **fan-out** — how many modules import a library *anywhere*. If that exceeds the sites you'd defer, the library "turns up elsewhere": deferring the visible sites helps this entry but won't fully contain it.
- **cycles** — a module that (transitively) imports one of its own importers. Deferring something inside an import cycle can unmask or merely relocate it; the tool flags these `RISKY` so they aren't mistaken for low-hanging fruit.

`grimp` *cannot* answer the cut-point question itself — it is a static, whole-program graph (so a library imported in one runtime path looks reachable a thousand ways), and it exposes no dominator/path-enumeration API. Runtime DAG for the cut-point, static graph for the blast radius. Different graphs, different questions. (Skip it with `--no-grimp`.)

### 7. Verdict taxonomy

| verdict | pickable | meaning |
| --- | --- | --- |
| `CLEAN` | yes | 1 defer site, real removable cost |
| `SLIVER` | yes | 2–3 defer sites |
| `RISKY` | no | in an import cycle — untangle first |
| `SHARED` | no | imported widely — whack-a-mole |
| `transit` | no | no direct defer site — defer its parent |

### 8. Compare mode

Given two `importtime` logs (e.g. before/after a change, or two different entry points), `--compare` reports the per-module self-cost delta — what a change removed, and what re-attributed. The **net** is the trustworthy number; per-module deltas for shared libraries are noisy by the same first-importer mechanism as #1.

## Applications

- **Speed up process startup** — the original use case. Rank what to defer off `django.setup()` (or any framework boot) so short-lived and frequent processes stop paying for code they never run.
- **Audit a "first request" / lazy-built path** — point `--import` / `--root` at a lazily-built object (e.g. an API router built on first request) to see what that build pulls.
- **Decide defer vs. warmup — a policy, not an output.** The tool finds *where* an import can be moved off a path. Whether you *should* depends on the process:
  - short-lived / frequent / cold-start-sensitive (CLI, `migrate`, shell, workers, serverless): **deferral is a pure win**.
  - long-lived web server: you often *don't* want a deferral to land on the first request to an endpoint (a user pays the latency). Prefer to keep the import eager **or** pre-import it in an explicit startup **warmup** before the server accepts traffic, so the cost is paid once, off the request path.

  The tool gives you the cut list and the leverage; the eager-vs-defer-vs-warmup decision is yours (or your agent's, with this caveat in its prompt).

## Usage

```
hothog [IMPORTTIME_LOG] [options]
```

| option | meaning |
| --- | --- |
| `--entry MODULE:CALLABLE` | entry to run under the hook (default `django:setup`) |
| `--first-party PKGS` | comma-separated top-level packages scored individually (drives scoring + grimp) |
| `--django-settings MODULE` | set `DJANGO_SETTINGS_MODULE` before the entry |
| `--env KEY=VAL` | set an env var before the entry (repeatable) |
| `--test-only LIBS` | libs that only load under test settings (suppressed as artifacts) |
| `--import M1,M2` | after the entry, also import these under the hook (fold in the first-request path) |
| `--root M1,M2` | frame `removable`/dominators relative to these entry modules |
| `--top N` | rows to show (default 35) |
| `--min-removable MS` | floor for the pick-list (default 15.0) |
| `--no-grimp` | skip the static cross-check (faster; loses fan-out + cycle columns) |
| `--compare OTHER.log` | diff two importtime logs and exit |

The library API (`Config` / `Triage` / `Report`) is shown under [For coding agents](#for-coding-agents).

### The original PostHog invocation

The monorepo it came from runs it like this — a worked example of the flags:

```bash
DJANGO_SETTINGS_MODULE=posthog.settings TEST=1 \
  python -X importtime -c "import django; django.setup()" 2> /tmp/hothog.log
hothog /tmp/hothog.log \
  --django-settings posthog.settings --env TEST=1 \
  --first-party posthog,products,ee,common --test-only fakeredis
```

## Caveats & limitations

- **`importlib.import_module` is invisible to the hook.** Dynamically loaded modules (e.g. Django app loading) have no captured importer; the tool compensates by treating them as effective entry points for dominator analysis, but the dominator chain *above* such a module cannot be reconstructed. Capturing these (wrapping `importlib.import_module` / `_bootstrap._gcd_import`) is future work — and even then the "logical" importer of a dynamic load is ambiguous.
- **First-importer re-attribution noise.** `removable` for a module adjacent to a shared heavy leaf can vary run-to-run depending on which module imports the shared leaf first. The clean single-owner wins are stable; the shared-adjacent ones are noisy. Averaging over several runs would smooth this (TBD).
- **Test-mode artifacts.** If the entry runs under test settings, some libraries load that wouldn't in production (e.g. an in-memory fake for a datastore). `--test-only` suppresses the obvious ones; the general case is unsolved.
- **Function-level imports in the static graph.** `grimp` records imports wherever they appear, so an already-deferred import still shows as a static edge — relevant only to the `fanout` interpretation, not to `removable`.
- **Single language / single process.** This measures one Python process's import graph. No threads, no subprocesses, no native-extension internals.

## Algorithms & references

- Cooper, Harvey, Kennedy — *A Simple, Fast Dominance Algorithm* (2001). The iterative dominator-tree construction used here.
- Lengauer, Tarjan — *A Fast Algorithm for Finding Dominators in a Flowgraph* (1979). The classic near-linear alternative; not used (CHK is simpler and fast enough).
- Lowest common ancestor in a tree — used to reduce a multi-module library to a single cut-point.
- Graph reachability under vertex deletion — the `removable` cost.
- CPython `-X importtime` — import cost measurement.
- [`grimp`](https://github.com/seddonym/grimp) — static import graph, fan-out, cycle detection.

## Development

```bash
uv run --extra dev pytest        # tests (pure cores + a synthetic end-to-end run)
uvx ruff check . && uvx ruff format --check .
uv run --extra dev mypy
```

The pure cores (`importtime`, `dominators`, `deferability`) are unit-tested without Django or grimp; `tests/test_end_to_end.py` drives the live import hook, entry resolution, and the full join against a synthetic app under `tests/fixtures/`.

## Roadmap

- Capture `importlib.import_module` edges to close the dynamic-import blind spot.
- Multi-run averaging to denoise first-importer re-attribution.
- JSON output mode (a second machine-readable surface alongside the `Report` API).
- A realistic Django + DRF + heavy-SDK example app for the docs.

## License

MIT — see [LICENSE](LICENSE).
