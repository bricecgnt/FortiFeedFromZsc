# Zscaler SVPN → multi-vendor firewall feed

Automatically publish the Zscaler **SVPN (Z-Tunnel 2.0 server) IP list** as a feed
that **FortiGate, Palo Alto (EDL), Check Point, Juniper SRX, and Cisco Secure
Firewall** can all consume, so you can keep Z-Tunnel 2.0 traffic off a
site-to-site IPsec tunnel without maintaining the IP list by hand.

> **Disclaimer.** This is a community solution provided **as-is, without warranty of
> any kind**. It is **not an official Zscaler product, offering, or supported
> integration**. Review it before deploying it into your environment.

Deploy with one click into **your own** AWS account or Azure subscription. After
deployment, the stack is **self-contained**: the function logic is embedded in the
template, so nothing is fetched from this repository at runtime. You can delete this
repo and existing deployments keep running.

---

## What it does

Zscaler publishes the current SVPN IP list at
`https://config.zscaler.com/api/<cloud>/cenr/json` (the IPs sit in a top-level
`svpnIPs` block). This solution, on a schedule:

1. downloads that document over HTTPS,
2. extracts the `svpnIPs`, validates each entry, removes duplicates, and splits
   IPv4 from IPv6,
3. refuses to publish if the result looks empty or too small (so a bad fetch can
   never wipe your feed), and
4. writes two text-file **variants** per IP family that firewalls pull on their
   own refresh timer:
   - `svpn_ipv4.txt` / `svpn_ipv6.txt` — one IP/CIDR per line with a `#` comment
     header. Use these for **FortiGate, Palo Alto EDL, Check Point, and Juniper
     SRX**, which all ignore `#` comment lines.
   - `svpn_ipv4_cisco.txt` / `svpn_ipv6_cisco.txt` — the same list with **no
     comment line**. Use these for **Cisco Secure Firewall** (Security
     Intelligence feeds reject `#` lines).

## Vendor compatibility

| Vendor | Feature | File to use |
|---|---|---|
| FortiGate | External Threat Feed (IP Address) | `svpn_ipv4.txt` / `svpn_ipv6.txt` |
| Palo Alto Networks | External Dynamic List (EDL), type "IP List" | `svpn_ipv4.txt` / `svpn_ipv6.txt` |
| Check Point | Network Feed (Custom Intelligence Feed) | `svpn_ipv4.txt` / `svpn_ipv6.txt` |
| Juniper SRX | Dynamic Address / feed-server | `svpn_ipv4.txt` / `svpn_ipv6.txt` |
| Cisco Secure Firewall | Security Intelligence feed (network list) | `svpn_ipv4_cisco.txt` / `svpn_ipv6_cisco.txt` |

All files are plain text, `Content-Type: text/plain; charset=utf-8`, one
host/CIDR per line, refreshed on the schedule below.

## Usage model: routing, not whitelisting

These feeds are **SVPN (Z-Tunnel 2.0) server addresses**. The intended use is a
**routing/PBR match** — a policy route, SD-WAN rule, or route-map entry that
steers Z-Tunnel 2.0 traffic *off* a site-to-site IPsec tunnel. They are **not**
intended as a security allow-list/whitelist entry in a firewall policy. Keeping
this distinction matters: a future release may add ZPA and data-center IP
categories, which serve the opposite purpose (allow-listing Zscaler
infrastructure in security policy) and will always be published as **separate**
feed files so the two usages are never mixed.

## Architecture

```
Zscaler config (HTTPS)
        |
        v
  AWS Lambda  /  Azure Logic App     (scheduled)
        |
        v
  S3 bucket   /  Blob container       (private by default)
        |
        v
  CloudFront  /  (Front Door, optional)   --> stable HTTPS URL
        |
        v
  FortiGate External Threat Feed (IP Address)
        |
        v
  Dynamic address object you reference to exclude Z-Tunnel 2.0 from IPsec
```

---

## Deploy on AWS (one click)

