"""Validate, dedupe, sort, and split a list of IP/CIDR strings."""

import ipaddress


def fmt(net):
    """Render a network, dropping the prefix only for single-host entries.

    A host is /32 for IPv4 or /128 for IPv6 (prefixlen == max_prefixlen); keying
    on the family's max prefix avoids mistaking a legitimate IPv6 /32 range for
    a host.
    """
    return str(net.network_address) if net.prefixlen == net.max_prefixlen else str(net)


def split(ips):
    """Validate, dedupe, sort; return (ipv4_list, ipv6_list).

    Accepts host addresses and CIDR notation. Host addresses are emitted
    without a redundant /32 or /128 suffix; networks keep their prefix
    length. Default routes (0.0.0.0/0, ::/0) are rejected as a safety guard.
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
    return [fmt(n) for n in sorted(v4)], [fmt(n) for n in sorted(v6)]
