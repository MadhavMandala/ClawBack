# Deploying ClawBack

This is the runbook for the hosted demo: the backend on `oracle-hermes`, an Oracle Cloud VM the team already runs,
and the frontend on Vercel. Both addresses are free: `https://157-151-180-120.sslip.io` for the backend and a
`*.vercel.app` address for the site.

The backend was first planned for Nebius AI Cloud. [Section 14](#14-the-nebius-ai-cloud-plan-not-used) keeps that
plan and says why it changed. The hackathon rule is met either way: the backend calls NVIDIA Nemotron models through
Nebius Token Factory at runtime, and the rules let the frontend and the rest of the backend be hosted anywhere.

Each step is marked:
- **[You]**: a person must do it: signing in, adding a key, approving something, or pasting secrets.
- **[Script]**: a script or a command you can copy. It needs no decisions.

## 1. The plan

| Part | Where | How |
|---|---|---|
| Backend API | `oracle-hermes`: Oracle Cloud, region `us-ashburn-1`, shape `VM.Standard.A1.Flex` (2 ARM cores, 12 GB), Ubuntu 24.04 | already running, and shared with other services |
| HTTPS | the same VM | Caddy with a free Let's Encrypt certificate for `157-151-180-120.sslip.io`, listening on the private address `10.0.0.213` only |
| Process | the same VM | a systemd service running uvicorn on `127.0.0.1:8000`, one worker, as its own `clawback` user |
| Database | the same VM | the SQLite file in `/var/lib/clawback`, on the boot disk |
| Nightly job | the same VM | a systemd timer at 3:00 AM Pacific running `python -m clawback.nightly` |
| Logs | the same VM | ClawBack's own journal (`journalctl --namespace=clawback`), kept for 14 days |
| Code | GitHub, public since Oct 28 | an archive copy for now; the VM can clone over HTTPS (section 6) |
| Frontend | Vercel, Hobby plan | root directory `frontend`, `NEXT_PUBLIC_API_URL=https://157-151-180-120.sslip.io` |
| Models | Nebius Token Factory | the backend calls it with `NEBIUS_API_KEY` |

In the rest of this runbook, `HOST` means `157-151-180-120.sslip.io`: the VM's public IP with dashes, plus
`.sslip.io`.

**Cost: $0.** The VM already exists, sslip.io and Let's Encrypt are free, and so is Vercel's Hobby plan.

### What's different about this VM

`oracle-hermes` already runs other services. `setup.sh` works around them by itself:
- **Port 443 may be taken.** If another program already listens on it on a different address, Caddy listens on
  the VM's private address `10.0.0.213` instead, which is where Oracle forwards the public IP, and the other
  program keeps working. The script notices the busy port and picks the address; `BIND_ADDR` overrides it.
- **The firewall is iptables, not ufw.** Oracle's Ubuntu images come with iptables rules that turn away everything
  except SSH, and Oracle warns that ufw can stop an instance from booting. The script adds two rules (ports 80 and
  443) just above the reject rule, both live and in `/etc/iptables/rules.v4`. It backs that file up first, as
  `rules.v4.before-clawback`.
- **Oracle has a second firewall** in the cloud network (the subnet's security list). Ports 80 and 443 must be
  opened there by hand: step 1.
- **Nothing else is upgraded or restarted.** Packages already on the VM keep their versions, and needrestart only
  lists the services it would restart.
- **Logs:** the 14-day limit the privacy policy promises applies to ClawBack's own journal, not to the logs of
  the VM's other services.
- **Isolation:** the API runs as the `clawback` user with `ProtectHome=yes` and a read-only system. It can't read
  `/home` or write outside `/var/lib/clawback`.

## 2. Before you start

- [ ] **[You]** Access to the Oracle Cloud console for the account that owns `oracle-hermes`.
- [ ] **[You]** Admin access to the GitHub repo, to add a deploy key.
- [ ] **[You]** A Vercel account connected to GitHub.
- [ ] **[You]** Access to the Nylas and Plaid dashboards.
- [ ] **[You]** A working Nebius Token Factory key, with Zero Data Retention on. Section 13 lists every key and where
      it comes from.
- [ ] **[Script]** SSH from the laptop works: `ssh oracle-hermes` (the host is in `~/.ssh/config`).

## 3. Facts and sources

Checked on 2026-10-28.

| Fact | Source |
|---|---|
| The VM: Ubuntu 24.04.4, Python 3.12.3, ARM (`aarch64`), 2 cores, 12 GB of memory with about 5 GB free, 69 GB of disk free | on the VM |
| Port 443 is in use on another address; ports 80, 2019 and 8000 are free | `ss -tlnp` on the VM |
| The saved iptables rules are Oracle's defaults (SSH only, then reject); other services add theirs at boot | `/etc/iptables/rules.v4` on the VM |
| "Do not use Uncomplicated Firewall (UFW) to edit firewall rules on an Ubuntu image" | https://docs.oracle.com/en-us/iaas/Content/Compute/References/bestpracticescompute.htm |
| Caddy's `bind` directive limits a site to given addresses | https://caddyserver.com/docs/caddyfile/directives/bind |
| A journal namespace has its own settings file, `journald@NAMESPACE.conf`; a unit joins it with `LogNamespace=` | `man journald.conf`, `man systemd.exec` |
| sslip.io works and is the same service as nip.io; Let's Encrypt raised its limit for these names | https://nip.io |
| Caddy gets certificates by itself when the name points at the server and ports 80 and 443 are open | https://caddyserver.com/docs/automatic-https |

## 4. Step by step

### Step 1. Open ports 80 and 443 in Oracle's cloud firewall **[You]**

In the Oracle Cloud console: **Compute → Instances → oracle-hermes →** the primary VNIC's **Subnet → Security
Lists →** the list in use **→ Add Ingress Rules**. Add two rules:

| Source CIDR | IP protocol | Destination port |
|---|---|---|
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |

If the instance uses a network security group instead, add the same two rules there. Do this before step 5: Caddy
asks Let's Encrypt for a certificate as soon as it starts, and Let's Encrypt has to reach ports 80 and 443.

### Step 2. Copy the setup script to the VM **[Script]**

From the repo folder on the laptop (PowerShell or Git Bash):

```bash
scp deploy/vm/setup.sh oracle-hermes:
ssh oracle-hermes
```

### Step 3. First run of the setup script **[Script]**

```bash
sudo bash setup.sh
```

This first run installs whatever is missing of Python's venv, git, SQLite and Caddy, creates a `clawback` user, makes
a deploy key, and stops. It prints a line that starts with `ssh-ed25519`. Copy that line.

### Step 4. Add the deploy key on GitHub **[You]**

On GitHub, in the ClawBack repo: **Settings → Deploy keys → Add deploy key**.
- Title: `clawback-vm`.
- Key: the `ssh-ed25519 ...` line from step 3.
- Leave **Allow write access** unticked. The VM only ever reads.

### Step 5. Second run of the setup script **[Script]**

```bash
sudo bash setup.sh
```

This run:
- clones the repo into `/opt/clawback/app` and installs the backend into `/opt/clawback/venv`;
- writes `/etc/clawback/clawback.env` from `deploy/vm/clawback.env.example`, filling in the host name and a fresh
  `CLAWBACK_SECRET_KEY`;
- starts the `clawback` service and the nightly timer, logging to ClawBack's own 14-day journal;
- opens ports 80 and 443 in iptables;
- sets up Caddy for `https://HOST` on `10.0.0.213`.

To run a different branch, add `BRANCH=<name>`. To use nip.io instead of sslip.io, add
`CLAWBACK_HOST=157-151-180-120.nip.io`.

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

See [section 7](#7-callback-and-webhook-urls) for the exact list. The Nylas callback is required. The two webhooks
are optional: without them, the nightly job and the **Sync** button keep the data current.

### Step 11. Smoke test **[You]**

- [ ] `https://clawback.vercel.app` loads, and the front page shows live numbers.
- [ ] The dashboard loads the demo month. The browser console shows no CORS errors.
- [ ] **Connect email** opens the Nylas page, and after sign-in you land back on the dashboard with
      `?connected=email`. Use a test inbox, not anyone's real mail.
- [ ] **Connect bank** opens Plaid Link. Pick a test bank and sign in with `user_good` / `pass_good`.
- [ ] **Find cheaper** and **Prepare cancel** show Nemotron rows in the trace.
- [ ] A second browser (or a private window) gets its own session and its own demo month.
- [ ] A saved draft appears in the test inbox's drafts folder.
- [ ] `sudo systemctl restart clawback`, then reload the dashboard: the session's data is still there.

### Step 12. Check the nightly job **[Script]**

`setup.sh` turns the timer on. Check it, and run the job once:

```bash
systemctl list-timers clawback-nightly.timer
sudo systemctl start clawback-nightly      # run it once now
journalctl --namespace=clawback -u clawback-nightly -n 50
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
journalctl --namespace=clawback -u clawback -f    # API logs: time, address, path and status of each request
journalctl -u caddy -n 50                         # HTTPS and certificates
```

## 6. How the VM gets the code

The repo was private until Oct 28, so the VM needed a way in. Now that it's public, the VM can clone over HTTPS
with no key at all:

```bash
sudo mv /opt/clawback/app /opt/clawback/app.copy && sudo REPO=https://github.com/MadhavMandala/ClawBack.git bash setup.sh
```

The options below were written while it was private.

| Option | How | For | Against |
|---|---|---|---|
| **Deploy key (recommended)** | `setup.sh` makes an SSH key on the VM; you add the public half on GitHub as a read-only deploy key | One click on GitHub, then `update.sh` pulls on its own. Works the same after the repo goes public. Nothing to install on the laptop. | Gives the VM read access to the whole repo |
| Copy from the laptop | `git archive` on the laptop, `scp` to the VM, `update.sh --archive` | No GitHub change | Every update is a manual copy. This laptop has `scp` but not `rsync`. |

**Recommendation: the deploy key.** Updates during judging become one command on the VM. Remove the key on GitHub
after Dec 15.

**What's in place (Oct 28):** the first deploy used the copy route, because adding a deploy key needs a person's OK
on GitHub. The VM's key already exists. To switch to it, add the line from
`sudo cat /opt/clawback/.ssh/clawback_deploy.pub` on GitHub (step 4), then on the VM:

```bash
sudo mv /opt/clawback/app /opt/clawback/app.copy && sudo bash setup.sh
```

The copy route, if you need it:

```bash
# on the laptop, from the repo folder
git archive --format=tar.gz -o clawback.tar.gz HEAD
scp clawback.tar.gz deploy/vm/setup.sh oracle-hermes:
# on the VM, the first time
sudo mkdir -p /opt/clawback/app && sudo tar -xzf clawback.tar.gz -C /opt/clawback/app
sudo SKIP_CLONE=1 bash setup.sh
# on the VM, later updates
sudo bash /opt/clawback/app/deploy/vm/update.sh --archive ~/clawback.tar.gz
```

## 7. Callback and webhook URLs

Register these after the backend has its HTTPS name. `HOST` is the sslip.io name from step 1.

| What | URL | Where to register it | Needed? |
|---|---|---|---|
| Nylas callback URI | `https://HOST/api/connect/email/callback` | Nylas Dashboard → the app → **Hosted authentication → Callback URIs**. It must match `EMAIL_REDIRECT_URI` exactly. Keep the `http://localhost:8000/...` entry for local work. | Yes |
| Nylas webhook | `https://HOST/api/ingest/email/webhook` | Nylas Dashboard → **Notifications → Create webhook**, trigger `message.created` `grant.expired` and `grant.deleted` | Optional |
| Plaid webhook | `https://HOST/api/ingest/plaid/webhook` | Not in the Plaid Dashboard. The backend sends it as `webhook` in `/link/token/create`, so it is a backend setting. `clawback.env` sets `PUBLIC_API_URL` to `https://HOST` for this. Banks linked before it was set get no webhook until they reconnect. | Optional |

The paths come from `backend/clawback/main.py`.

Notes on the webhooks:
- **Nylas checks a new webhook once.** It sends a `GET` with a `challenge` query parameter and expects that exact
  value back as the body, within 10 seconds. The `GET` route does that (`email_webhook_challenge` in `main.py`). If
  the check fails anyway, delete the webhook and create it again: Nylas doesn't retry.
- Nylas shows the webhook secret once, when it is created. Put it in `/etc/clawback/clawback.env` as
  `NYLAS_WEBHOOK_SECRET`, then restart. Until it's set, the `POST` route answers 501.
- Nylas signs each notification with `X-Nylas-Signature` (HMAC-SHA256 of the raw body). Plaid offers optional
  verification. The handlers should check both.
- Nothing needs registering for Plaid OAuth redirects: the demo uses the Sandbox test banks only.
- Vercel needs no callback URLs.

## 8. Frontend origin and CORS

`FRONTEND_ORIGIN` (`frontend_origin` in `backend/clawback/config.py`) is used in two places:
- `backend/clawback/main.py`: the CORS middleware allows the listed origins.
- `backend/clawback/connect.py`, `finish_email()`: after the email sign-in, the browser is sent back to the first
  origin's `/dashboard`.

So:
- Set it to the **production** Vercel URL. It can be a comma-separated list; the first one is where the email
  sign-in returns.
- Vercel preview deployments each have their own `*.vercel.app` origin. To let them call the API, set
  `FRONTEND_ORIGIN_REGEX`, for example `https://clawback-[a-z0-9-]+\.vercel\.app`. Judges only need the
  production URL.

## 9. The nightly job

- The VM runs the job with a systemd timer: `deploy/vm/clawback-nightly.timer` starts `deploy/vm/clawback-nightly.service` every day at
  `03:00 America/Los_Angeles`. systemd follows daylight saving time. `Persistent=true` runs a missed job after the
  VM was off at 3:00.
- The service runs `python -m clawback.nightly` with the same settings file as the API.
- The job runs as its own process beside the API, on the same SQLite file. `backend/clawback/db.py` opens it in WAL
  mode with a busy timeout, and the job keeps the API's change when both touch the same user (`SaveConflict` in
  `nightly.py`).

## 10. Stopping it after judging

Keep it running until judging ends on Dec 15. Then remove ClawBack and leave the rest of `oracle-hermes` as it was.
The privacy policy promises the database is deleted when the demo closes.

**[Script]** On the VM:

```bash
sudo systemctl disable --now clawback clawback-nightly.timer caddy   # Caddy serves only ClawBack on this VM
sudo rm -rf /var/lib/clawback /etc/clawback /opt/clawback               # the database, settings, code and venv
sudo rm -f /etc/systemd/system/clawback.service /etc/systemd/system/clawback-nightly.* /etc/systemd/journald@clawback.conf
sudo journalctl --namespace=clawback --rotate && sudo journalctl --namespace=clawback --vacuum-time=1s
sudo systemctl daemon-reload && sudo userdel clawback
# close ports 80 and 443 again: live, then in the saved rules
sudo iptables -D INPUT -p tcp -m state --state NEW -m tcp --dport 80 -j ACCEPT
sudo iptables -D INPUT -p tcp -m state --state NEW -m tcp --dport 443 -j ACCEPT
sudo sed -i -E '/^-A INPUT -p tcp -m state --state NEW -m tcp --dport (80|443) -j ACCEPT$/d' /etc/iptables/rules.v4
```

**[You]**:
- In the Oracle console, delete the two ingress rules from step 1.
- Remove the deploy key on GitHub, and the hosted callback URI and webhooks in Nylas.
- Delete the Vercel project, or leave it showing the front page only.

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `curl https://HOST` fails with a certificate error or times out | Caddy couldn't get a certificate: port 80 or 443 is closed in Oracle's security list or in iptables | Check step 1; `sudo iptables -L INPUT -n --line-numbers` should list ports 80 and 443 above the REJECT rule; `journalctl -u caddy -n 50` |
| Caddy won't start: "address already in use" | another program took port 443 or 80 on the address Caddy uses | `sudo ss -tlnp 'sport = :443'`; run `setup.sh` again, or set `BIND_ADDR` to the private address |
| 502 from Caddy | the API is down | `journalctl --namespace=clawback -u clawback -n 80` |
| The dashboard shows a CORS error | `FRONTEND_ORIGIN` doesn't match the page's origin exactly | fix it in the settings file (https, no slash at the end), then restart |
| Nylas says the redirect URI isn't allowed | the callback URI isn't registered, or differs from `EMAIL_REDIRECT_URI` | register the exact URL from section 7 |
| Email sign-in returns with "expired" | the API restarted during the sign-in: sign-in state is kept in memory | connect again |
| Health shows `false` for a service | its key is missing from the settings file | add it, then restart |
| Find cheaper or Prepare cancel fails; the logs show 401 from Token Factory | the Nebius key was revoked or mistyped | a new key in `NEBIUS_API_KEY`, then restart |

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

The repo has to be public to submit. Until Oct 28, `backend/.env` was tracked on purpose while the repo was private,
so the team could share test keys.

**Done on 2026-10-28** (steps 1 to 6):
- Every key was replaced. The old Nebius, Nylas and Plaid keys no longer work (checked: 401, 401 and
  `INVALID_API_KEYS`). The old Tavily key belongs to Ishani's Tavily account; delete it there.
- `backend/.env` is no longer tracked, and `.gitignore` ignores it.
- `git filter-repo` removed `backend/.env` from every commit on all 8 branches, which were then force-pushed. A
  check of every commit and stored object found none of the old or new key values.
- **Still visible:** pull requests #1 to #7 keep their original commits on GitHub, so they still show the old file.
  Only GitHub Support can remove those. The Nebius, Nylas and Plaid keys in them are dead; the old Tavily key
  still worked on Oct 28, so delete it in Ishani's Tavily account.

**Made public on 2026-10-28**, after steps 7 and 8: no old or current key in any branch's history, and no private
file tracked. The old Tavily key was still live then (see above).

1. **[You] Regenerate every key** in `backend/.env`, and delete the old ones in each dashboard.

   | Key | Who made it | Where it comes from | Status (Oct 28) |
   |---|---|---|---|
   | `NEBIUS_API_KEY` | Ishani, Oct 22 | Nebius Token Factory: https://tokenfactory.nebius.com, **API keys** | Replaced. Check Zero Data Retention is on for the account the new key belongs to. |
   | `TAVILY_API_KEY` | Ishani, Oct 22 | Tavily: https://app.tavily.com, **API Keys** | Replaced. Delete the old key in Ishani's Tavily account. |
   | `NYLAS_API_KEY` | Madhav, Oct 22 | Nylas Dashboard: https://dashboard-v3.nylas.com, the ClawBack app, **API Keys** | Replaced; the old one answers 401 |
   | `NYLAS_CLIENT_ID` | Madhav, Oct 22 | Nylas Dashboard, the app's overview page | Not a secret; it stays |
   | `PLAID_SECRET` | Madhav, Oct 22 | Plaid Dashboard: https://dashboard.plaid.com/developers/keys, **Rotate** on the Sandbox secret | Rotated; the old one is rejected |
   | `PLAID_CLIENT_ID` | Madhav, Oct 22 | the same page | Not a secret; it stays |
   | `CLAWBACK_SECRET_KEY` | made by `setup.sh` on the VM | `/etc/clawback/clawback.env`; never in git | Nothing: it was never committed. Keep the backup from step 7 |
   | `NYLAS_WEBHOOK_SECRET` | Nylas, when the webhook is created | `/etc/clawback/clawback.env`; never in git | Nothing, unless it leaks |

   The Nylas grants and Plaid tokens that visitors create are stored encrypted on the VM, never in git.
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

## 14. The Nebius AI Cloud plan (not used)

Until 2026-10-28 the plan was one CPU VM on Nebius AI Cloud (`cpu-d3`, preset `2vcpu-8gb`, Ubuntu 24.04, region
`us-north1`) with a 10 GiB data disk. It moved to `oracle-hermes` because the team already runs that VM, and no
hackathon credit covers AI Cloud: the same setup would have cost about $81 through judging. The notes stay here
because the AI Cloud part of `docs/token-factory-feedback.md` draws on them. They were checked on 2026-10-23.

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

### Why a VM and not a serverless endpoint (Nebius)

Nebius Serverless AI Endpoints can run a plain FastAPI container on CPU, always on, with a managed HTTPS URL. They
fit this app worse than a VM:
- The container's disk is wiped on every stop or restart. SQLite would need a separate shared filesystem volume.
- The image, settings and environment variables can't be changed after creation. A change means a new endpoint,
  and a new endpoint gets a **new URL**, which breaks the registered Nylas callback and webhooks.
- The default container disk is 250 GiB, which raises the cost to about $107 unless it is set smaller.

A VM keeps the same URL, IP address and database all the way to Dec 15. The Nebius web
console covers every step from Windows. The container files are still in the repo (see [section 12](#12-the-container-route-not-used)).

### The Nebius CLI

The Nebius CLI has no Windows build: the installer supports only Linux and macOS. Nothing below needs it. If you
want it, use **Cloud Shell** in the console (a browser terminal with the CLI already signed in), or install it on
the VM. On a machine with a browser, `nebius profile create` signs in through your Nebius account in the browser.

### Prices and sources (Nebius)

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
