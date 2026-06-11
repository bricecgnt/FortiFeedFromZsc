import json
import os

from zscaler_feed.parse import find_svpn_ips, find_zpa_ips

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_find_svpn_ips_nested():
    doc = {
        "continents": {
            "Americas": {"cities": [{"svpnIPs": ["1.1.1.1", "2.2.2.2"]}]},
            "EMEA": {"cities": [{"svpnIPs": ["3.3.3.3"]}]},
        }
    }
    out = find_svpn_ips(doc)
    assert sorted(out) == ["1.1.1.1", "2.2.2.2", "3.3.3.3"]


def test_find_svpn_ips_ignores_non_string_entries():
    doc = {"svpnIPs": ["1.1.1.1", 2, None, "3.3.3.3"]}
    assert find_svpn_ips(doc) == ["1.1.1.1", "3.3.3.3"]


def test_find_zpa_ips_real_fixture():
    with open(os.path.join(FIXTURES, "zpa_private_zscaler_com.json")) as f:
        doc = json.load(f)
    out = find_zpa_ips(doc)
    # Three "content" entries in the trimmed fixture, flattened.
    assert "8.25.203.0/24" in out
    assert "13.57.83.247" in out
    assert "2a03:eec0:3212::/48" in out
    # Duplicated CIDR across entries is preserved here; dedup happens in filter.split.
    assert out.count("165.225.0.0/17") == 2


def test_find_zpa_ips_handles_missing_content():
    assert find_zpa_ips({}) == []
    assert find_zpa_ips({"content": "not-a-list"}) == []
