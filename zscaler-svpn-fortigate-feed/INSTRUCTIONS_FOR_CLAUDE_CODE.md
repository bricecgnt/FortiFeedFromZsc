# Instructions for Claude Code

You are working inside a directory that contains a finished infrastructure repository.
Your job is to **validate it, publish it to GitHub, and cut a tagged release**, then
fix the launch-button URLs so they point at that release. Do **not** redesign the
solution. Treat the templates and function logic as correct unless validation proves
otherwise.

## What this repo is

A one-click deployable solution that publishes the Zscaler SVPN (Z-Tunnel 2.0) IP
list as a feed a FortiGate consumes. AWS uses an inline Lambda in
`aws/template.yaml`; Azure uses an inline Logic App in `azure/azuredeploy.json`. The
key design constraint: the deployed stack must stay **self-contained** (no runtime
dependency on this repo), so the function code is embedded in the templates on
purpose. The launch buttons in `README.md` reference raw GitHub URLs pinned to a
release tag.

## Inputs the human will give you (ask if not provided)

```
OWNER       = <github user or org>          e.g. brice-zs
REPO        = <repository name>             e.g. zscaler-svpn-fortigate-feed
VISIBILITY  = public                        (must be public; see note in Step 5)
TAG         = v1.0.0                         release tag
RUN_CLOUD_VALIDATION = yes|no               run aws/az validators if logged in
```

## Expected files

```
aws/template.yaml
azure/azuredeploy.json
lambda/zscaler_svpn_to_fortigate_feed.py
README.md   LICENSE   .gitignore
```
If any are missing, stop and report.

## Step 1: Pre-flight validation (before any git work)

Run these and fix only genuine breakages. Report results.

```bash
# Python logic compiles
python3 -m py_compile lambda/zscaler_svpn_to_fortigate_feed.py

# Azure ARM is valid JSON
python3 -c "import json; json.load(open('azure/azuredeploy.json')); print('azure JSON ok')"

# AWS template lint (preferred). If pip is slow/unavailable, skip and say so.
pip install --quiet cfn-lint && cfn-lint aws/template.yaml && echo "cfn-lint ok"
```

Also confirm the inline Lambda inside `aws/template.yaml` (the block under
`Code: ZipFile: |`) stays under **4096 bytes**; CloudFormation rejects larger inline
code. If you ever edit it, keep `lambda/zscaler_svpn_to_fortigate_feed.py` in sync
(same logic) and re-check the size.

## Step 2: Replace the placeholders in README.md

`README.md` contains placeholder tokens in the two launch-button URLs. Replace **all**
occurrences:

- `OWNER`  -> the GitHub owner
- `REPO`   -> the repository name
- `v1.0.0` -> the chosen `TAG`

Both buttons must end up consistent. The AWS button uses a plain raw URL; the Azure
button uses the **URL-encoded** raw URL (slashes shown as `%2F`), so `OWNER`, `REPO`,
and the tag appear as literal text between the encoded slashes and a normal text
replace is correct.

```bash
sed -i "s#OWNER#$OWNER#g; s#REPO#$REPO#g; s#v1.0.0#$TAG#g" README.md
git --no-pager diff --no-index /dev/null README.md >/dev/null 2>&1 || true
grep -n "raw.githubusercontent.com\|deploytoazurebutton\|portal.azure.com" README.md
```

Eyeball the grep output: the AWS URL should read
`https://raw.githubusercontent.com/$OWNER/$REPO/$TAG/aws/template.yaml` and the Azure
URL should contain `...%2F$OWNER%2F$REPO%2F$TAG%2Fazure%2Fazuredeploy.json`.

## Step 3: Initialise git and commit

```bash
git init -q
git add .
git commit -qm "Initial commit: Zscaler SVPN to FortiGate feed (AWS + Azure one-click)"
```

## Step 4: Create the GitHub repo and push

Use the GitHub CLI (`gh`). It must already be authenticated (`gh auth status`).

```bash
gh repo create "$OWNER/$REPO" --"$VISIBILITY" --source=. --remote=origin --push
```

If the repo already exists, add the remote and push instead:

```bash
git remote add origin "https://github.com/$OWNER/$REPO.git"
git push -u origin HEAD:main
```

## Step 5: Tag and create the release

The launch buttons resolve `raw.githubusercontent.com/$OWNER/$REPO/$TAG/...`, so the
tag must exist and point at the commit that already contains the corrected README.

```bash
git tag "$TAG"
git push origin "$TAG"
gh release create "$TAG" --title "$TAG" --notes "One-click Zscaler SVPN to FortiGate feed for AWS and Azure."
```

**Important:** the repo must be **public** for the buttons to work. AWS CloudFormation
and the Azure portal fetch the template anonymously over `raw.githubusercontent.com`;
a private repo will make both buttons fail. If the human needs it private, tell them
the templates must instead be hosted somewhere anonymously reachable (for AWS, an S3
object URL), and do not claim the buttons work as-is.

## Step 6: Verify the published URLs actually resolve

```bash
curl -fsSL "https://raw.githubusercontent.com/$OWNER/$REPO/$TAG/aws/template.yaml" | head -3
curl -fsSL "https://raw.githubusercontent.com/$OWNER/$REPO/$TAG/azure/azuredeploy.json" | head -3
```

Both must return content (not 404). If they 404, the tag was not pushed or the path is
wrong; fix before reporting success.

## Step 7 (optional): Cloud-side validation

Only if `RUN_CLOUD_VALIDATION = yes` and the CLIs are authenticated. These need cloud
credentials; skip cleanly if not present.

```bash
# AWS (no resources created)
aws cloudformation validate-template --template-body file://aws/template.yaml

# Azure (no resources created; needs an existing empty resource group)
az deployment group validate \
  --resource-group "$RG" \
  --template-file azure/azuredeploy.json \
  --parameters zscalerCloud=zscaler.net exposureMode=PublicRead
```

## Step 8: Report back

Print, for the human to paste into the customer email or README:
- the repo URL,
- the release tag,
- the final AWS "Launch Stack" URL,
- the final Azure "Deploy to Azure" URL,
- the result of every validation step (pass / skipped / fixed).

## Guardrails (do NOT)

- Do **not** change the function logic, the IAM scoping, the SSRF allow-list, the TLS
  settings, or the min-count safety valve. These are deliberate security properties.
- Do **not** widen S3 / blob access beyond what the existing `ExposureMode` /
  `exposureMode` flag controls, and do not remove Block Public Access defaults.
- Do **not** introduce a runtime dependency on this repo (no `RUN_FROM_PACKAGE` from a
  GitHub URL, no fetching code at runtime). Code stays inline in the templates.
- Do **not** commit any secrets, cloud credentials, or `.env` files.
- Do **not** remove the as-is / no-warranty / not-an-official-Zscaler-product
  disclaimer from `README.md` or `LICENSE`.

## Definition of done

A public GitHub repo exists at `$OWNER/$REPO`, a release `$TAG` is published, both raw
template URLs return content, the README buttons point at `$TAG`, and all validation
steps either passed or were explicitly reported as skipped.
