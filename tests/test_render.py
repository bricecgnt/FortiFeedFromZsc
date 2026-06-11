from zscaler_feed.render import commented, plain


def test_plain_no_header():
    out = plain(["1.1.1.1", "2.2.2.2"])
    assert out == "1.1.1.1\n2.2.2.2\n"
    assert "#" not in out


def test_commented_has_header_and_count():
    out = commented(["1.1.1.1"], "zscaler.net", "ZPA", "IPv4")
    lines = out.splitlines()
    assert lines[0].startswith("#")
    assert "count=1" in lines[0]
    assert "cloud=zscaler.net" in lines[0]
    assert lines[1] == "1.1.1.1"
