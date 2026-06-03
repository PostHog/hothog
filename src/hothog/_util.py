"""Tiny shared helpers."""

from __future__ import annotations


def top_level(module: str) -> str:
    """The top-level package of a dotted module name (``a.b.c`` -> ``a``)."""
    return module.split(".", 1)[0]
