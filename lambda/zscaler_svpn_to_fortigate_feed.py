"""
zscaler_svpn_to_fortigate_feed.py

Reference copy of the AWS Lambda handler. The deployable copy is embedded inline
inside aws/template.yaml so the deployed stack has NO dependency on this repo at
runtime. This file exists only so the logic is easy to read and review. Keep the
two copies in sync (same logic).

What it does:
  For each category selected via CATEGORIES (svpn and/or zpa):
    - svpn: fetches the published Zscaler SVPN (Z-Tunnel 2.0 server) IP list
      (cenr/json). Used for routing/PBR (steer Z-Tunnel 2.0 traffic off an
      IPsec tunnel) -- never for security allow-listing.
    - zpa: fetches the published ZPA app-connector IP ranges (zpa/json). Used
      for security allow-listing (whitelist) -- never for routing. Only
      supported on clouds present in ZPA_PATHS (currently zscaler.net and
      zscalertwo.net); on other clouds the category is silently skipped, and
      any fetch/parse failure is non-fatal so it never blocks the svpn feed.

  For each category, every entry is validated, deduplicated, sorted, split
  IPv4 vs IPv6, and written as two text variants per family to S3:
    - a commented variant (`#` header line) for FortiGate, Palo Alto EDL,
      Check Point, and Juniper SRX, which all ignore `#` comment lines, and
    - a plain `_cisco` variant (no comment line) for Cisco Secure Firewall
      Security Intelligence feeds, which do not support comments at all.

Safety:
  - svpn: if fewer than MIN_EXPECTED valid IPs are found in total, it raises
    and writes nothing, so a bad fetch can never empty the feed.
  - zpa: if fewer than MIN_EXPECTED valid IPs are found in total, the category
    is skipped for this run (existing files untouched); this is logged, not
    raised, since zpa support is best-effort.
  - A family (IPv4 or IPv6) that comes back empty for a run is NOT written, so
    a partial fetch can never overwrite a good per-family feed with an empty
    file.

Runtime: python3.12 (boto3 is provided by the Lambda runtime).
Environment variables: ZSCALER_CLOUD, S3_BUCKET, CATEGORIES, MIN_EXPECTED,
HTTP_TIMEOUT.

Output keys (always, regardless of CATEGORIES content -- only categories
selected and supported for the chosen cloud are written):
  zscaler/svpn_ipv4.txt, zscaler/svpn_ipv4_cisco.txt,
  zscaler/svpn_ipv6.txt, zscaler/svpn_ipv6_cisco.txt,
  zscaler/zpa_ipv4.txt,  zscaler/zpa_ipv4_cisco.txt,
  zscaler/zpa_ipv6.txt,  zscaler/zpa_ipv6_cisco.txt

Community solution, provided as-is, without warranty. Not an official Zscaler
product or offering.
"""

import ipaddress
import json
import os
import ssl
import urllib.request
from datetime import datetime, timezone

import boto3

HOST = "config.zscaler.com"  # pinned; only the path tokens below are variable
CLOUDS = {
    "zscaler.net", "zscalertwo.net", "zscalerthree.net", "zscalerten.net",
    "zscalereleven.net", "zscalertwelve.net", "zscalerbeta.net",
    "zspreview.net", "zscloud.net", "zscalergov.us",
}

# Per-cloud ZPA endpoint *path* on the pinned HOST above. Confirmed-only
# allowlist of full paths -- the shape is NOT a simple per-cloud pattern (e.g.
# zscaler.net uses "/api/private.zscaler.com/zpa/json" while zscalertwo.net
# uses "/zpatwo.net/zpa": no "/api/" prefix, no "/json" suffix). A cloud with
# no entry here does not support the zpa category yet.
ZPA_PATHS = {
    "zscaler.net": "/api/private.zscaler.com/zpa/json",
    "zscalertwo.net": "/zpatwo.net/zpa",
}

s3 = boto3.client("s3")


