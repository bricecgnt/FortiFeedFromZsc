"""Validated allowlists for the Zscaler firewall feed.

Nothing here is derived from user-supplied free text: every value a deploy
parameter can select must appear in one of these lookup tables. This keeps
the upstream-fetch host pinned (SSRF posture) regardless of which category or
cloud a customer selects.
"""

HOST = "config.zscaler.com"  # pinned; only the path tokens below vary

CLOUDS = {
    "zscaler.net", "zscalertwo.net", "zscalerthree.net", "zscalerten.net",
    "zscalereleven.net", "zscalertwelve.net", "zscalerbeta.net",
    "zspreview.net", "zscloud.net", "zscalergov.us",
}

# Per-cloud ZPA endpoint *path* on the pinned HOST above.
#
# The ZPA endpoint is NOT a simple per-cloud pattern: e.g. zscaler.net uses
# "/api/private.zscaler.com/zpa/json" while zscalertwo.net uses
# "/zpatwo.net/zpa" (no "/api/" prefix, no "/json" suffix). So this is a
# confirmed-only allowlist of full paths, not a derived/templated value.
# A cloud with no entry here does not support the ZPA category yet --
# confirm its endpoint shape before adding it.
ZPA_PATHS = {
    "zscaler.net": "/api/private.zscaler.com/zpa/json",
    "zscalertwo.net": "/zpatwo.net/zpa",
}

CATEGORIES = {"svpn", "zpa"}


def validate_cloud(cloud):
    cloud = cloud.strip().lower()
    if cloud not in CLOUDS:
        raise ValueError("Unrecognised Zscaler cloud: %s" % cloud)
    return cloud


def zpa_path(cloud):
    cloud = validate_cloud(cloud)
    if cloud not in ZPA_PATHS:
        raise ValueError("ZPA category not yet supported for cloud: %s" % cloud)
    return ZPA_PATHS[cloud]
