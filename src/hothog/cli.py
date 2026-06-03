"""``hothog`` command-line entry point."""

from __future__ import annotations

import argparse
import sys

from .analysis import Triage
from .config import Config
from .importtime import compare_logs
from .report import format_compare, format_report

CAPTURE_HINT = """\
no importtime self-times found in {log!r}.
capture them first with the SAME entry, e.g.:

    python -X importtime -c "import django; django.setup()" 2> {log}

then re-run hothog (point the positional arg at that log).
"""


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hothog",
        description="Find the imports hogging your hot path — and the single best place to defer each one.",
    )
    p.add_argument(
        "importtime_log",
        nargs="?",
        default="/tmp/hothog.log",
        help="path to a `python -X importtime` log captured with the same entry (default: /tmp/hothog.log)",
    )
    p.add_argument(
        "--entry",
        default="django:setup",
        help='entry to run under the hook, as "module:callable" (default: django:setup)',
    )
    p.add_argument("--django-settings", metavar="MODULE", help="set DJANGO_SETTINGS_MODULE before running the entry")
    p.add_argument(
        "--first-party",
        metavar="PKGS",
        type=_split_csv,
        default=[],
        help="comma-separated top-level packages treated as first-party (drives scoring + grimp)",
    )
    p.add_argument(
        "--test-only",
        metavar="LIBS",
        type=_split_csv,
        default=[],
        help="comma-separated libs that only load under test settings (suppressed as artifacts)",
    )
    p.add_argument(
        "--import",
        dest="import_extra",
        metavar="M1,M2",
        type=_split_csv,
        default=[],
        help="after the entry, also import these under the hook (fold in the first-request path)",
    )
    p.add_argument(
        "--root",
        dest="root_override",
        metavar="M1,M2",
        type=_split_csv,
        default=[],
        help="frame removable-cost/dominators relative to these entry modules instead of the process entry",
    )
    p.add_argument(
        "--env",
        action="append",
        metavar="KEY=VAL",
        default=[],
        help="set an environment variable before the entry (repeatable)",
    )
    p.add_argument("--top", type=int, default=35, help="rows to show (default: 35)")
    p.add_argument(
        "--min-removable", type=float, default=15.0, metavar="MS", help="floor for the pick-list in ms (default: 15.0)"
    )
    p.add_argument("--no-grimp", action="store_true", help="skip the static cross-check (loses fanout + cycle columns)")
    p.add_argument("--compare", metavar="OTHER.log", help="diff two importtime logs and exit")
    return p


def _env_dict(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs:
        key, _, val = pair.partition("=")
        out[key.strip()] = val
    return out


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # The entry we run imports the target project from the current directory, but a console script
    # (unlike `python -c` / `python script.py`) doesn't put CWD on sys.path. Mirror `python -c` so the
    # analysis run matches how the importtime log was captured, and `hothog` works from the repo root.
    if "" not in sys.path:
        sys.path.insert(0, "")
    env = _env_dict(args.env)
    if args.django_settings:  # convenience alias for --env DJANGO_SETTINGS_MODULE=...
        env["DJANGO_SETTINGS_MODULE"] = args.django_settings
    cfg = Config(
        importtime_log=args.importtime_log,
        entry=args.entry,
        import_extra=args.import_extra,
        root_override=args.root_override,
        first_party=tuple(args.first_party),
        test_only=frozenset(args.test_only),
        env=env,
        top=args.top,
        min_removable=args.min_removable,
        use_grimp=not args.no_grimp,
        compare=args.compare,
    )

    if cfg.compare:
        base_total, cur_total, deltas = compare_logs(cfg.compare, cfg.importtime_log, cfg.is_first_party)
        print(format_compare(cfg.compare, cfg.importtime_log, base_total, cur_total, deltas))
        return 0

    report = Triage(cfg).run()
    if report.total_self_ms == 0:
        print(CAPTURE_HINT.format(log=cfg.importtime_log), file=sys.stderr)
        return 1
    report.rows = report.rows[: cfg.top]
    print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
