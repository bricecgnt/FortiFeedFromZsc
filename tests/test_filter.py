from zscaler_feed.filter import split


def test_split_basic_v4_v6():
    v4, v6 = split(["165.225.0.0/22", "8.8.8.8", "2606:4700::/32"])
    assert v4 == ["8.8.8.8", "165.225.0.0/22"]
    assert v6 == ["2606:4700::/32"]


def test_split_dedupes_and_sorts():
    v4, _ = split(["10.0.0.1", "10.0.0.1", "1.1.1.1"])
    assert v4 == ["1.1.1.1", "10.0.0.1"]


def test_split_rejects_default_routes():
    v4, v6 = split(["0.0.0.0/0", "::/0", "1.1.1.1"])
    assert v4 == ["1.1.1.1"]
    assert v6 == []


def test_split_ignores_invalid_and_blank():
    v4, v6 = split(["not-an-ip", "", "  ", "1.1.1.1"])
    assert v4 == ["1.1.1.1"]
    assert v6 == []


def test_split_keeps_ipv6_slash32_as_network():
    # An IPv6 /32 is a huge block, not a host -- must keep its prefix.
    v4, v6 = split(["2606:4700::/32"])
    assert v6 == ["2606:4700::/32"]


def test_split_host_addresses_drop_redundant_prefix():
    v4, v6 = split(["1.1.1.1/32", "::1/128"])
    assert v4 == ["1.1.1.1"]
    assert v6 == ["::1"]
