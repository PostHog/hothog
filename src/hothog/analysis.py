"""The live triage: hook the import system, run the entry, join the four signals.

This is the part that needs a real process — it installs a hook on ``builtins.__import__``
for the duration of the entry call, builds the runtime import DAG (the hook's ``globals``
argument *is* the importing module's namespace, so ``globals["__name__"]`` gives the direct
importer for free), then joins it with importtime self-cost, a grimp static graph, the
dominator tree, and AST deferability into a ranked, actionable backlog of deferrals.
"""

from __future__ import annotations

import builtins
import contextlib
import importlib.util
import os
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .deferability import deferability
from .dominators import DominatorTree
from .importtime import parse_self_ms

STDLIB = set(getattr(sys, "stdlib_module_names", set())) | {"__future__", "_io"}


@dataclass
class Row:
    """One library in the backlog. `removable` is the real saving; `cut` is the 1-place defer."""

    removable: float
    label: str
    importers: list[str]
    external: bool
    fanout: int | None
    defer: str
    blocked: bool
    cut: str = ""


@dataclass
class Report:
    total_self_ms: float
    pickable_ms: float
    addressable_ms: float
    rows: list[Row] = field(default_factory=list)
    excluded: list[tuple[str, int, float, str]] = field(default_factory=list)


class Triage:
    """Run a single triage against the configured entry point."""

    def __init__(self, config: Config) -> None:
        self.cfg = config

    def run(self) -> Report:
        self._apply_env()
        edges = self._capture_entry()
        loaded = set(sys.modules)
        self.self_ms = parse_self_ms(self.cfg.importtime_log)

        self.graph, imp_graph, rev = self._build_graphs(edges, loaded)
        self.roots = self._roots(edges, loaded)
        self.base = self._reachable(frozenset())
        self.dom = self._dominator_tree(imp_graph, loaded)
        self.grimp = self._build_grimp()

        scored = self._score(loaded, rev)
        return self._assemble(scored)

    # -- entry & hook ---------------------------------------------------------------------------

    def _apply_env(self) -> None:
        if self.cfg.django_settings:
            os.environ["DJANGO_SETTINGS_MODULE"] = self.cfg.django_settings
        os.environ.update(self.cfg.env)

    def _capture_entry(self) -> dict[str, set[str]]:
        """Install the import hook, run the entry callable, restore. Returns importer->imported edges."""
        edges: dict[str, set[str]] = defaultdict(set)
        real = builtins.__import__

        def hook(name, g=None, loc=None, fromlist=(), level=0):
            importer = (g or {}).get("__name__", "__main__")
            base = name
            if level:  # relative import: __import__ gets the UNqualified name; resolve the full path
                pkg = (g or {}).get("__package__") or (importer.rsplit(".", 1)[0] if "." in importer else importer)
                try:
                    base = importlib.util.resolve_name("." * level + name, pkg)
                except (ImportError, ValueError):
                    base = name
            edges[importer].add(base)
            for f in fromlist or ():
                edges[importer].add(f"{base}.{f}")
            return real(name, g, loc, fromlist, level)

        builtins.__import__ = hook
        try:
            mod_name, _, attr = self.cfg.entry.partition(":")
            hook(mod_name, {"__name__": "__main__"})  # real import statement -> captured edge
            module = sys.modules.get(mod_name)
            if attr and module is not None:
                getattr(module, attr)()
            for extra in self.cfg.import_extra:  # e.g. a lazy router — fold the first-request path in
                try:
                    hook(extra, {"__name__": "__main__"})
                except Exception:  # noqa: BLE001
                    print(f"(could not import {extra})", file=sys.stderr)
        finally:
            builtins.__import__ = real
        return edges

    # -- graphs ---------------------------------------------------------------------------------

    def _build_graphs(self, edges, loaded):
        graph: dict[str, set[str]] = defaultdict(set)  # real edges + package->submodule (reachability)
        imp_graph: dict[str, set[str]] = defaultdict(set)  # ONLY real import edges (for dominators)
        rev: dict[str, set[str]] = defaultdict(set)  # imported -> {first-party importers}
        for imp, tgts in edges.items():
            for t in tgts:
                if t in loaded and t != imp:
                    graph[imp].add(t)
                    imp_graph[imp].add(t)
                    if self.cfg.is_first_party(imp):
                        rev[t].add(imp)
        for m in loaded:
            if "." in m:
                parent = m.rsplit(".", 1)[0]
                if parent in loaded:
                    graph[parent].add(m)
        return graph, imp_graph, rev

    def _roots(self, edges, loaded) -> set[str]:
        if self.cfg.root_override:
            return {m for m in self.cfg.root_override if m in loaded}
        seeds = {t for t in edges.get("__main__", set()) if t in loaded} | {self.cfg.entry_module}
        return seeds & loaded

    def _reachable(self, blocked) -> set[str]:
        seen: set[str] = set()
        dq = deque(r for r in self.roots if r not in blocked)
        while dq:
            n = dq.popleft()
            if n in seen:
                continue
            seen.add(n)
            for c in self.graph.get(n, ()):
                if c not in seen and c not in blocked:
                    dq.append(c)
        return seen

    def _removable(self, block_set) -> float:
        return sum(self.self_ms.get(x, 0) for x in (self.base - self._reachable(block_set)))

    def _dominator_tree(self, imp_graph, loaded) -> DominatorTree:
        # The hook can't see dynamic (importlib.import_module) app loading, so some first-party modules
        # have no captured importer. Treat every loaded module with no real first-party importer as an
        # entry — this keeps the static-import subgraph connected so dominance is well-defined.
        has_importer = {v for u, vs in imp_graph.items() if self.cfg.is_first_party(u) for v in vs}
        dom_roots = (set(self.roots) | {m for m in loaded if m not in has_importer}) & (loaded | set(self.roots))
        return DominatorTree(imp_graph, dom_roots)

    # -- grimp static cross-check ---------------------------------------------------------------

    def _build_grimp(self):
        if not self.cfg.use_grimp or not self.cfg.first_party:
            return None
        try:
            import grimp

            return grimp.build_graph(*self.cfg.first_party, include_external_packages=True)
        except Exception as e:  # noqa: BLE001
            print(f"(grimp unavailable: {e})", file=sys.stderr)
            return None

    def _fanout_and_cycle(self, name, external):
        if self.grimp is None:
            return None, None
        try:
            fanout = len(self.grimp.find_modules_that_directly_import(name))
        except Exception:  # noqa: BLE001
            fanout = None
        cycle = None
        if not external:
            try:
                cycle = bool(self.grimp.find_upstream_modules(name) & self.grimp.find_downstream_modules(name))
            except Exception:  # noqa: BLE001
                cycle = None
        return fanout, cycle

    # -- scoring & assembly ---------------------------------------------------------------------

    def _candidates(self, loaded, rev):
        """First-party modules scored individually; external libs aggregated by top-level package."""
        candidates = []  # (label, block_set, importers, external)
        ext_groups: dict[str, set[str]] = defaultdict(set)
        for m in loaded:
            tl = m.split(".")[0]
            if self.cfg.is_first_party(m):
                if self.self_ms.get(m, 0) >= 1 or m in rev:
                    candidates.append((m, {m}, sorted(rev.get(m, ())), False))
            elif tl not in STDLIB:
                ext_groups[tl].add(m)
        for tl, mods in ext_groups.items():
            importers = sorted({c for mm in mods for c in rev.get(mm, ())})
            candidates.append((tl, mods, importers, True))
        return candidates

    def _score(self, loaded, rev):
        scored = []
        for label, block_set, importers, external in self._candidates(loaded, rev):
            rm = self._removable(block_set)
            if rm < self.cfg.min_removable:
                continue
            fanout, cycle = self._fanout_and_cycle(label, external)
            scored.append((rm, label, importers, external, fanout, cycle))
        scored.sort(key=lambda r: -r[0])
        return scored

    @staticmethod
    def _verdict(importers, cycle) -> tuple[str, bool]:
        n = len(importers)
        if cycle:
            return "RISKY", False  # import cycle — untangle first, not low-hanging
        if n == 0:
            return "transit", False  # no first-party defer site; defer its parent
        if n == 1:
            return "CLEAN", True
        if n <= 3:
            return "SLIVER", True
        return "SHARED", False  # imported widely — whack-a-mole

    def _sources_for(self, modules) -> list[str]:
        out = []
        for m in modules:
            mod = sys.modules.get(m)
            path = getattr(mod, "__file__", None)
            if path and path.endswith(".py"):
                with contextlib.suppress(OSError):
                    out.append(Path(path).read_text(encoding="utf-8"))
        return out

    def _assemble(self, scored) -> Report:
        addressable = 0.0
        excluded: dict[str, list] = defaultdict(lambda: [0, 0.0])
        rows: list[Row] = []
        for rm, label, importers, external, fanout, cycle in scored:
            verdict, ok = self._verdict(importers, cycle)
            if not ok:
                excluded[verdict][0] += 1
                excluded[verdict][1] += rm
                continue
            addressable += rm
            defer, _sites = deferability(label, self._sources_for(importers), test_only=self.cfg.test_only)
            blocked = defer.startswith("BLOCKED") or defer in ("TEST-only", "?")
            cut = ""
            if len(importers) > 1 or defer.startswith("many"):
                chain = self.dom.cut_chain(importers)
                dom = next((c for c in chain if c not in importers), None)
                if dom:
                    cut = f"1-cut@{dom}"
            rows.append(Row(rm, label, importers, external, fanout, defer, blocked, cut))

        rows.sort(key=lambda r: (r.blocked, -r.removable))  # blocked sink below clean, else by payoff
        pickable = sum(r.removable for r in rows if not r.blocked)
        reasons = {
            "RISKY": "import cycle — untangle first",
            "SHARED": "imported widely — whack-a-mole",
            "transit": "no direct defer site — defer its parent",
        }
        excluded_rows = sorted(
            ((v, c, tot, reasons.get(v, "")) for v, (c, tot) in excluded.items()),
            key=lambda x: -x[2],
        )
        return Report(
            total_self_ms=sum(self.self_ms.values()),
            pickable_ms=pickable,
            addressable_ms=addressable,
            rows=rows,
            excluded=excluded_rows,
        )
