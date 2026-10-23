# Deploying ClawBack

This is the runbook for the hosted demo: the backend on Nebius AI Cloud and the frontend on Vercel. Nothing in it
has been run yet. Prices and product facts were checked on 2026-10-23, with sources in [section 3](#3-prices-and-sources).

Each step is marked:
- **[You]**: a person must do it: signing in, billing, adding a key, approving something, or pasting secrets.
- **[Script]**: a script or a command you can copy. It needs no decisions.
- **After the merge**: it depends on work from the other workstreams (per-visitor sessions, SQLite, encrypted
  tokens, webhooks, the nightly job, drafts). Do those steps once that work is on `main`.

## 1. The plan

| Part | Where | How |
|---|---|---|
| Backend API | Nebius AI Cloud, Compute: one CPU VM | `cpu-d3`, preset `2vcpu-8gb`, Ubuntu 24.04, region `us-north1` |
| HTTPS | the same VM | Caddy with a free Let's Encrypt certificate on `<ip-with-dashes>.sslip.io` |
| Process | the same VM | a systemd service running uvicorn on `127.0.0.1:8000`, one worker |
| Database | the same VM | the SQLite file on a 10 GiB data disk at `/var/lib/clawback` |
| Nightly job | the same VM | a systemd timer at 3:00 AM Pacific running `python -m clawback.nightly` |
| Code | GitHub, private repo | a read-only deploy key made on the VM |
| Frontend | Vercel | root directory `frontend`, `NEXT_PUBLIC_API_URL` set to the backend URL |
| Models | Nebius Token Factory | unchanged: the backend calls it with `NEBIUS_API_KEY` |

**Cost through Dec 15, 2026: about $81**, before tax. It runs from 2026-10-28 00:00 to 2026-12-15 24:00, which is
49 days or 1,176 hours.

| Item | Arithmetic | USD |
|---|---|---|
| VM, `cpu-d3` `2vcpu-8gb` | 2 vCPU × $0.015 + 8 GiB × $0.0045 = $0.066 an hour; × 1,176 h | 77.62 |
| Boot disk, `network_ssd`, 20 GiB | 20 × $0.071 per GiB-month × 1.611 months | 2.29 |
| Data disk, `network_ssd`, 10 GiB | 10 × $0.071 × 1.611 | 1.14 |
| Static public IPv4 address | listed as free | 0.00 |
| Traffic in and out | listed as free | 0.00 |
| **Total** | | **81.05** |

- Each extra day, for example starting on Oct 24 to test, adds about $1.65.
- Skipping the separate data disk saves $1.14. The data then lives on the boot disk, which is fine for the demo.
  The data disk only helps if the VM has to be rebuilt.
- Nebius takes a first payment of $25 into the balance when a card is added. That covers about 15 days. After
  that the card is charged automatically. Budgets only send alerts; they don't stop spending.
- No hackathon or Token Factory credit covers AI Cloud. The Builders Program gives $25 of Token Factory credit
  and $25 of Tavily credit, and no AI Cloud credit.

### Why a VM and not a serverless endpoint

Nebius Serverless AI Endpoints can run a plain FastAPI container on CPU, always on, with a managed HTTPS URL. They
fit this app worse than a VM:
- The container's disk is wiped on every stop or restart. SQLite would need a separate shared filesystem volume.
- The image, settings and environment variables can't be changed after creation. A change means a new endpoint,
  and a new endpoint gets a **new URL**, which breaks the registered Nylas callback and webhooks.
- The default container disk is 250 GiB, which raises the cost to about $107 unless it is set smaller.

A VM keeps the same URL, IP address and database for the whole judging window (Dec 1 to Dec 15). The Nebius web
console covers every step from Windows. The container files are still in the repo (see [section 12](#12-the-container-route-not-used)).

## 2. Before you start

- [ ] **[You]** A Nebius AI Cloud account with a card added (console: https://console.nebius.com).
- [ ] **[You]** Admin access to the GitHub repo, to add a deploy key.
- [ ] **[You]** A Vercel account connected to GitHub.
- [ ] **[You]** Access to the Nylas and Plaid dashboards.
- [ ] **[You]** Zero Data Retention is on in Token Factory (it is, as of 2026-10-23; check it once more).
- [ ] **[Script]** An SSH key on the laptop. In PowerShell:
  ```powershell
  Test-Path $HOME\.ssh\id_ed25519.pub     # True means you already have one
  ssh-keygen -t ed25519                   # only if it said False; press Enter for the default path
  Get-Content $HOME\.ssh\id_ed25519.pub   # the public key to paste into Nebius
  ```
- [ ] **After the merge:** the platform work (sessions, SQLite, encrypted tokens, webhooks, the nightly job) is on
  `main`. The first deploy can go out before that, but then it runs the single shared demo user.

The Nebius CLI has no Windows build: the installer supports only Linux and macOS. Nothing below needs it. If you
want it, use **Cloud Shell** in the console (a browser terminal with the CLI already signed in), or install it on
the VM. On a machine with a browser, `nebius profile create` signs in through your Nebius account in the browser.

## 3. Prices and sources

All checked on 2026-10-23.

| Fact | Source |
|---|---|
| CPU price: $0.015 per vCPU-hour + $0.0045 per GiB-hour (`cpu-d3`); billed per second; a stopped VM pays no compute | https://docs.nebius.com/compute/resources/pricing |
| `network_ssd` disk: $0.071 per GiB per 730 hours; no HDD type | https://docs.nebius.com/compute/resources/pricing |
| Smallest CPU preset is `2vcpu-8gb`; no shared or burstable sizes | https://docs.nebius.com/compute/virtual-machines/types |
| Public IP address and traffic: free | https://nebius.com/prices, https://docs.nebius.com/vpc/resources/pricing |
| A dynamic IP is released after the VM is stopped for over an hour; a static IP stays until the VM is deleted | https://docs.nebius.com/compute/virtual-machines/network |
| Default CPU quota is 0 in `eu-north1` and `us-central1`, and 200 vCPUs in `us-north1`, `eu-west1` and others | https://docs.nebius.com/compute/resources/quotas-limits |
| Ubuntu 24.04 image `ubuntu24.04-driverless`; the 22.04 image can't be used for new disks | https://docs.nebius.com/compute/storage/boot-disk-images |
| The default security group allows all traffic in and out | https://docs.nebius.com/vpc/security-groups/overview |
| Serverless endpoints: disk wiped on stop or restart; settings fixed after creation | https://docs.nebius.com/serverless/endpoints/manage, https://docs.nebius.com/serverless/maintenance/stop-start |
| Serverless Jobs have no schedule option | https://docs.nebius.com/serverless/jobs/manage |
| CLI: Linux and macOS only; sign-in with `nebius profile create` | https://docs.nebius.com/cli/install, https://docs.nebius.com/cli/configure |
| $25 first payment; budgets are alerts only | https://docs.nebius.com/signup-billing/sign-up, https://docs.nebius.com/signup-billing/budgets |
| Builders Program credits: Token Factory and Tavily only | https://nebius.com/builders-terms-and-conditions |
| sslip.io works and is the same service as nip.io; Let's Encrypt raised its limit for these names | https://nip.io |
| Caddy gets certificates by itself when the name points at the server and ports 80 and 443 are open | https://caddyserver.com/docs/automatic-https |

Not verified: whether static IPs are free in every case (the price list just says "Public IP address: Free"), and
the minimum boot disk size (the docs use 10 GiB in their example).

## 4. Step by step

### Step 1. Create the VM **[You]**

In the Nebius console: **Compute → Virtual machines → Create resource → Virtual machine**.

1. **Project:** pick the **us-north1** project. Each new account gets one project per region. Don't use
   `eu-north1` or `us-central1`: their default CPU quota is 0.
2. **Compute:** platform **Without GPUs**, type **Regular**, platform `cpu-d3`, preset `2vcpu-8gb`. Name: `clawback`.
3. **Storage:**
   - Boot disk: new disk, image **Ubuntu 24.04 LTS** (`ubuntu24.04-driverless`), type `network_ssd`, **20 GiB**.
   - Add a second disk: new disk, `network_ssd`, **10 GiB**, name `clawback-data`. (Optional; see section 1.)
4. **Network:** the default network and subnet. **Public IP address → Auto assign static IP.**
5. **Configuration → Access → Username and SSH key → Create:** a username such as `madhav` (not `root` or
   `admin`), and paste the public key from section 2. Then **Add credentials**.
6. **Review → Create VM.**

Write down the **public IP address**, for example `203.0.113.7`. The backend's host name is that address with
dashes, plus `.sslip.io`: `203-0-113-7.sslip.io`. In the rest of this runbook, `HOST` means that name.

### Step 2. Copy the setup script to the VM **[Script]**

From the repo folder on the laptop (PowerShell or Git Bash):

```bash
scp deploy/vm/setup.sh madhav@203.0.113.7:
ssh madhav@203.0.113.7
```

On the VM, find the data disk's name. It is the 10 GiB disk with no partitions, usually `/dev/vdb`:

```bash
lsblk
```

### Step 3. First run of the setup script **[Script]**

```bash
sudo DATA_DEVICE=/dev/vdb bash setup.sh
```

Leave out `DATA_DEVICE=/dev/vdb` if you skipped the data disk. The script formats the data disk only if it has
no filesystem yet.

This first run installs Python, git, SQLite and Caddy, creates a `clawback` user, makes a deploy key, and stops.
It prints a line that starts with `ssh-ed25519`. Copy that line.

### Step 4. Add the deploy key on GitHub **[You]**

On GitHub, in the ClawBack repo: **Settings → Deploy keys → Add deploy key**.
- Title: `clawback-vm`.
- Key: the `ssh-ed25519 ...` line from step 3.
- Leave **Allow write access** unticked. The VM only ever reads.

### Step 5. Second run of the setup script **[Script]**

```bash
sudo DATA_DEVICE=/dev/vdb bash setup.sh
```

This run clones the repo into `/opt/clawback/app`, installs the backend into `/opt/clawback/venv`, writes
`/etc/clawback/clawback.env` from `deploy/vm/clawback.env.example`, starts the `clawback` service, configures Caddy
for `https://HOST`, and opens ports 22, 80 and 443 in Ubuntu's firewall. It fills in the host name and a fresh
`CLAWBACK_SECRET_KEY` by itself.

To use a different branch, add `BRANCH=<name>`. To use nip.io instead of sslip.io, add
`CLAWBACK_HOST=203-0-113-7.nip.io`.

### Step 6. Put the keys on the VM **[You]**

```bash
sudo nano /etc/clawback/clawback.env
```

Fill in `NEBIUS_API_KEY`, `TAVILY_API_KEY`, `NYLAS_CLIENT_ID`, `NYLAS_API_KEY`, `PLAID_CLIENT_ID` and
`PLAID_SECRET`. Copy the values from `backend/.env` on the laptop. Paste them only into this file: never into a
chat, an issue or a commit. Leave `FRONTEND_ORIGIN` for step 9.

Then:

```bash
sudo systemctl restart clawback
curl https://HOST/api/health
```

The health check should show `"ok": true` and `true` for each service you added a key for. The first HTTPS request
can take a few seconds while Caddy gets the certificate.

**After the merge:** add the new settings from the platform work to the same file (webhook secrets, daily spend
caps). Copy their exact names from `backend/.env.example` once it lands.

### Step 7. Back up the secret key **[You]**

```bash
sudo grep CLAWBACK_SECRET_KEY /etc/clawback/clawback.env
```

Keep that value in a password manager. Without it, the saved tokens in the database can't be decrypted, and every
visitor would have to connect again.

### Step 8. Deploy the frontend on Vercel **[You]**

In Vercel: **Add New → Project → Import** the ClawBack repo, then:

| Setting | Value |
|---|---|
| Framework preset | Next.js (detected) |
| Root directory | `frontend` |
| Node.js version | 24.x (Settings → Build and Deployment → Node.js Version). Next.js 16 needs 20.9 or newer, and Vercel offers 22.x and 24.x. |
| Build and install commands | the defaults |
| Environment variable | `NEXT_PUBLIC_API_URL` = `https://HOST` (no slash at the end), for Production and Preview |

`NEXT_PUBLIC_API_URL` is built into the pages, so changing it needs a new deployment.

Vercel gives the project a production URL such as `https://clawback.vercel.app`. Vercel's default Standard
Protection asks for a Vercel login on every URL except the production domain, so give judges the production URL.
Under **Settings → Deployment Protection**, check the scope is Standard Protection and not All Deployments.

### Step 9. Point the backend at the frontend **[Script]**

On the VM, set the production URL, with `https://` and no slash at the end:

```bash
sudo sed -i 's|^FRONTEND_ORIGIN=.*|FRONTEND_ORIGIN=https://clawback.vercel.app|' /etc/clawback/clawback.env
sudo systemctl restart clawback
```

### Step 10. Register the callback and webhook URLs **[You]**

See [section 7](#7-callback-and-webhook-urls) for the exact list. Today only the Nylas callback is needed. The
two webhooks come **after the merge**.

### Step 11. Smoke test **[You]**

- [ ] `https://clawback.vercel.app` loads, and the front page shows live numbers.
- [ ] The dashboard loads the demo month. The browser console shows no CORS errors.
- [ ] **Connect email** opens the Nylas page, and after sign-in you land back on the dashboard with
      `?connected=email`. Use a test inbox, not anyone's real mail.
- [ ] **Connect bank** opens Plaid Link. Pick a test bank and sign in with `user_good` / `pass_good`.
- [ ] **Find cheaper** and **Prepare cancel** show Nemotron rows in the trace.
- [ ] **After the merge:** a second browser (or a private window) gets its own session and its own demo month.
- [ ] **After the merge:** a saved draft appears in the test inbox's drafts folder.
- [ ] `sudo systemctl restart clawback`, then reload the dashboard: the session's data is still there.

### Step 12. Turn on the nightly job **[Script]**, after the merge

Once `clawback.nightly` is on `main`, run `update.sh` (section 5). It turns the timer on by itself. Check it:

```bash
systemctl list-timers clawback-nightly.timer
sudo systemctl start clawback-nightly      # run it once now
journalctl -u clawback-nightly -n 50
```

## 5. Updating the backend

On the VM:

```bash
sudo bash /opt/clawback/app/deploy/vm/update.sh          # the current branch
sudo bash /opt/clawback/app/deploy/vm/update.sh main     # or a named branch
```

It backs up the SQLite file into `/var/lib/clawback/backups` (it keeps the last 7), fetches the branch, resets the
checkout to it, reinstalls dependencies, reinstalls the systemd units, restarts the service, waits for the health
check and turns on the nightly timer once the job exists. It resets rather than merges, because nobody edits code
on the VM and the history may be rewritten before the repo goes public.

Useful commands:

```bash
systemctl status clawback
journalctl -u clawback -f              # API logs
sudo tail -f /var/log/caddy/clawback.log
```

## 6. How the VM gets the code

The repo is private, so the VM needs a way in.

| Option | How | For | Against |
|---|---|---|---|
| **Deploy key (recommended)** | `setup.sh` makes an SSH key on the VM; you add the public half on GitHub as a read-only deploy key | One click on GitHub, then `update.sh` pulls on its own. Works the same after the repo goes public. Nothing to install on the laptop. | Gives the VM read access to the whole repo, including `backend/.env` while it is still tracked |
| Copy from the laptop | `git archive` on the laptop, `scp` to the VM, `update.sh --archive` | No GitHub change | Every update is a manual copy. This laptop has `scp` but not `rsync`. |

**Recommendation: the deploy key.** Updates during judging become one command on the VM. Remove the key on GitHub
after Dec 15.

The copy route, if you need it:

```bash
# on the laptop, from the repo folder
git archive --format=tar.gz -o clawback.tar.gz HEAD
scp clawback.tar.gz deploy/vm/setup.sh madhav@203.0.113.7:
# on the VM, the first time
sudo mkdir -p /opt/clawback/app && sudo tar -xzf clawback.tar.gz -C /opt/clawback/app
sudo SKIP_CLONE=1 DATA_DEVICE=/dev/vdb bash setup.sh
# on the VM, later updates
sudo bash /opt/clawback/app/deploy/vm/update.sh --archive ~/clawback.tar.gz
```

## 7. Callback and webhook URLs

Register these after the backend has its HTTPS name. `HOST` is the sslip.io name from step 1.

| What | URL | Where to register it | When |
|---|---|---|---|
| Nylas callback URI | `https://HOST/api/connect/email/callback` | Nylas Dashboard → the app → **Hosted authentication → Callback URIs**. It must match `EMAIL_REDIRECT_URI` exactly. Keep the `http://localhost:8000/...` entry for local work. | Now |
| Nylas webhook | `https://HOST/api/ingest/email/webhook` | Nylas Dashboard → **Notifications → Create webhook**, trigger `message.created` (plus any others the handler supports) | After the merge |
| Plaid webhook | `https://HOST/api/ingest/plaid/webhook` | Not in the Plaid Dashboard. The backend sends it as `webhook` in `/link/token/create`, so it is a backend setting. Banks linked before the setting existed get no webhook until they reconnect. | After the merge |

The paths come from `backend/clawback/main.py`. The platform work may move or keep them; check `main.py` after the
merge.

Notes on the webhooks:
- **Nylas checks a new webhook once.** It sends a `GET` with a `challenge` query parameter and expects that exact
  value back as the body, within 10 seconds. Today the route only takes `POST` and answers 501, so creating the
  webhook now would fail, and Nylas doesn't retry. Create it only after the merged handler answers the challenge.
  If it fails anyway, delete the webhook and create it again.
- Nylas shows the webhook secret once, when it is created. Put it in `/etc/clawback/clawback.env` under the name the
  platform work uses, then restart.
- Nylas signs each notification with `X-Nylas-Signature` (HMAC-SHA256 of the raw body). Plaid offers optional
  verification. The handlers should check both.
- Nothing needs registering for Plaid OAuth redirects: the demo uses the Sandbox test banks only.
- Vercel needs no callback URLs.

## 8. Frontend origin and CORS

`FRONTEND_ORIGIN` (`frontend_origin` in `backend/clawback/config.py`) is used in two places:
- `backend/clawback/main.py`: the CORS middleware allows exactly that one origin.
- `backend/clawback/connect.py`, `finish_email()`: after the email sign-in, the browser is sent back to
  `{FRONTEND_ORIGIN}/dashboard`.

So, today:
- Set it to the **production** Vercel URL. The dashboard then works there.
- **Preview deployments won't work against this backend**: each one has its own `*.vercel.app` origin, and CORS
  blocks it. That is fine for judges, who get the production URL.

**Suggested change, after the merge:** let CORS allow both the production origin and the previews.
- Read `FRONTEND_ORIGIN` as a comma-separated list. CORS allows all of them, and the first one stays the place the
  email sign-in returns to.
- Add an optional `FRONTEND_ORIGIN_REGEX` for previews, passed to the middleware's `allow_origin_regex`, for
  example `^https://clawback-[a-z0-9-]+\.vercel\.app$`.
- If the session id comes back in a response header, the middleware must also list it in `expose_headers`, or the
  browser can't read it. The request header (`X-ClawBack-Session`) is already allowed, because `allow_headers` is
  `*`.

## 9. The nightly job

- Nebius Serverless Jobs have no schedule option, so the VM runs the job with a systemd timer:
  `deploy/vm/clawback-nightly.timer` starts `deploy/vm/clawback-nightly.service` every day at
  `03:00 America/Los_Angeles`. systemd follows daylight saving time. `Persistent=true` runs a missed job after the
  VM was off at 3:00.
- The service runs `python -m clawback.nightly` with the same settings file as the API.
- **After the merge, check one thing:** the job runs as its own process beside the API, on the same SQLite file.
  The platform code must allow that (for example SQLite's WAL mode, and the API not holding stale copies in
  memory). If it doesn't, the job should call the running API instead.

## 10. Stopping it after judging

- Keep it running until judging ends on Dec 15.
- Then **[You]**: in the console, delete the VM, both disks and the static IP. Stopping the VM alone still bills the
  disks.
- Remove the deploy key on GitHub, and the hosted callback URI and webhooks in Nylas.
- The privacy policy says the server and its database are deleted when the demo closes.

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `curl https://HOST` fails with a certificate error | Caddy couldn't get a certificate: port 80 or 443 closed, or the name doesn't match the IP | `journalctl -u caddy -n 50`; check the IP in the name; check the VM's security group |
| 502 from Caddy | the API is down | `journalctl -u clawback -n 80` |
| The dashboard shows a CORS error | `FRONTEND_ORIGIN` doesn't match the page's origin exactly | fix it in the settings file (https, no slash at the end), then restart |
| Nylas says the redirect URI isn't allowed | the callback URI isn't registered, or differs from `EMAIL_REDIRECT_URI` | register the exact URL from section 7 |
| Email sign-in returns with "expired" | the API restarted during the sign-in: sign-in state is kept in memory | connect again |
| Health shows `false` for a service | its key is missing from the settings file | add it, then restart |

## 12. The container route (not used)

`backend/Dockerfile` and `backend/.dockerignore` build the backend as a container, for a container host such as a
Nebius serverless endpoint.
- Build from the backend folder: `docker build -t clawback-backend backend`. This laptop has no Docker, so build it
  elsewhere, for example on the VM or in Cloud Shell.
- The image never contains `backend/.env`. It reads settings from environment variables only
  (`CLAWBACK_DOTENV=0`), and keeps the database and connections under `/data`. Mount a volume there.
- It runs one uvicorn worker on port 8000.
- On a Nebius endpoint, `/data` would have to be a shared filesystem volume, and each settings change would mean a
  new endpoint with a new URL (see section 1).

## 13. Before the repo goes public

The repo has to be public to submit. `backend/.env` is tracked on purpose while it is private, so the team can share
test keys. Those keys are in the git history too. Do all of this, in order, before changing the visibility.

1. **[You] Regenerate every key** in `backend/.env`, and delete the old ones in each dashboard:
   - Nebius Token Factory: a new API key, then delete the old key;
   - Tavily: a new API key, then delete the old one;
   - Nylas: a new API key for the app, then delete the old one (the client id can stay);
   - Plaid: rotate the Sandbox secret under **Developers → Keys**.
2. **[You]** Put the new keys into `/etc/clawback/clawback.env` on the VM and into each teammate's local
   `backend/.env`. Restart the VM's service. Share the new keys outside git.
3. **[Script]** Stop tracking the file, and keep the local copy:
   ```bash
   git rm --cached backend/.env
   ```
4. **[Script]** In `.gitignore`, delete the `!backend/.env` line and the two comment lines above it. `.env` stays
   ignored by the rules above them.
5. **[Script]** Commit both changes.
6. **Remove the old keys from the history.** Rotating them already makes them useless, but they shouldn't stay
   readable. Pick one:
   - **Rewrite the history (keeps the build timeline).** In a fresh mirror clone:
     ```bash
     pip install git-filter-repo
     git clone --mirror git@github.com:MadhavMandala/ClawBack.git clawback-mirror
     cd clawback-mirror
     git filter-repo --invert-paths --path backend/.env
     git push --force --mirror origin
     ```
     **[You]** Every teammate then deletes their clone and clones again. The VM's `update.sh` already copes with
     rewritten history. Old commits can stay reachable on GitHub through cached pull request views; rotating the
     keys in step 1 is what makes that harmless.
   - **Publish from a fresh repo with one squashed commit.** Create a new empty public repo, then from a clean
     checkout of `main`:
     ```bash
     git archive --format=tar.gz -o ../clawback-public.tar.gz HEAD
     mkdir ../clawback-public && cd ../clawback-public && tar -xzf ../clawback-public.tar.gz
     git init -b main && git add -A && git commit -m "ClawBack"
     git remote add origin git@github.com:MadhavMandala/<new-repo>.git && git push -u origin main
     ```
     This loses the commit history, which shows the project was built during the hackathon.
7. **[Script] Check that no key is left anywhere in the history.** This prints only the names of keys it finds,
   never their values. Run it with the *old* `backend/.env` saved somewhere outside the repo:
   ```bash
   python - /path/to/old.env <<'PY'
   import subprocess, sys
   keys = {}
   for line in open(sys.argv[1], encoding="utf-8-sig"):
       name, _, value = line.strip().partition("=")
       if value and len(value) >= 12 and not name.startswith("#"):
           keys[name] = value
   history = subprocess.run(["git", "log", "-p", "--all"], capture_output=True, text=True, errors="replace").stdout
   found = [name for name, value in keys.items() if value in history]
   print("old keys still in history:", found or "none")
   PY
   ```
8. **[Script] Check nothing private is tracked.** Read the whole list and make sure only source, docs, the license
   and the example settings files are there: no `.env`, no database, no token files, no personal notes.
   ```bash
   git ls-files
   git ls-files | grep -Ei '(^|/)\.env$|\.db$|\.sqlite|connections\.json|\.local/'   # should print nothing
   git status --ignored --short                                                       # what stays local
   ```
9. **[You]** On GitHub: **Settings → General → Danger Zone → Change repository visibility → Public.**
10. **[You]** Check that GitHub shows "MIT license" in the repo's About panel.
11. The VM's deploy key keeps working after the repo goes public. Remove it after Dec 15.
