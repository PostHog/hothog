"""Render a :class:`~hothog.analysis.Report` (or a compare diff) as a terminal table."""

from __future__ import annotations

from .analysis import Report


def format_report(report: Report) -> str:
    lines: list[str] = []
    lines.append(
        f"\nhot-path self-cost: {report.total_self_ms:.0f}ms total   |   "
        f"pickable (deferrable) ~{report.pickable_ms:.0f}ms; full addressable ~{report.addressable_ms:.0f}ms"
    )
    header = f"{'rank':>4} {'ms':>5} {'cum':>6} {'sites':>5} {'fanout':>6} {'defer?':<14}  module  →  defer at  /  upstream 1-cut"  # noqa: E501
    lines.append(header)
    lines.append("-" * 120)
    cum = 0.0
    for i, r in enumerate(report.rows, 1):
        if not r.blocked:
            cum += r.removable
        where = r.importers[0] if r.importers else ("(leaf)" if r.external else "?")
        more = f" +{len(r.importers) - 1}" if len(r.importers) > 1 else ""
        fo = "-" if r.fanout is None else (f"{r.fanout}*" if r.fanout > len(r.importers) else str(r.fanout))
        cumtxt = f"{cum:6.0f}" if not r.blocked else "    --"
        mark = "  ⟂" if r.blocked else ""
        cuttxt = f"   ⤷ {r.cut}" if r.cut else ""
        lines.append(
            f"{i:>4} {r.removable:5.0f} {cumtxt} {len(r.importers):>5} {fo:>6} {r.defer:<14}  {r.label}  →  {where}{more}{cuttxt}{mark}"  # noqa: E501
        )
    lines.append(
        "⟂ = not cleanly deferrable (baseclass/modscope = used at class/module scope; TEST-only = test artifact)"
    )
    lines.append("⤷ 1-cut@X = dominator: deferring the lib at module X removes the whole subtree in one place")

    if report.excluded:
        lines.append("\nexcluded (not low-hanging):")
        for verdict, count, total, why in report.excluded:
            lines.append(f"  {verdict:<8} {count:>3} items  ~{total:5.0f}ms  ({why})")
    lines.append(
        "\nfanout* = grimp says it's imported beyond the defer sites shown (deferral helps but won't fully contain it)"
    )
    return "\n".join(lines)


def format_compare(base_path, cur_path, base_total, cur_total, deltas, *, top=30, floor=10.0) -> str:
    lines: list[str] = []
    lines.append(f"\ncompare: baseline {base_path} ({base_total:.0f}ms self) vs {cur_path} ({cur_total:.0f}ms self)")
    lines.append(f"net self-cost off hot path: {base_total - cur_total:.0f}ms\n")
    lines.append(f"{'delta_ms':>8}  {'state':<10}  module (+ = removed/cheaper on current, - = grew)")
    lines.append("-" * 90)
    for d, state, mod in deltas[:top]:
        if abs(d) < floor:
            continue
        lines.append(f"{d:8.0f}  {state:<10}  {mod}")
    return "\n".join(lines)
