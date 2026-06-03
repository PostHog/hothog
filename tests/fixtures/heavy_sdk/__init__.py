"""A stand-in for a heavy third-party SDK: does real work at import time so it has self-cost."""

_total = 0
for _i in range(500_000):  # ~tens of ms of import-time work, so it shows measurable self-time
    _total += _i


def charge(amount):
    return amount


def report():
    return "ok"
