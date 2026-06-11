"""Render a sorted IP/CIDR list as feed text.

Two variants of the same data:
  - commented: a '#' header line, ignored by FortiGate, Palo Alto EDL,
    Check Point, and Juniper SRX.
  - plain: no header line, for Cisco Secure Firewall Security Intelligence
    feeds, which reject '#' comment lines.
"""

from datetime import datetime, timezone


def commented(ips, cloud, category, fam):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ("# Zscaler %s %s cloud=%s generated=%s count=%d\n"
            % (category, fam, cloud, ts, len(ips))) + "\n".join(ips) + "\n"


def plain(ips):
    return "\n".join(ips) + "\n"
