"""AST classification: *can* a library be deferred at its importer, and how hard?

removable cost says how much a cut is worth; this says whether it's feasible. For each heavy
library we parse the importer module(s) and classify every use of the bound name by syntactic
context — function body (deferrable), class base (needed at class-definition time), module
top-level (evaluated at import), or annotation (deferrable via string refs / ``from __future__
import annotations``). This is an intra-module question a type-checker or import-grapher won't
answer directly; ``ast`` answers it in one pass over the one file.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable


def bound_names(tree: ast.AST, lib: str) -> set[str]:
    """Local names that `lib` is bound to in this module (handles ``as`` aliases)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == lib or a.name.split(".")[0] == lib:
                    names.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == lib or mod.split(".")[0] == lib:
                for a in node.names:
                    names.add(a.asname or a.name)
    return names


def classify(tree: ast.AST, names: set[str]) -> dict:
    """Tally how `names` are used: base-class, module-scope, annotation, or in which functions."""
    r: dict = {"base": 0, "mod": 0, "ann": 0, "fns": set()}

    def walk(n, infn, inann, inbase, fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in names:
            if inbase:
                r["base"] += 1
            elif inann:
                r["ann"] += 1
            elif infn:
                r["fns"].add(fn)
            else:
                r["mod"] += 1
            return
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in n.decorator_list:
                walk(d, infn, inann, inbase, fn)
            allargs = [*n.args.posonlyargs, *n.args.args, *n.args.kwonlyargs, n.args.vararg, n.args.kwarg]
            for a in allargs:
                if a and a.annotation:
                    walk(a.annotation, infn, True, False, fn)
            if n.returns:
                walk(n.returns, infn, True, False, fn)
            for d in [*n.args.defaults, *n.args.kw_defaults]:
                if d:
                    walk(d, infn, inann, inbase, fn)
            for s in n.body:
                walk(s, True, False, False, n.name)
            return
        if isinstance(n, ast.ClassDef):
            for d in n.decorator_list:
                walk(d, infn, inann, inbase, fn)
            for b in n.bases:
                walk(b, infn, False, True, fn)
            for s in n.body:
                walk(s, infn, inann, False, fn)
            return
        if isinstance(n, ast.AnnAssign):
            walk(n.annotation, infn, True, False, fn)
            if n.value:
                walk(n.value, infn, inann, inbase, fn)
            return
        for c in ast.iter_child_nodes(n):
            walk(c, infn, inann, inbase, fn)

    walk(tree, False, False, False, None)
    return r


def _has_future_annotations(tree: ast.Module) -> bool:
    return any(
        isinstance(n, ast.ImportFrom) and n.module == "__future__" and any(a.name == "annotations" for a in n.names)
        for n in tree.body
    )


def deferability(lib: str, sources: Iterable[str], *, test_only: frozenset[str] = frozenset()) -> tuple[str, int]:
    """Worst-case deferability verdict for `lib` across the given importer source strings.

    Returns ``(verdict, n_call_sites)``. Verdicts:
    ``easy(N)`` / ``many(N)`` (deferrable, N call sites), ``BLOCKED:baseclass``,
    ``BLOCKED:modscope``, ``annot:lazy`` / ``annot:needs-str``, ``TEST-only``, or ``?``.
    """
    if lib in test_only:
        return "TEST-only", 0
    total = {"base": 0, "mod": 0, "ann": 0, "fns": 0}
    future = True
    for source in sources:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        names = bound_names(tree, lib)
        if not names:
            continue
        future = future and _has_future_annotations(tree)
        c = classify(tree, names)
        total["base"] += c["base"]
        total["mod"] += c["mod"]
        total["ann"] += c["ann"]
        total["fns"] += len(c["fns"])
    if total["base"]:
        return "BLOCKED:baseclass", total["fns"]
    if total["mod"]:
        return "BLOCKED:modscope", total["fns"]
    if total["fns"] == 0 and total["ann"]:
        return ("annot:lazy" if future else "annot:needs-str"), 0
    n = total["fns"]
    if n == 0:
        return "?", 0
    return (f"easy({n})" if n <= 2 else f"many({n})"), n
