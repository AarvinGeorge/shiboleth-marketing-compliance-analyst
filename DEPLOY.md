# Deploying the Adlign demo

> **LIVE since 2026-07-14.** Share link (frontend):
> https://adlign.vercel.app (Vercel project `adlign`). Full-stack fallback:
> https://217.15.168.253.sslip.io (Hostinger VPS, everything below).
> Backend updates ship via `git push` to `main` — see Part 7b. The frontend
> does NOT auto-deploy: this project has no Vercel git integration, so a
> frontend change needs an explicit `vercel --prod` (see Part 7b). Parts 1-7
> are the from-scratch runbook; keep them for rebuilds.
>
> Rename history: the project shipped as `shiboleth`, was renamed to
> `marketing-compliance-analysis-tool` on 2026-07-14, and to `adlign` on
> 2026-07-23 with the product rebrand. Both earlier vercel.app URLs are dead.
>
> The architecture (2026-07-13 plan, now live): Hostinger VPS + Docker Compose.
> Caddy (automatic HTTPS) → Next.js web app + FastAPI (under `/api`) → Postgres.
> The database is pre-seeded with the certified TurboTax demo data.
> API keys live only in one file on the server; the browser never sees them.

```
Visitor's browser
      │  https://your-domain
      ▼
   Caddy  ──────────── /api/* ──▶  FastAPI (LLM calls, keys)  ──▶  Postgres
      │                                                             (seeded
      └──── everything else ──▶  Next.js web app                demo data)
```

Time needed: about 60 to 90 minutes, most of it waiting on builds.
Cost: about $5 to 8 per month for the VPS, plus a domain if you buy one.

---

## Part 0 — What you need before starting

- [ ] A credit/debit card (for Hostinger).
- [ ] Your LLM API keys (the same ones from `code/.env` on this Mac).
- [ ] A terminal on this Mac.

---

## Part 1 — Set spend caps FIRST (10 min)

Do this before anything is public. If someone abuses the demo, the caps are
the real safety net.

1. **Anthropic**: go to https://console.anthropic.com → Settings → Limits →
   set the monthly spend limit to **$10**.
2. **OpenAI**: go to https://platform.openai.com → Settings → Billing →
   Limits → set the monthly budget to **$10**.
3. Google (Gemini) and Groq are on free tiers — nothing to do.

---

## Part 2 — Create the Hostinger account and buy a VPS (15 min)

1. Go to https://www.hostinger.com and click **VPS** in the menu.
2. Pick the plan **KVM 2** (2 vCPU, 8 GB RAM). The 8 GB matters: the app
   runs a headless Chrome for live crawling. Choose the billing period you
   are comfortable with (monthly is fine for a demo).

   > What actually happened (2026-07-14): the live box is a 4 GB KVM 1-class
   > VPS, not the planned 8 GB. Mitigation: a 4 GB swapfile was added on the
   > server. The seeded demo runs fine; live crawls are the only headroom
   > concern. If rebuilding from scratch, still prefer KVM 2.
3. Create the account when prompted (email + password), pay, and continue
   to VPS setup.
4. During setup Hostinger asks a few questions:
   - **Location**: pick a US data center (the audience is US-based).
   - **Operating system**: choose the template **"Ubuntu 24.04 with Docker"**
     if offered. If not, plain **Ubuntu 24.04 LTS** works (step 3.4 installs
     Docker).
   - **Root password**: set one and save it in your password manager.
   - **SSH key**: it may ask for one — you can add it now (see Part 3 step 1
     for how to get it) or later in the panel.
5. When the VPS is ready, the panel shows its **IP address**. Write it down.
   Everywhere below, replace `YOUR_SERVER_IP` with it.

---

## Part 3 — First login and basic security (10 min)

All commands in this part run **on your Mac** unless said otherwise.

1. Create an SSH key if you don't have one yet:

   ```bash
   ls ~/.ssh/id_ed25519.pub || ssh-keygen -t ed25519
   cat ~/.ssh/id_ed25519.pub
   ```

   Copy the printed line into Hostinger: VPS panel → Settings → SSH keys →
   Add SSH key. (If you already added it during setup, skip.)

   > The live setup (2026-07-14) uses a dedicated passphrase-free key
   > `~/.ssh/adlign_deploy` on the Mac, wired into `~/.ssh/config` for
   > this host with `IdentitiesOnly yes`. CI uses its own separate key
   > (the `VPS_SSH_KEY` GitHub secret, Part 7b). The server is keys-only
   > (`PasswordAuthentication no`).

2. Log in to the server:

   ```bash
   ssh root@YOUR_SERVER_IP
   ```

   Type `yes` when asked about the fingerprint. If it asks for a password,
   use the root password from Part 2 — the key will be used next time.

