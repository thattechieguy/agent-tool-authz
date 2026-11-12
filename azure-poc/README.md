# Azure POC: real Entra sign-in, real API Management, real enforcement

Proves the controls from `agent-tool-authz` against **real Azure services**: real users sign in
to Microsoft Entra, each agent step gets a **delegated token with only that step's scope**, and an
API Management (APIM) policy enforces **user entitlement ∩ step scope**, deny-by-default, rate
limits, a taint signal (fail closed) and approvals bound to the exact request.

There is no LLM in the loop. The test client plays the agent and sends the calls a manipulated
agent would send. The gateway controls hold whether or not a model is fooled.

---

## Before you start: what you need ready (copy this block into your repo README)

> **To run this POC you need:**
>
> - An Azure subscription where you can create resources in a resource group (Contributor on
>   the group is enough). **Use a dev/test tenant and subscription, never production.**
> - Microsoft Entra permissions to: register applications, create three test users, and grant
>   tenant-wide admin consent (for example Cloud Application Administrator or higher, plus
>   User Administrator for the users). If you lack these, ask a tenant admin to do step 2.
> - These resources, all created by you in the portal: 1 API Management instance (with a
>   system-assigned managed identity), 1 App Service plan with 2 web apps, 1 Application
>   Insights instance, 3 app registrations, 3 test users.
> - On your machine: Python 3.11+, a browser (for device-code sign-in), and optionally the Azure CLI.
> - Time: about 3 to 4 hours including APIM provisioning, which can take a long time. Start it first.
> - Cost: APIM and App Service bill while they exist. **Delete the resource group when finished**
>   (step 9). Check current pricing for your chosen APIM tier.
> - Everything is synthetic test data. Do not point this at real APIs or real customer data.

---

## Architecture

```
 you (test client, plays the agent)
   |  1. device-code sign-in as alice / bob / dave   (real Entra user tokens)
   |  2. per-step token: scp = ONE scope, roles = the user's app roles
   v
 API Management  ── validates JWT, azp, scope AND role, rate limit,
   |                 taint claim (signed by orchestrator), approval check
   |   -- send-request /verify -->  Approval service (App Service)
   |  3. forwards with APIM's OWN managed-identity token (service account model)
   v
 Legacy backend (App Service) ── trusts only the APIM managed identity;
                                 never sees the user or the agent
```

The backend token is deliberately a **service-account (managed identity) token**: that is the
legacy constraint this project targets. The user's identity is enforced at the gateway. True
user-preserving propagation (OBO) is a different variant, see "Not covered".

---

## Step 0: Worksheet and secrets

Record these as you go (put them in `.env` later):

| Name | Where it comes from |
|---|---|
| `TENANT_ID` | Entra > Overview |
| `BACKEND_CLIENT_ID` | app registration `loans-backend-api` |
| `GATEWAY_CLIENT_ID` | app registration `loans-gateway-api` |
| `AGENT_CLIENT_ID` | app registration `loans-agent` |
| `APIM_MI_OBJECT_ID` | APIM > Identity > System assigned > Object (principal) ID |

Generate four secrets (any machine with Python):

```
python -c "import secrets,base64,os;print('ADMIN_KEY='+secrets.token_urlsafe(24));print('APPROVER_KEY='+secrets.token_urlsafe(24));print('VERIFY_KEY='+secrets.token_urlsafe(24));print('ORCHESTRATOR_SIGNING_KEY_B64='+base64.b64encode(os.urandom(32)).decode())"
```

`VERIFY_KEY` is shared by the approval service and an APIM named value. The others go in `.env`.

## Step 1: Create API Management first (it is slow)

Portal > **API Management services** > Create.

- Resource group: new, e.g. `rg-agent-authz-poc`. Pick a region and a name.
- **Pricing tier:** Developer (non-production) or a v2 tier if it is available to you. Do **not**
  use Consumption: `rate-limit-by-key` is not supported there. Verify current tier features.
