# Zscaler SVPN → FortiGate IP feed

Automatically publish the Zscaler **SVPN (Z-Tunnel 2.0 server) IP list** as a feed
that a **FortiGate External Threat Feed** can consume, so you can keep Z-Tunnel 2.0
traffic off a site-to-site IPsec tunnel without maintaining the IP list by hand.

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
4. writes two plain-text files (`svpn_ipv4.txt`, `svpn_ipv6.txt`) that FortiGate
   pulls on its own refresh timer.

The output is one IP per line with a `#` comment header, which is exactly the
format a FortiGate IP-address threat feed expects (comment lines are ignored).

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

[![Launch Stack](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home#/stacks/create/review?templateURL=https://raw.githubusercontent.com/bricecgnt/FortiFeedFromZsc/v0.1.0/aws/template.yaml&stackName=zscaler-svpn-feed)

Replace `bricecgnt/FortiFeedFromZsc` and the `v0.1.0` tag in the link above with your published
repository and release tag. The button opens the CloudFormation console in **your**
account, pre-filled with the template. Review the parameters and create the stack.

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

The feed URLs are shown in the stack **Outputs** (`FeedUrlIPv4`, `FeedUrlIPv6`).

---

## Deploy on Azure (one click)

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fbricecgnt%2FFortiFeedFromZsc%2Fv0.1.0%2Fazure%2Fazuredeploy.json)

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

The feed URLs are shown in the deployment **Outputs**.

---

## After deploying: FortiGate side

Create two External Threat Feed connectors of type **IP Address** pointing at the
two URLs (Security Fabric > External Connectors > IP Address), or via CLI:

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
object you reference in whatever steers traffic today (static route, SD-WAN rule,
or policy route) to keep that destination out of the IPsec tunnel. The exact
routing change depends on your topology.

Requires FortiOS 6.2 or later to use the feed as a destination address (every
current release qualifies). A self-hosted IP-address threat feed needs **no
FortiGuard licence**.

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

## Repository layout

```
aws/template.yaml      CloudFormation template (inline Lambda + CloudFront flag)
azure/azuredeploy.json  ARM template (inline Logic App workflow)
lambda/                 readable reference copy of the function logic
README.md  LICENSE
```
