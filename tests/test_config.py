import pytest

from zscaler_feed.config import CLOUDS, ZPA_PATHS, validate_cloud, zpa_path


def test_zpa_paths_subset_of_clouds():
    assert set(ZPA_PATHS.keys()) <= CLOUDS


def test_validate_cloud_accepts_known():
    assert validate_cloud("Zscaler.NET") == "zscaler.net"


def test_validate_cloud_rejects_unknown():
    with pytest.raises(ValueError):
        validate_cloud("evil.example.com")


def test_zpa_path_lookup():
    assert zpa_path("zscaler.net") == "/api/private.zscaler.com/zpa/json"
    assert zpa_path("zscalertwo.net") == "/zpatwo.net/zpa"


def test_zpa_path_unsupported_cloud():
    with pytest.raises(ValueError):
        zpa_path("zscalerthree.net")
