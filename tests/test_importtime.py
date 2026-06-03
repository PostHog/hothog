import pytest

from hothog.importtime import aggregate_self_ms, compare_logs, parse_self_ms

# A realistic `python -X importtime` fragment: "self us | cumulative us | name".
SAMPLE = """\
import time: self [us] | cumulative | imported package
import time:        50 |         50 |   _io
import time:       300 |        350 |   os
import time:      1500 |       1850 |   mypkg.heavy
import time:       250 |       2100 |   mypkg.heavy.sub
import time:       900 |       3000 | boto3
import time:       400 |       3400 |   boto3.session
"""


def _write(tmp_path, text):
    p = tmp_path / "it.log"
    p.write_text(text)
    return p


def test_parse_self_ms_skips_header_and_converts_us_to_ms(tmp_path):
    out = parse_self_ms(_write(tmp_path, SAMPLE))
    assert out["os"] == 0.3  # 300us -> 0.3ms
    assert out["mypkg.heavy"] == 1.5
    assert "self [us]" not in out  # header row ignored


def test_parse_self_ms_missing_file_is_empty():
    assert parse_self_ms("/no/such/file.log") == {}


def test_aggregate_external_collapses_to_top_level_first_party_stays_full(tmp_path):
    log = _write(tmp_path, SAMPLE)
    agg = aggregate_self_ms(log, is_first_party=lambda m: m.split(".")[0] == "mypkg")
    assert agg["boto3"] == 1.3  # boto3 + boto3.session collapsed
    assert agg["mypkg.heavy"] == 1.5  # first-party kept per-module
    assert agg["mypkg.heavy.sub"] == 0.25


def test_compare_logs_net_and_states(tmp_path):
    base = _write(tmp_path, SAMPLE)  # base has boto3
    cur_text = SAMPLE.replace("import time:       900 |       3000 | boto3\n", "").replace(
        "import time:       400 |       3400 |   boto3.session\n", ""
    )
    cur = tmp_path / "cur.log"
    cur.write_text(cur_text)
    base_total, cur_total, deltas = compare_logs(base, cur, is_first_party=lambda m: m.startswith("mypkg"))
    assert base_total - cur_total == pytest.approx(1.3)  # boto3 fully removed
    removed = [d for d in deltas if d[2] == "boto3"][0]
    assert removed[1] == "REMOVED"
    assert removed[0] == pytest.approx(1.3)