3. **On the server**, turn on the firewall (SSH + web traffic only):

   ```bash
   ufw allow OpenSSH
   ufw allow 80/tcp
   ufw allow 443/tcp
   ufw --force enable
   ```

4. **On the server**, check Docker is there:

   ```bash
   docker --version && docker compose version
   ```

   If that fails (plain Ubuntu image), install it:

   ```bash
   curl -fsSL https://get.docker.com | sh
   ```

5. Optional but recommended once key login works: disable password logins.

   ```bash
   sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
   systemctl restart ssh
   ```

---

## Part 4 — Point a domain at the server (10 min)

Pick ONE of these:

**Option A — no domain, zero cost (fastest):** use sslip.io. Your domain is
simply `YOUR_SERVER_IP.sslip.io` (for example `31.97.55.10.sslip.io`). It
resolves to your server automatically and Caddy still gets a real HTTPS
certificate for it. Nothing to configure — just use that string as `DOMAIN`
in Part 6.

**Option B — real domain (nicer for the portfolio, ~$10/yr):**
1. In Hostinger: Domains → buy one (e.g. `adlign-demo.com`), or use a
   domain you already own.
2. In the domain's DNS settings, add an **A record**:
   - Name/host: `@` (or `demo` if you want `demo.yourdomain.com`)
   - Value: `YOUR_SERVER_IP`
   - TTL: default is fine.
3. Wait a few minutes for DNS to spread.

---

## Part 5 — Copy the app to the server (10 min)

**On your Mac**, from this project's `code/` directory:

```bash
cd "/Users/aarvingeorge/Documents/Climb/Profile_Builder/tech-personal-projects/marketing-compliance-checker/code"

# create the target folder on the server (one time)
ssh root@YOUR_SERVER_IP "mkdir -p /opt/adlign"

# the app itself (excludes local junk and your dev .env)
rsync -av --exclude .git --exclude .venv --exclude node_modules \
  --exclude .next --exclude .env --exclude .worktrees \
  ./ root@YOUR_SERVER_IP:/opt/adlign/code/

# the frozen corpus snapshots (optional, enables corpus-mode re-runs)
rsync -av ../ground-truth root@YOUR_SERVER_IP:/opt/adlign/
```

Notes:
- The demo database seed (`deploy/seed/01_demo.sql.gz`) and the LLM response
  cache ride along automatically — nothing extra to do.
- To update the server later after code changes, just run the same rsync
  again (then see Part 8).

---

## Part 6 — Configure the server environment (10 min)

**On the server:**

```bash
cd /opt/adlign/code
cp deploy/.env.prod.example .env
nano .env
```

Fill in, then save (Ctrl+O, Enter, Ctrl+X):

- `DOMAIN` — from Part 4 (e.g. `31.97.55.10.sslip.io` or `demo.yourdomain.com`).
  No `https://` prefix.