def _fs(node, out):
    """Collect every value under any 'svpnIPs' key, wherever it appears."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "svpnIPs" and isinstance(v, list):
                out += [x for x in v if isinstance(x, str)]
            else:
                _fs(v, out)
    elif isinstance(node, list):
        for i in node:
            _fs(i, out)
    return out


def _fz(doc):
    """Flatten the 'IPs' arrays from each entry of a ZPA zpa/json 'content' list."""
    out = []
    for e in (doc.get("content") or []):
        if isinstance(e, dict) and isinstance(e.get("IPs"), list):
            out += [x for x in e["IPs"] if isinstance(x, str)]
    return out


def _fmt(n):
    """Render a network, dropping the prefix only for single-host entries.

    A host is /32 for IPv4 or /128 for IPv6 (prefixlen == max_prefixlen); keying
    on the family's max prefix avoids mistaking a legitimate IPv6 /32 range for a
    host.
    """
    return str(n.network_address) if n.prefixlen == n.max_prefixlen else str(n)


def _split(ips):
    """Validate, dedupe, sort; return (ipv4_list, ipv6_list).

    Accepts host addresses and CIDR notation. Host addresses are emitted without
    a redundant /32 or /128 suffix; networks keep their prefix length. Default
    routes (0.0.0.0/0, ::/0) are rejected as a safety guard.
    """
    v4, v6 = set(), set()
    for e in ips:
        e = e.strip()
        if not e:
            continue
        try:
            o = ipaddress.ip_network(e, strict=False)
        except ValueError:
            continue
        if o.prefixlen == 0:  # never publish a default route into the feed
            continue
        (v4 if o.version == 4 else v6).add(o)
    return [_fmt(n) for n in sorted(v4)], [_fmt(n) for n in sorted(v6)]


def _body(ips, cloud, cat, fam):
    """Commented variant: FortiGate, Palo Alto EDL, Check Point, Juniper SRX."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ("# Zscaler %s %s cloud=%s generated=%s count=%d\n"
            % (cat, fam, cloud, ts, len(ips))) + "\n".join(ips) + "\n"


def _get(path, to):
    """Fetch and JSON-decode a path on the pinned HOST, with a size ceiling."""
    req = urllib.request.Request(
        "https://%s%s" % (HOST, path),
        headers={"Accept": "application/json", "User-Agent": "svpn-feed/1.0"})
    with urllib.request.urlopen(req, timeout=to, context=ssl.create_default_context()) as r:
        raw = r.read(52428801)
    if len(raw) > 52428800:
        raise RuntimeError("Response exceeded size ceiling")
    return json.loads(raw.decode("utf-8"))


def _pub(bucket, prefix, cat, cloud, v4, v6, mn):
    """Write commented + plain ('_cisco') variants per family under prefix.

    If the total count is below mn, skip entirely (existing files untouched).
    A family that is empty this run is also skipped, so a partial fetch can
    never overwrite a good per-family feed with an empty file.
    """
    if len(v4) + len(v6) < mn:
        print("Only %d %s IPs found; skipping." % (len(v4) + len(v6), cat))
        return
    for ips, fam, suf in ((v4, "IPv4", "ipv4"), (v6, "IPv6", "ipv6")):
        if not ips:
            print("No %s %s entries this run; feed untouched." % (cat, fam))
            continue
        s3.put_object(Bucket=bucket, Key=prefix + suf + ".txt",
                      Body=_body(ips, cloud, cat, fam).encode(),
                      ContentType="text/plain; charset=utf-8", CacheControl="max-age=300")
        s3.put_object(Bucket=bucket, Key=prefix + suf + "_cisco.txt",
                      Body=("\n".join(ips) + "\n").encode(),
                      ContentType="text/plain; charset=utf-8", CacheControl="max-age=300")


def handler(event, context):
    cloud = os.environ.get("ZSCALER_CLOUD", "zscaler.net").strip().lower()
    if cloud not in CLOUDS:
        raise ValueError("Unrecognised Zscaler cloud: %s" % cloud)
    bucket = os.environ["S3_BUCKET"]
    mn = int(os.environ.get("MIN_EXPECTED", "10"))
    to = int(os.environ.get("HTTP_TIMEOUT", "20"))
    cats = {c.strip() for c in os.environ.get("CATEGORIES", "svpn").lower().split(",") if c.strip()}

    if "svpn" in cats:
        v4, v6 = _split(_fs(_get("/api/%s/cenr/json" % cloud, to), []))
        if len(v4) + len(v6) < mn:
            raise RuntimeError("Only %d valid SVPN IPs found; refusing to publish"
                               % (len(v4) + len(v6)))
        _pub(bucket, "zscaler/svpn_", "SVPN", cloud, v4, v6, 0)

    if "zpa" in cats and cloud in ZPA_PATHS:
        try:
            v4, v6 = _split(_fz(_get(ZPA_PATHS[cloud], to)))
            _pub(bucket, "zscaler/zpa_", "ZPA", cloud, v4, v6, mn)
        except Exception as e:
            print("ZPA fetch failed (non-fatal):", e)
