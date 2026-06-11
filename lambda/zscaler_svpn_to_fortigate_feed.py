"""
zscaler_svpn_to_fortigate_feed.py

Reference copy of the AWS Lambda handler. The deployable copy is embedded inline
inside aws/template.yaml so the deployed stack has NO dependency on this repo at
runtime. This file exists only so the logic is easy to read and review. Keep the
two copies in sync (same logic).

What it does:
  Fetches the published Zscaler SVPN (Z-Tunnel 2.0 server) IP list, validates
  every entry, removes duplicates, sorts, splits IPv4 from IPv6, and writes two
  text variants per family to S3:
    - a commented variant (`#` header line) for FortiGate, Palo Alto EDL,
      Check Point, and Juniper SRX, which all ignore `#` comment lines, and
    - a plain variant (no comment line) for Cisco Secure Firewall Security
      Intelligence feeds, which do not support comments at all.

Safety:
  - If fewer than MIN_EXPECTED valid IPs are found in total, it raises and writes
    nothing, so a bad fetch can never empty the feed.
  - A family (IPv4 or IPv6) that comes back empty for a run is NOT written, so a
    partial fetch can never overwrite a good per-family feed with an empty file.

Runtime: python3.12 (boto3 is provided by the Lambda runtime).
Environment variables: ZSCALER_CLOUD, S3_BUCKET, S3_KEY_IPV4, S3_KEY_IPV6,
S3_KEY_IPV4_PLAIN, S3_KEY_IPV6_PLAIN, MIN_EXPECTED, HTTP_TIMEOUT.

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

HOST = "config.zscaler.com"  # pinned; only the cloud token below is variable
CLOUDS = {
    "zscaler.net", "zscalertwo.net", "zscalerthree.net", "zscalerten.net",
    "zscalereleven.net", "zscalertwelve.net", "zscalerbeta.net",
    "zspreview.net", "zscloud.net", "zscalergov.us",
}
s3 = boto3.client("s3")


def _find(node, out):
    """Collect every value under any 'svpnIPs' key, wherever it appears."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "svpnIPs" and isinstance(v, list):
                out += [x for x in v if isinstance(x, str)]
            else:
                _find(v, out)
    elif isinstance(node, list):
        for i in node:
            _find(i, out)
    return out


def _fmt(net):
    """Render a network, dropping the prefix only for single-host entries.

    A host is /32 for IPv4 or /128 for IPv6 (prefixlen == max_prefixlen); keying
    on the family's max prefix avoids mistaking a legitimate IPv6 /32 range for a
    host.
    """
    return str(net.network_address) if net.prefixlen == net.max_prefixlen else str(net)


def _split(ips):
    """Validate, dedupe, sort; return (ipv4_list, ipv6_list).

    Accepts host addresses and CIDR notation. Host addresses are emitted without
    a redundant /32 or /128 suffix so the output stays identical to the previous
    host-only format; networks keep their prefix length. Default routes
    (0.0.0.0/0, ::/0) are rejected as a safety guard.
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


def _body(ips, cloud, fam):
    """Commented variant: FortiGate, Palo Alto EDL, Check Point, Juniper SRX."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ("# Zscaler SVPN %s cloud=%s generated=%s count=%d\n"
            % (fam, cloud, ts, len(ips))) + "\n".join(ips) + "\n"


def _body_plain(ips):
    """Plain variant: Cisco Secure Firewall (no '#' comment support)."""
    return "\n".join(ips) + "\n"


def handler(event, context):
    cloud = os.environ.get("ZSCALER_CLOUD", "zscaler.net").strip().lower()
    if cloud not in CLOUDS:
        raise ValueError("Unrecognised Zscaler cloud: %s" % cloud)
    bucket = os.environ["S3_BUCKET"]
    k4 = os.environ.get("S3_KEY_IPV4", "zscaler/svpn_ipv4.txt")
    k6 = os.environ.get("S3_KEY_IPV6", "zscaler/svpn_ipv6.txt")
    k4p = os.environ.get("S3_KEY_IPV4_PLAIN", "zscaler/svpn_ipv4_cisco.txt")
    k6p = os.environ.get("S3_KEY_IPV6_PLAIN", "zscaler/svpn_ipv6_cisco.txt")
    mn = int(os.environ.get("MIN_EXPECTED", "10"))
    to = int(os.environ.get("HTTP_TIMEOUT", "20"))
    url = "https://%s/api/%s/cenr/json" % (HOST, cloud)
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "svpn-feed/1.0"})
    with urllib.request.urlopen(req, timeout=to, context=ssl.create_default_context()) as r:
        raw = r.read(52428801)
    if len(raw) > 52428800:
        raise RuntimeError("Response exceeded size ceiling")
    v4, v6 = _split(_find(json.loads(raw.decode("utf-8")), []))
    if len(v4) + len(v6) < mn:
        raise RuntimeError("Only %d valid IPs found; refusing to publish"
                           % (len(v4) + len(v6)))
    # Skip a family that is empty this run so a partial fetch never overwrites a
    # good per-family feed with an empty file.
    for key, keyp, ips, fam in ((k4, k4p, v4, "IPv4"), (k6, k6p, v6, "IPv6")):
        if not ips:
            print("No %s entries this run; leaving existing feed untouched." % fam)
            continue
        s3.put_object(Bucket=bucket, Key=key,
                      Body=_body(ips, cloud, fam).encode("utf-8"),
                      ContentType="text/plain; charset=utf-8",
                      CacheControl="max-age=300")
        s3.put_object(Bucket=bucket, Key=keyp,
                      Body=_body_plain(ips).encode("utf-8"),
                      ContentType="text/plain; charset=utf-8",
                      CacheControl="max-age=300")
    return {"ipv4": len(v4), "ipv6": len(v6)}
