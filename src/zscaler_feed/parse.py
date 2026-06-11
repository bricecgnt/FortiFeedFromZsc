"""Extract raw IP/CIDR strings for each category from the Zscaler JSON APIs."""


def find_svpn_ips(node, out=None):
    """Collect every value under any 'svpnIPs' key, wherever it appears.

    cenr/json nests data under continent/region groupings, so this walks the
    whole document rather than assuming a fixed shape.
    """
    if out is None:
        out = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "svpnIPs" and isinstance(v, list):
                out += [x for x in v if isinstance(x, str)]
            else:
                find_svpn_ips(v, out)
    elif isinstance(node, list):
        for i in node:
            find_svpn_ips(i, out)
    return out


def find_zpa_ips(doc):
    """Extract every IP/CIDR from a zpa/json document.

    Shape: {"Cloud Name": ..., "content": [{..., "IPs": [...]}, ...]}.
    Each entry in "content" contributes its "IPs" list (a mix of bare hosts
    and CIDRs, IPv4 and IPv6).
    """
    out = []
    content = doc.get("content") if isinstance(doc, dict) else None
    if not isinstance(content, list):
        return out
    for entry in content:
        if not isinstance(entry, dict):
            continue
        ips = entry.get("IPs")
        if isinstance(ips, list):
            out += [x for x in ips if isinstance(x, str)]
    return out
