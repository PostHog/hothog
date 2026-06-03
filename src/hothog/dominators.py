"""Dominator tree over the runtime import graph (the single-cut-point engine).

"This library is imported in N places — is there *one* upstream place to cut instead?" is
the classic flow-graph dominance question: with a single entry, module ``D`` dominates module
``N`` if every path entry->N passes through ``D``. The dominators of ``N`` form a chain from
the entry down to ``N``; each is a single module where deferring the onward import disconnects
``N``'s whole subtree. For a library that is a *set* of modules, the deepest shared cut-point
is the lowest common ancestor (LCA) of its importers in the dominator tree.

Built with Cooper–Harvey–Kennedy, "A Simple, Fast Dominance Algorithm" (2001) — an iterative
data-flow formulation, near-linear in practice and far smaller than Lengauer–Tarjan.

A single virtual root is added with edges to every real root, so dominance is well-defined for
a multi-root entry. Must be built on the *real* import edges only — package->submodule edges
would create phantom paths that make every package a false dominator.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping

VROOT = "::entry::"


class DominatorTree:
    def __init__(self, succ: Mapping[str, Iterable[str]], roots: Iterable[str]) -> None:
        graph: dict[str, set[str]] = {k: set(v) for k, v in succ.items()}
        graph[VROOT] = set(roots)
        self._idom: dict[str, str] = {VROOT: VROOT}
        self._depth: dict[str, int] = {VROOT: 0}
        self._build(graph)

    def _build(self, graph: dict[str, set[str]]) -> None:
        post, seen, stack = [], {VROOT}, [(VROOT, iter(graph.get(VROOT, ())))]
        while stack:  # iterative postorder from the virtual entry
            node, it = stack[-1]
            for child in it:
                if child not in seen:
                    seen.add(child)
                    stack.append((child, iter(graph.get(child, ()))))
                    break
            else:
                post.append(node)
                stack.pop()
        self._postnum = {n: i for i, n in enumerate(post)}
        rpo = [n for n in reversed(post) if n != VROOT]

        preds: dict[str, set[str]] = defaultdict(set)
        for node, children in graph.items():
            for child in children:
                if node in seen and child in seen:
                    preds[child].add(node)

        idom = self._idom
        changed = True
        while changed:
            changed = False
            for node in rpo:
                new: str | None = None
                for pred in preds[node]:
                    if pred in idom:
                        new = pred if new is None else self._intersect(pred, new)
                if new is not None and idom.get(node) != new:
                    idom[node] = new
                    changed = True

        for node in rpo:  # rpo visits parents before children, so idom depth is known
            if node in idom:
                self._depth[node] = self._depth.get(idom[node], 0) + 1

    def _intersect(self, a: str, b: str) -> str:
        postnum, idom = self._postnum, self._idom
        while a != b:
            while postnum[a] < postnum[b]:
                a = idom[a]
            while postnum[b] < postnum[a]:
                b = idom[b]
        return a

    def lca(self, a: str, b: str) -> str:
        depth, idom = self._depth, self._idom
        while depth.get(a, 0) > depth.get(b, 0):
            a = idom[a]
        while depth.get(b, 0) > depth.get(a, 0):
            b = idom[b]
        while a != b:
            a, b = idom[a], idom[b]
        return a

    def cut_chain(self, importers: Iterable[str]) -> list[str]:
        """Dominator chain (deepest first, up toward the entry) shared by all `importers`.

        Each module on the chain dominates every importer, so deferring the library-ward
        import there removes the whole subtree from the hot path in one place. The caller
        picks the deepest module above the leaf importers.
        """
        present = [m for m in importers if m in self._idom]
        if not present:
            return []
        cp = present[0]
        for m in present[1:]:
            cp = self.lca(cp, m)
        chain: list[str] = []
        node = cp
        while node != VROOT:
            chain.append(node)
            node = self._idom[node]
        return chain