[![Launch Stack](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home?region=eu-west-1#/stacks/create/review?templateURL=https://zscaler-feed-templates-11022.s3.eu-west-1.amazonaws.com/zscaler-svpn-fortigate/template.yaml&stackName=zscaler-svpn-feed)

The button opens the CloudFormation console in **your** account, pre-filled with the
template. Review the parameters and create the stack.

> **Why an S3 URL?** AWS CloudFormation's quick-create only accepts a template URL
> hosted on Amazon S3 — it rejects raw GitHub URLs (`TemplateURL must be a supported
> URL`). The template above is the same content as `aws/template.yaml` in this repo,
> published to a public S3 object in `eu-west-1`. To host your own copy: upload
> `aws/template.yaml` to an S3 bucket and point the button's `templateURL` at it.
> Alternatively, skip the button entirely — in the CloudFormation console choose
> **Create stack → Upload a template file** and select `aws/template.yaml`.

The template creates: an S3 bucket (private, versioned, encrypted), the Lambda
(code embedded inline), its IAM role (write to the two feed objects only), an
EventBridge schedule, a one-time initialiser so the files exist right after deploy,
and optionally a CloudFront distribution.

### AWS parameters

| Parameter | Default | Notes |
|---|---|---|
| `ZscalerCloud` | `zscaler.net` | Your Zscaler cloud |
| `ScheduleExpression` | `rate(6 hours)` | Refresh cadence |
| `ExposureMode` | `PublicRead` | `PublicRead` (direct S3 HTTPS) or `CloudFront` (private bucket + CDN) |
| `MinExpected` | `10` | Safety floor before publishing |

The feed URLs are shown in the stack **Outputs**: `FeedUrlIPv4` / `FeedUrlIPv6`
(commented variant — FortiGate, Palo Alto, Check Point, Juniper) and
`FeedUrlIPv4Cisco` / `FeedUrlIPv6Cisco` (plain variant — Cisco Secure Firewall).

---

## Deploy on Azure (one click)

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fbricecgnt%2FFortiFeedFromZsc%2Fmain%2Fazure%2Fazuredeploy.json)

Replace `bricecgnt`, `zscaler-svpn-fortigate-feed`, and `v0.1.0` in the link (the raw URL must be
URL-encoded, as shown). The button opens a custom deployment in **your**
subscription.

The template creates: a Storage account (TLS 1.2, HTTPS-only), a `feed` blob
container, a Consumption **Logic App** (the whole workflow is defined inline, no
separate code artifact), a system-assigned managed identity, and a Storage Blob
Data Contributor role assignment so the Logic App can write the blobs with no keys.

### Azure parameters

| Parameter | Default | Notes |
|---|---|---|
| `zscalerCloud` | `zscaler.net` | Your Zscaler cloud |
| `refreshIntervalHours` | `6` | Refresh cadence (hours) |
| `exposureMode` | `PublicRead` | `PublicRead` (anonymous blob read) or `Private` |
| `minExpected` | `10` | Safety floor before publishing |

The feed URLs are shown in the deployment **Outputs**: `feedUrlIPv4` /
`feedUrlIPv6` (commented variant) and `feedUrlIPv4Cisco` / `feedUrlIPv6Cisco`
(plain variant for Cisco).

---

## After deploying: firewall side

Use the **commented** feed URLs (`FeedUrlIPv4` / `FeedUrlIPv6` /
`feedUrlIPv4` / `feedUrlIPv6`) for FortiGate, Palo Alto, Check Point, and
Juniper. Use the **Cisco** URLs (`...Cisco`) only for Cisco Secure Firewall.

Remember the [usage model](#usage-model-routing-not-whitelisting): these are
SVPN server addresses for **routing/PBR**, used to steer Z-Tunnel 2.0 traffic
*off* an IPsec tunnel — not a security allow-list entry.

### FortiGate

Create two External Threat Feed connectors of type **IP Address** (Security
Fabric > External Connectors > IP Address), or via CLI:

```
config system external-resource
    edit "Zscaler-SVPN-v4"
        set type address
        set resource "<FeedUrlIPv4 from the stack output>"
        set refresh-rate 360
    next
    edit "Zscaler-SVPN-v6"
        set type address
        set resource "<FeedUrlIPv6 from the stack output>"
        set refresh-rate 360
    next
end
```

`refresh-rate` is in minutes. Each connector then exists as a dynamic address
object you reference in a **policy route / SD-WAN rule** to keep that
destination out of the IPsec tunnel. The exact routing change depends on your
topology.

Requires FortiOS 6.2 or later to use the feed as a destination address (every
current release qualifies). A self-hosted IP-address threat feed needs **no
FortiGuard licence**.

### Palo Alto Networks

Objects > External Dynamic Lists > New, type **IP List**, set Source URL to
`FeedUrlIPv4` (and a second EDL for `FeedUrlIPv6`), choose a refresh interval.
Reference the resulting address objects in a **PBF (Policy-Based Forwarding)**
rule to route Z-Tunnel 2.0 traffic away from the IPsec tunnel.

### Check Point

Security Gateways > Network Feeds > New, point at `FeedUrlIPv4` /
`FeedUrlIPv6`. Use the resulting network object in a **routing**
configuration (e.g. a policy-based routing rule), not in the access policy.

### Juniper SRX

Configure a dynamic address feed-server pointing at `FeedUrlIPv4` /
`FeedUrlIPv6` (`security dynamic-address address-name ... profile feed-name`),
then reference the resulting dynamic address in a **routing instance / RIB
group / filter-based forwarding** rule.

### Cisco Secure Firewall

Objects > Security Intelligence > Network Lists and Feeds > Add Network Lists
and Feeds, point the URL at `FeedUrlIPv4Cisco` / `FeedUrlIPv6Cisco` (no `#`
comment lines). Use the resulting network object in a **policy-based routing**
(PBR) configuration to steer traffic away from the IPsec tunnel.

---

## Exposure options

By default the two files are served directly over HTTPS (`PublicRead`). The feed
content is **public Zscaler data**, so this is bucket hygiene rather than secrecy.
If your security team requires restricted access:

- **AWS:** set `ExposureMode = CloudFront`. The bucket stays fully private and
  CloudFront serves the files; add a WAF IP set or basic auth if you want to
  restrict who can fetch.
- **Azure:** set `exposureMode = Private` (no anonymous access) and front the
  container with Azure Front Door or a SAS URL.

The FortiGate feed connector supports HTTP basic auth, and on 7.6 mutual TLS, so
either pairs cleanly with a restricted setup.

> Note: some organisations enforce a policy that forbids public-read storage
> (AWS account-level Block Public Access / SCP, or an Azure Policy on
> `allowBlobPublicAccess`). If so, the `PublicRead` mode is denied at deploy by
> that guardrail, and you should use the CloudFront / Private + Front Door path.

---

## Cost

At this volume (a few KB, four runs a day) the running cost rounds to well under
**1 USD/month**, often within free-tier allowances. The only component that adds
real cost is optional **AWS WAF** (≈ 5–7 USD/month) if you put an IP allowlist in
front of CloudFront.

## Maintenance / support

The deployed stack does not call back to this repository, so there is nothing to
keep running on the repo side for existing deployments. If Zscaler ever changes the
feed structure, or you want a fix, re-deploy from an updated template; running
copies will not auto-update (by design). Pin the launch buttons to a release tag
rather than `main` so deployments are reproducible.

### Behaviour notes

- **Per-family safety.** Beyond the global `MinExpected` / `minExpected` floor, a
  family (IPv4 or IPv6) that returns zero entries on a given run is **not**
  written, so a partial fetch can never overwrite a known-good per-family feed
  with an empty file. The corresponding feed files (both the commented and the
  Cisco plain variant) simply keep their last value.
- **CIDR support.** Both host addresses and CIDR ranges are accepted. Host
  addresses are emitted without a redundant `/32` or `/128` suffix, so existing
  feeds are unchanged.
- **Two variants, same data.** The commented and Cisco plain files always contain
  the same IP set for a given family — only the presence of the `#` header line
  differs.

### Teardown (AWS)

The S3 bucket is created with `DeletionPolicy: Retain` because it is versioned and
holds objects — an automatic delete would otherwise fail and leave the stack in
`DELETE_FAILED`. To fully remove the solution: delete the CloudFormation stack,
then empty and delete the retained bucket manually (its name is in the stack
**Outputs** as `BucketName`).

## Repository layout

```
aws/template.yaml      CloudFormation template (inline Lambda + CloudFront flag)
azure/azuredeploy.json  ARM template (inline Logic App workflow)
lambda/                 readable reference copy of the function logic
README.md  LICENSE
```
