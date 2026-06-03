"""Read CPython's ``python -X importtime`` output.

importtime emits, per imported module, a ``self`` time (its own top-level code) and a
``cumulative`` time. We only ever use ``self``: cumulative over-credits shared grandchildren,
and ``self`` is what actually comes off the hot path when a module stops loading. The
first-importer attribution caveat (a shared leaf is charged to whoever imports it first) is
handled downstream by the removable-cost computation, not here.
"""

from __future__ import annotations

import contextlib
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path


def parse_self_ms(path: str | Path) -> dict[str, float]:
    """Map module name -> self-time in milliseconds. Missing/unreadable log -> empty."""
    out: dict[str, float] = {}
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return out
    for line in text.splitlines():
        if "import time:" not in line or "self [us]" in line:
            continue
        parts = line.split("import time:", 1)[1].split("|")
        if len(parts) < 3:
            continue
        with contextlib.suppress(ValueError):
            out[parts[2].strip()] = int(parts[0].strip()) / 1000
    return out


def aggregate_self_ms(path: str | Path, is_first_party: Callable[[str], bool]) -> dict[str, float]:
    """Self-time aggregated by full module (first-party) or top-level package (external)."""
    agg: dict[str, float] = defaultdict(float)
    for mod, ms in parse_self_ms(path).items():
        key = mod if is_first_party(mod) else mod.split(".")[0]
        agg[key] += ms
    return agg


def compare_logs(
    base_path: str | Path,
    cur_path: str | Path,
    is_first_party: Callable[[str], bool],
) -> tuple[float, float, list[tuple[float, str, str]]]:
    """Diff two importtime logs by aggregated self-cost.

    Returns ``(base_total, cur_total, deltas)`` where each delta is
    ``(delta_ms, state, module)`` and ``state`` is ``REMOVED`` / ``reduced`` / ``GREW``.
    Positive delta = removed/cheaper on current. Per-module deltas for shared libraries are
    noisy (first-importer re-attribution); the net (``base_total - cur_total``) is the
    trustworthy number.
    """
    base = aggregate_self_ms(base_path, is_first_party)
    cur = aggregate_self_ms(cur_path, is_first_party)
    deltas: list[tuple[float, str, str]] = []
    for key in set(base) | set(cur):
        d = base.get(key, 0.0) - cur.get(key, 0.0)
        gone = key in base and key not in cur
        state = "REMOVED" if gone else ("reduced" if d > 0 else "GREW")
        deltas.append((d, state, key))
    deltas.sort(key=lambda x: -abs(x[0]))
    return sum(base.values()), sum(cur.values()), deltas