- `POSTGRES_PASSWORD` — any long random string.
- The API keys — copy the values from `code/.env` on your Mac
  (`GOOGLE_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
  `LANGSMITH_API_KEY`).
- The hardening block is pre-set (`PAGE_CAP_MAX=8`,
  `CHECKS_RATE_LIMIT_PER_HOUR=3`). For `PROTECTED_RUN_IDS` paste this exact
  line (the five seeded showcase runs):

  ```
  PROTECTED_RUN_IDS=559e0b158e41480eaa303af9cdc0d550,e9fc612df3d54fd6b035122dd7e7687c,05a9dd009201430ea56ce9f3f21aa0b1,3c09c654b7324415a3af90f7e581718a,13042afce80644d295e14ea559a3b75c
  ```

---

## Part 7 — Launch (20 min, mostly waiting)

**On the server:**

```bash
cd /opt/adlign/code
docker compose -f docker-compose.prod.yml up -d --build
```

The first build takes 5 to 15 minutes (it downloads Chromium). Watch it
settle:

```bash
docker compose -f docker-compose.prod.yml ps        # all should be Up
docker compose -f docker-compose.prod.yml logs -f api   # Ctrl+C to stop watching
```

Then open **https://YOUR-DOMAIN** in a browser and check:

- [ ] The page loads with a padlock (real HTTPS, no warning).
      (Give Caddy a minute on first load — it is fetching the certificate.)
- [ ] The dashboard shows the seeded TurboTax product with hero metrics.
- [ ] Open the product → flags and issue groupings are there.
- [ ] Open a flag → evidence highlights; "View original source" works.
- [ ] Confirm or dismiss a flag → the verified score moves.
- [ ] Deleting a seeded run is refused (that is the protection working).
- [ ] Optional live test: start a new check on a small site — it should
      crawl at most 8 pages, and a 4th run within an hour gets rate limited.

If all boxes tick: **you are live.**

---

## Part 7b — CI/CD (set up 2026-07-14)

Deploys are automated; manual rsync (Part 5) is only for first-time setup
or emergencies.

**How updates ship now: `git push` to `main` does everything.** The repo's
main branch is the source of truth for code AND configuration (pattern A,
Aarvin's call 2026-07-14): every deploy re-renders the server's `.env` from
GitHub Actions secrets plus the non-secret config block at the top of the
workflow file. Nothing on the server or a laptop drives production.

```
git push origin main
   ├─▶ GitHub Actions "deploy-backend": rsync code to the VPS, render
   │   /opt/adlign/code/.env from GitHub secrets, rebuild the Docker
   │   stack, smoke-check /api/health (DB volume untouched)
   └─▶ Vercel git integration: builds apps/web, deploys the frontend
```

- Backend workflow: `.github/workflows/deploy-backend.yml`. Watch runs with
  `gh run list --workflow deploy-backend` or the repo's Actions tab.
- Repo secrets: `VPS_HOST`, `VPS_SSH_KEY` (dedicated CI key; its public
  half is in the VPS `authorized_keys`), `VPS_KNOWN_HOSTS`, plus the real
  secrets the .env render uses: `POSTGRES_PASSWORD`, `GOOGLE_API_KEY`,
  `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
  `LANGSMITH_API_KEY`. Rotate a key = update the GitHub secret, rerun the
  workflow (Actions tab -> deploy-backend -> Run workflow, or push).
- Non-secret config (DOMAIN, caps, PROTECTED_RUN_IDS, CORS_ALLOW_ORIGINS)
  lives in the workflow's `env:` block — edit in git, never on the server.
- CAUTION: `POSTGRES_PASSWORD` in GitHub must stay equal to the password
  the pgdata volume was initialized with, or the api loses the DB. To
  change it, change it in Postgres first, then in the GitHub secret.
- Frontend: Vercel project `adlign` (scope `aarvingeorges-projects`), live
  at https://adlign.vercel.app — the shareable link. Root directory
  `apps/web`, env
  `NEXT_PUBLIC_API_URL=https://217.15.168.253.sslip.io/api` (marked
  sensitive, so it is not readable back via the API — only replaceable).
  Deploys are CLI-driven (`vercel --prod` from `code/`): there is NO git
  integration on this project, despite what earlier notes claimed, so a
  push to main does NOT update the frontend. Verified 2026-07-23.
  The browser calls the VPS API cross-origin; the API allows it via
  `CORS_ALLOW_ORIGINS` in the server `.env`.
- The VPS keeps serving its own full copy (web + api) at the sslip.io
  domain — it is a complete fallback if Vercel is down.
- Vercel preview deployments (non-main branches) get preview URLs that are
  NOT in `CORS_ALLOW_ORIGINS`; their API calls will fail CORS. Add specific
  preview origins to the server `.env` if you ever need one to work.

## Part 8 — Everyday operations

All on the server, from `/opt/adlign/code`:

| What | Command |
|---|---|
| See status | `docker compose -f docker-compose.prod.yml ps` |
| Watch API logs | `docker compose -f docker-compose.prod.yml logs -f api` |
| Restart everything | `docker compose -f docker-compose.prod.yml restart` |
| Deploy new code | normally just `git push origin main` (Part 7b); manual fallback: rsync from Mac, then `docker compose -f docker-compose.prod.yml up -d --build` |
| Stop the demo | `docker compose -f docker-compose.prod.yml down` |
| Wipe the DB and re-seed from the dump | `docker compose -f docker-compose.prod.yml down -v` then `up -d` |

To refresh the seed itself (capture your current local DB into the dump):
run `./deploy/make_seed.sh` on the Mac, rsync again, then wipe + re-seed.

---

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Browser says "connection not private" | Caddy is still getting the certificate — wait 1 to 2 minutes and reload. Still failing? Check `DOMAIN` in `.env` matches the URL exactly and DNS points at the server (`ping YOUR-DOMAIN`). |
| Site unreachable | `ufw status` should show 80 and 443 allowed; `docker compose ... ps` should show caddy Up. Hostinger's panel firewall (if enabled) must also allow 80/443. |
| API container restarting | `logs api` — usually a missing key in `.env` (the app names exactly which key at startup). |
| Dashboard empty | The seed only loads on FIRST boot of an empty DB volume. Fix: `down -v` then `up -d` (this erases any data added since). |
| New check run errors immediately | Corpus mode needs `/opt/adlign/ground-truth` (Part 5's second rsync). Live mode needs no extra files. |
| "Rate limited" while you demo | You hit your own 3-runs-per-hour cap. Either wait, or temporarily raise `CHECKS_RATE_LIMIT_PER_HOUR` in `.env` and `restart`. |