- After creation: **Security > Managed identities > System assigned > On > Save.**
  Copy the **Object (principal) ID** into `APIM_MI_OBJECT_ID`.

While it provisions, continue with steps 2 and 3.

## Step 2: Microsoft Entra

### 2a. App `loans-backend-api`
App registrations > New > single tenant, no redirect URI. Then **Expose an API > Set** the
Application ID URI (default `api://<client-id>`). Copy the client ID to `BACKEND_CLIENT_ID`.

### 2b. App `loans-gateway-api` (the API the agent calls through APIM)
1. Register, single tenant. Copy the client ID to `GATEWAY_CLIENT_ID`.
2. **Expose an API:** set the Application ID URI (default). Add **five scopes**
   (who can consent: Admins and users; state: Enabled): `Loans.Read`, `Loans.Credit`,
   `Loans.Deferral`, `Loans.Waiver`, `Loans.Income`.
3. **App roles > Create app role**, three times. Allowed member types: **Users/Groups**.
   Display name = value: `ReadOnly`, `Servicer`, `SeniorServicer`.
4. **Manifest:** make the API issue **v2 tokens**: set `requestedAccessTokenVersion` to `2`
   (under `api`; in the older manifest format it is `accessTokenAcceptedVersion`). Save.

### 2c. App `loans-agent` (the client that signs users in)
1. Register, single tenant.
2. **Authentication > Add a platform > Mobile and desktop applications** and tick the
   `nativeclient` redirect. Then **Advanced settings > Allow public client flows = Yes.**
3. **API permissions > Add > My APIs > loans-gateway-api > Delegated** and select all five scopes.
   Then **Grant admin consent for the tenant.** Copy the client ID to `AGENT_CLIENT_ID`.

### 2d. Test users and roles
1. Entra > Users > New user: `alice`, `bob`, `dave` (note the UPNs and passwords). Sign each in once
   in a private browser window to set the password and complete any MFA enrolment.
2. Entra > **Enterprise applications > loans-gateway-api > Users and groups > Add user/group.**
   Assign roles (one role per assignment):

   | User | Roles |
   |---|---|
   | alice | `Servicer` and `SeniorServicer` (two assignments) |
   | bob | `ReadOnly` |
   | dave | `Servicer` |

## Step 3: App Service (backend and approval service)

Create **one** App Service plan (Linux, Basic B1 is fine) and **two** web apps on it:
`<name>-backend` and `<name>-approval`. Publish: **Code**; Runtime: **Python 3.11**; HTTPS only.
**Keep each app at a single instance and a single worker** (state is in memory).

For each app: **Settings > Environment variables > App settings**.

Backend (`-backend`):

| Setting | Value |
|---|---|
| `TENANT_ID` | your tenant id |
| `BACKEND_CLIENT_ID` | from 2a |
| `APIM_MI_OBJECT_ID` | from step 1 |
| `ADMIN_KEY` | generated |
| `BACKEND_AUTH_MODE` | `entra_mi` |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` |

Approval (`-approval`):

| Setting | Value |
|---|---|
| `APPROVER_KEY` | generated |
| `VERIFY_KEY` | generated |
| `APPROVAL_TTL_SECONDS` | `300` |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` |

**Startup command** (Settings > Configuration > General settings), for both apps:

```
gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:8000 app:app
```

**Deploy the code** (zip so `app.py` sits at the zip root). PowerShell:

```
Compress-Archive -Path backend\* -DestinationPath backend.zip -Force
Compress-Archive -Path approval-service\* -DestinationPath approval.zip -Force
az webapp deploy --resource-group <rg> --name <name>-backend  --src-path backend.zip  --type zip
az webapp deploy --resource-group <rg> --name <name>-approval --src-path approval.zip --type zip
```

Check `https://<name>-backend.azurewebsites.net/healthz` and the approval `/healthz`.

## Step 4: API Management configuration

