"""
zscaler_svpn_to_fortigate_feed.py

Reference copy of the AWS Lambda handler. The deployable copy is embedded inline
inside aws/template.yaml so the deployed stack has NO dependency on this repo at
runtime. This file exists only so the logic is easy to read and review.

What it does:
  Fetches the published Zscaler SVPN (Z-Tunnel 2.0 server) IP list, validates
  every entry, removes duplicates, sorts, splits IPv4 from IPv6, and writes two
  plain-text files to S3 that a FortiGate External Threat Feed consumes.

Safety: if fewer than MIN_EXPECTED valid IPs are found, it raises and writes
nothing, so a bad fetch can never empty the feed.

Runtime: python3.12 (boto3 is provided by the Lambda runtime).
Environment variables: ZSCALER_CLOUD, S3_BUCKET, S3_KEY_IPV4, S3_KEY_IPV6,
MIN_EXPECTED, HTTP_TIMEOUT.

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


def _split(ips):
    """Validate, dedupe, sort; return (ipv4_list, ipv6_list)."""
    v4, v6 = set(), set()
    for e in ips:
        e = e.strip()
        if not e:
            continue
        try:
            o = ipaddress.ip_address(e)
        except ValueError:
            continue
        (v4 if o.version == 4 else v6).add(o)
    return [str(i) for i in sorted(v4)], [str(i) for i in sorted(v6)]


def _body(ips, cloud, fam):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ("# Zscaler SVPN %s cloud=%s generated=%s count=%d\n"
            % (fam, cloud, ts, len(ips))) + "\n".join(ips) + "\n"


def handler(event, context):
    cloud = os.environ.get("ZSCALER_CLOUD", "zscaler.net").strip().lower()
    if cloud not in CLOUDS:
        raise ValueError("Unrecognised Zscaler cloud: %s" % cloud)
    bucket = os.environ["S3_BUCKET"]
    k4 = os.environ.get("S3_KEY_IPV4", "zscaler/svpn_ipv4.txt")
    k6 = os.environ.get("S3_KEY_IPV6", "zscaler/svpn_ipv6.txt")
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
    for key, ips, fam in ((k4, v4, "IPv4"), (k6, v6, "IPv6")):
        s3.put_object(Bucket=bucket, Key=key,
                      Body=_body(ips, cloud, fam).encode("utf-8"),
                      ContentType="text/plain; charset=utf-8",
                      CacheControl="max-age=300")
    return {"ipv4": len(v4), "ipv6": len(v6)}