1. **Application Insights:** create one (workspace-based). In APIM > **Application Insights > Add**,
   then APIs > All APIs > Settings > enable Application Insights, **sampling 100%, verbosity
   Information** (the policy's audit `trace` needs this).
2. **Named values** (APIM > Named values > Add). Mark the two secrets as **Secret**:

   | Name | Value | Secret |
   |---|---|---|
   | `tenant-id` | tenant id | no |
   | `gateway-client-id` | `GATEWAY_CLIENT_ID` | no |
   | `agent-client-id` | `AGENT_CLIENT_ID` | no |
   | `backend-client-id` | `BACKEND_CLIENT_ID` | no |
   | `approval-service-url` | `https://<name>-approval.azurewebsites.net` (no trailing slash) | no |
   | `approval-verify-key` | `VERIFY_KEY` | **yes** |
   | `orchestrator-signing-key` | `ORCHESTRATOR_SIGNING_KEY_B64` | **yes** |

3. **Import the API:** APIs > Add API > **OpenAPI** > Full. OpenAPI URL:
   `https://<name>-backend.azurewebsites.net/openapi.json`. Display name `Loans`,
   **API URL suffix `loans`**, no product. After import, open API > **Settings**: set **Web service URL**
   to `https://<name>-backend.azurewebsites.net` if empty, and **untick "Subscription required"**
   (Entra tokens are the authentication here). You should see 6 operations. `DELETE` must not be there.
4. **Bring-up policy first.** API > **All operations > Policy (code editor)**: paste
   `apim/policy-baseline.xml`. Save.

## Step 5: Client setup and checkpoints

```
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.lock
copy .env.example .env            # macOS/Linux: cp .env.example .env ; then fill it in
pytest tests/local                # 15 offline tests, no Azure needed
python -m client.login alice      # follow the device-code prompt, sign in AS alice
python -m client.login bob
python -m client.login dave
```

`APIM_BASE` is `https://<apim>.azure-api.net/loans`. The loan path is then
`.../loans/loans/L-1001` (API suffix `loans` + operation path `/loans/{id}`).

**Checkpoint A: the token.** Run `python -m client.show_token alice Loans.Read`. Confirm:
`scp` is **only** `Loans.Read`; `roles` are alice's roles; `aud` is your gateway client id
(or `api://...`); `azp` is the agent client id; `ver` is `2.0`.
If `scp` lists more than you asked for, **stop**: per-step scoping is not working and the
results below would be meaningless. Tell me what you see.

**Checkpoint B: through APIM (baseline policy).**
```
$t = python -m client.show_token alice Loans.Read --raw
curl.exe -i -H "Authorization: Bearer $t" https://<apim>.azure-api.net/loans/loans/L-1001
```
Expect `200` and a header `X-Operation-Id: get_loan_details`. A `404` or a different operation id
means the OpenAPI `operationId`s did not import as expected. A `401` means an audience or issuer
mismatch: decode the token at jwt.ms and compare with the policy. A backend `403 caller_not_allowed`
means `APIM_MI_OBJECT_ID` is wrong.

## Step 6: "Before" run (baseline)

1. Backend app setting `BACKEND_AUTH_MODE` = `none` and restart (models a weak legacy service).
2. APIM policy stays `policy-baseline.xml`.
3. `pytest tests --junitxml=reports/baseline.xml`

Expected: most security tests **fail** (that is the finding). Tests that already pass at baseline:
S08 (positive control), S10 (token validation alone rejects no or garbage tokens) and S04
(the destructive operation is not imported, so APIM already returns 404; add a wildcard
`DELETE /*` operation to the baseline API if you want to see S04 fail like a typical pass-through setup).

## Step 7: "After" run (reference)

1. Backend `BACKEND_AUTH_MODE` = `entra_mi`, restart.
2. APIM > All operations > policy: replace with `apim/policy-reference.xml`. Save.
3. **Test in this order**, because policy expressions are only lightly validated on save and errors show up
   as HTTP 500 at runtime:
   `pytest tests -k "S08"` then `-k "S01 or S02"` then `-k "S03"` then `-k "S06 or S11"`
   then `-k "S07 or S09"` then the full suite: `pytest tests --junitxml=reports/reference.xml`.
4. A 500 means a policy-expression error. Open Application Insights > Failures, or use the APIM
   **Test** tab with tracing, and send me the message.

| Scenario | What it proves | Baseline | Reference |
|---|---|---|---|
| S01 | user without entitlement cannot act through the agent | FAIL | PASS |
| S02 | step token without the scope is refused | FAIL | PASS |
| S03 | credit-pull loop is rate limited | FAIL | PASS |
| S04 | unpublished destructive operation unreachable | PASS* | PASS |
| S05 | backend not reachable around the gateway | FAIL | PASS |
| S06 | tainted run needs approval to write | FAIL | PASS |
| S07 | approval bound to exact body; replay refused | FAIL | PASS |
| S08 | legitimate calls still work | PASS | PASS |
| S09 | tier-3 always needs approval | FAIL | PASS |
| S10 | no/garbage token rejected | PASS | PASS |
| S11 | missing context fails closed; forged context rejected | FAIL | PASS |
| S12 | spoofed role headers ignored | FAIL | PASS |

## Step 8: What to record

Baseline vs reference counts, the `scp`/`roles` of a real token (redact ids), any scenario that did
not behave as expected and why, and what Entra/APIM gave you natively vs what you wrote
(JWT validation, rate limiting and `send-request` are native; the operation map, taint check and
approval service are custom).

## Step 9: Clean up

Delete the resource group (removes APIM, App Service, Application Insights). Then delete the three
app registrations and three test users in Entra. Delete `.env` and `.token_cache/`.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `401 invalid_token` through APIM | `aud`/`iss` mismatch (token not v2; set `requestedAccessTokenVersion` = 2), or wrong tenant/client id in named values |
| `scp` has extra scopes | per-step scoping failed; stop and investigate before trusting any result |
| `roles` missing | user not assigned a role on the **enterprise application** `loans-gateway-api` |
| `403 unauthorized_client` for everyone | `agent-client-id` named value wrong (`azp` must be the agent app id) |
| `404 unknown_operation` on valid calls | `operationId` in OpenAPI differs from the policy `case` labels (check `X-Operation-Id`) |
| `500` after pasting the reference policy | policy expression error; use App Insights failures or Test-tab tracing; send me the text |
| `approval_service_unavailable` | `approval-service-url` wrong, app cold-starting, or `VERIFY_KEY` mismatch (that returns 401 to APIM) |
| `403 caller_not_allowed` from backend | `APIM_MI_OBJECT_ID` is not the APIM identity's object (principal) id |
| device login says wrong user | you signed in as yourself; use a private window and the test user's account |

## What is simplified, and what this does not prove

- Approver authentication is a shared key; production needs a real approver UI and identity.
- Approvals live in memory on one instance; production needs a shared durable store.
- The orchestrator claim is signed with a shared HS256 secret; production should use asymmetric keys
  held in Key Vault.
- The approval hash covers the **raw request body**, so the agent must send the exact bytes it submitted
  for approval. The main project's reference gateway uses canonical JSON; this POC does not.
- Rate-limit counters on multi-unit APIM tiers can be approximate. S03 asserts "at most 3", not "exactly 3".
- The backend is publicly reachable but only trusts the APIM identity; for stronger isolation add
  access restrictions or private networking.
- **Not covered: user-preserving OBO.** The backend token here is APIM's managed identity. APIM has no
  native on-behalf-of policy; preserving the user's identity to the backend would need a token broker
  (a confidential client doing OBO) and a backend that accepts delegated tokens.
- No LLM is involved, so this does not show that a real model can be steered into these calls.
