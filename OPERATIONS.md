# Adlign: Operations, Reliability and Infrastructure

> Living reference. Two parts:
> 1. **Risk register + hardening roadmap**, what can break, and the
>    recommended fix for each, chosen for scalability, reliability and
>    consistency rather than a quick patch.
> 2. **Reusing the VPS for other apps**, capacity, the recommended
>    multi-app architecture, and how to manage it.
>
> Companion to `DEPLOY.md` (the runbook). State captured 2026-07-24 from a
> live audit of the box. Nothing here has been applied to production yet;
> each item is a decision for later.

---

## Part 1: Risk register and hardening roadmap

Priorities: **P1** = will bite eventually, fix when convenient · **P2** =
low probability, real impact, worth a guard · **P3** = accepted for a
portfolio demo, revisit only if the app grows.

### R1 (P1): The whole system is nailed to one IP address

**Problem.** The Vercel frontend has `https://217.15.168.253.sslip.io/api`
compiled into its JavaScript bundle, and the TLS certificate plus the domain
are derived from that same IP through sslip.io. If Hostinger reassigns the IP
(rebuild, migration, plan change, missed payment), three things fail at once:
the domain stops resolving, Caddy cannot renew the cert for the old name, and
the frontend keeps calling a dead address baked into its build.

**Recommended solution: a real domain behind Cloudflare, address by name not
by number.**

1. Register a domain (about $10/year), e.g. `adlign.app`.
2. Put Cloudflare (free tier) in front as authoritative DNS. Create proxied
   records: `app.adlign.app` and `api.adlign.app` → the VPS IP.
3. Point the Vercel frontend's `NEXT_PUBLIC_API_URL` at `https://api.adlign.app`,
   a stable **name**, never an IP.
4. Caddy keeps terminating TLS at the origin with a Let's Encrypt cert for the
   real domain.

**Why this is the right shape, not just a patch:**

| Property | How this delivers it |
|---|---|
| Reliability | If the IP ever changes, you update **one** Cloudflare record. Nothing rebuilds, the cert is unaffected, the frontend never notices. |
| Scalability | A real domain + Cloudflare is the foundation for everything below: subdomains per app, edge caching, blue-green, moving the origin to a bigger box later. |
| Consistency | Frontend and backend both reference the domain. One source of truth for "where is the API," instead of an IP duplicated across the Vercel build, the workflow `DOMAIN`, and `CORS`. |
| Bonus | Cloudflare's proxy hides the origin IP and absorbs basic DDoS/bot traffic for free. |

**Effort:** ~1 hour. **Do this first**, it unblocks R6 and the multi-app plan.

---

### R2 (owner, deferred): LLM spend caps

**Problem.** Live runs call paid models (Anthropic Haiku, OpenAI). Without a
hard console cap, abuse or a runaway loop can spend real money. The app-level
limits already present (`CHECKS_RATE_LIMIT_PER_HOUR=3` per IP, `PAGE_CAP_MAX=8`)
narrow the blast radius but are not the last line of defence.

**Recommended solution: defence in depth, three layers:**
1. **Hard monthly cap** at the Anthropic and OpenAI consoles ($10 each). This
   is the real backstop. *(You are handling this.)*
2. Keep the app-level rate limits (already live).
3. Add a **billing alert** at 50% so you hear about drift before the cap trips.

**Status:** deferred to you. No code change needed; layers 2 and 3 already exist.

---

### R3 (P2): Database password is welded to the storage volume

**Problem.** Postgres bakes `POSTGRES_PASSWORD` into the data volume the first
time it initializes. After that the variable is ignored. If someone rotates the
GitHub secret, the next deploy renders a `.env` whose password no longer matches
the volume, and the API cannot authenticate, the DB effectively disappears,
even though the data is intact.

**Recommended solution: make rotation a deliberate, guarded procedure.**

1. Document the correct order (already partly in `DEPLOY.md`): change it **in
   Postgres first** with `ALTER ROLE ... PASSWORD`, then update the GitHub
   secret. Never the secret alone.
2. Add a **fail-fast gate** to the deploy job: before `docker compose up`
   rebuilds, run a one-line `psql` connectivity check with the rendered
   credentials. If it fails, abort the deploy **before** touching the running
   stack, so a mismatch costs you a red CI run, not a downed database.
3. Longer term, move the password to a Docker secret / external secret store so
   the value lives in exactly one place.

**Why:** reliability comes from catching the mismatch in seconds instead of
after the stack is down; consistency comes from a single documented source of
truth for the live password.

**Effort:** ~30 min for the fail-fast gate (highest value part).

---

### R4 (P2): Base images float; builds are not reproducible

**Problem.** The Dockerfiles pull `python:3.12-slim`, `node:22-alpine`,
`pgvector/pgvector:pg16`, `caddy:2-alpine`, all **moving tags**. Every deploy
runs `--build`, so a routine deploy months from now can pull a base image that
shifted underneath you, and fail or misbehave with **zero change on your side**.
The same code does not necessarily produce the same image twice.

**Recommended solution: pin to digests, update through the CI gate.**

1. Pin each base image to a content digest, e.g.
   `python:3.12-slim@sha256:...`. Builds become deterministic.
2. Add **Dependabot** (or Renovate) for Docker. It opens a PR when a pinned
   base has a new digest. The PR runs through `verify-api` / `verify-web`, so
   updates arrive **tested and reviewed**, never as a surprise mid-deploy.

**Why this beats both extremes:** floating tags give silent drift; manual
pinning-and-forgetting gives security staleness. Pin + auto-update-PR gives
reproducibility **and** controlled freshness, the scalable, consistent answer
that holds as the number of images grows.

**Effort:** ~45 min.

---

### R5 (P2): A pinned LLM model could be retired

**Problem.** Model IDs are pinned for eval reproducibility (`claude-haiku-4-5`,
a pinned Gemini, `llama-3.3-70b`). This already bit once: `gemini-2.5-flash`
started returning 404 for new keys. If a provider retires a pinned model, live
checks fail. (The seeded/corpus demo is unaffected, it replays cassettes.)

**Recommended solution: proactive detection plus a fallback path.**

1. The per-stage model registry is already env-configurable in one module
   (`config.py`), good, that is the consistency foundation.
2. Add a **weekly canary**: a scheduled CI job that runs one real check per
   provider and alerts if any model 404s or errors. You learn about a
   deprecation from a green/red badge, not from a user.
3. Document a **fallback model per stage** so swapping is a one-line env change,
   not an investigation.

**Why:** reliability here is about *time to detection*. A canary turns a
silent future outage into a scheduled heads-up.

**Effort:** ~1 hour for the canary.

---

### R6 (P2): CI gates 188 of 198 tests

**Problem.** Ten tests read data that lives **outside** the repo
(`../ground-truth/`, `../05_shibboleth_*.md`), so they skip on a CI runner. CI
gives real confidence on 188 tests but is blind to regressions in
corpus-loading and the verbatim-seed guarantee, exactly the compliance-
critical paths.

**Recommended solution: make the test data a versioned dependency CI can
fetch, in two tiers.**

1. **Quick win:** vendor the canonical rule text (doc 05 is small) into the
   repo as a test fixture, so `test_seed_verbatim`, the byte-for-byte
   compliance guard, runs in CI. Depends on R1/R7 not at all; do it anytime.
2. **Full fix:** publish the frozen ground-truth set as a **versioned artifact**
   (a release asset or a small tarball) and have CI fetch it, so CI and local
   run the identical suite. Alternatively commit a curated representative
   sample for the corpus tests.

**Why:** the goal is that "green CI" means the same thing everywhere. Fetching
a versioned artifact keeps the big data out of the repo while closing the
false-confidence gap, the consistent, scalable choice over committing 460
records or leaving the tests CI-invisible.

**Effort:** ~30 min for the quick win, ~half a day for the full artifact
pipeline.

---

### Accepted risks (P3): know them, do nothing for now

| Risk | Why it is acceptable | Revisit when |
|---|---|---|
| **No pgdata backup cron.** | The seed dump (`deploy/seed/01_demo.sql.gz`, 2.5MB) is committed, so you can rebuild to the seeded baseline. Only live-created state since the last seed would be lost. | The demo starts holding data you cannot regenerate → add a nightly `pg_dump` to object storage. |
| **1 vCPU / 4GB box; live crawls run headless Chrome.** | Seeded demo is comfortable (containers idle at ~165MB total). Only concurrent live crawls risk OOM; swap covers spikes. | You demo live crawls under load, or add a second app (see Part 2). |
| **`enforce_admins: false` on branch protection.** | Deliberate: keeps an owner escape hatch if CI itself breaks. | The repo gets collaborators → set it `true`. |
| **DB identifiers still named `shiboleth`.** | Internally consistent; invisible to users; renaming a live volume is destructive for zero gain. | Only on a from-scratch rebuild, if desired. |

---

### Suggested order of execution

```
R1  domain + Cloudflare        ← do first, unblocks everything
R6  vendor doc-05 fixture      ← 30 min, closes the compliance-test gap
R3  deploy DB-connectivity gate
R4  pin base images + Dependabot
R5  weekly model canary
R2  spend caps (you)           ← independent, anytime
```

---

## Part 2: Reusing this VPS for another app's backend

**Short answer: yes, viable, for additional low-traffic apps.** The box has
plenty of idle RAM and the current topology is already clean for it. The one
real ceiling is **1 vCPU**, fine for portfolio and demo workloads, not for
apps with real concurrent traffic.

### What the box looks like today (audited 2026-07-24)

| Resource | Total | In use (idle) | Headroom |
|---|---|---|---|
| vCPU | **1** | ~0% idle | The bottleneck under load |
| RAM | 3.8 GB | ~165 MB (all 4 containers) + OS | ~2.9 GB available |
| Swap | 4 GB | ~34 MB | Spillover cushion |
| Disk | 48 GB | 58% used | ~20 GB free |

**Why the topology is already reuse-friendly:** only Caddy publishes host ports
(80/443). The web, api and Postgres containers expose their ports **only inside
the `code_default` Docker network**, never to the host. So a second app cannot
collide on ports, and the two apps are network-isolated by default.

### Recommended architecture: shared edge, isolated apps

Do **not** bolt a second app into Adlign's compose file. Restructure into a
shared ingress tier plus one self-contained stack per app:

```
                Internet (:80 / :443)
                        │
              ┌─────────▼─────────┐
              │   Caddy (edge)    │   /opt/edge , its own compose,
              │  external network │   owns 80/443, routes by hostname,
              │  "edge", 1 owner  │   auto-HTTPS per domain
              └───┬───────────┬───┘
       adlign.app │           │ app2.app
          ┌───────▼──┐    ┌───▼───────┐
          │ adlign    │    │  app2      │   each: own /opt/<app> dir,
          │ web + api │    │  web + api │   own compose project,
          │ own network│    │ own network│   own DB, own repo + CI
          └───────────┘    └───────────┘
```

**The four rules that make this reliable:**

1. **Promote Caddy to a standalone edge tier.** Move it out of Adlign's compose
   into `/opt/edge/` on an **external** Docker network named `edge`. Each app
   attaches its web/api to `edge` so Caddy can reach them, and Caddy routes by
   hostname. This decouples ingress from any one app: deploying or tearing down
   Adlign no longer touches the proxy other apps depend on.

2. **One directory + one compose project + one repo + one CI workflow per app.**
   `/opt/adlign`, `/opt/app2`, each deployed independently by its own pipeline
   (identical pattern to Adlign's `ci-cd.yml`, just a different target dir and
   subdomain). The compose **project name** must be stable per app, it is
   derived from the directory basename, and changing it silently creates new,
   empty volumes.

3. **Set per-container resource limits.** Right now every container has
   `mem_limit=0` (unbounded), on a shared box, one app's runaway can starve
   the others. Give each stack explicit `deploy.resources.limits` (e.g. api
   768MB, web 256MB, Postgres 512MB). This is the single most important
   reliability change for multi-tenancy: it converts "one bad app takes down
   the box" into "one bad app hits its own ceiling."

4. **Database: one shared Postgres, separate databases + roles.** On a 1-vCPU /
   4GB box, running a second full Postgres container is wasteful. Prefer one
   Postgres instance with a database and login role **per app**
   (`CREATE DATABASE app2; CREATE ROLE app2 ...`). Efficient and reasonably
   isolated. Tradeoff to accept: a shared instance means a shared blast radius,
   so cap it with per-role `connection limit` and a memory limit on the
   container. If an app needs hard isolation (different Postgres version, or
   compliance separation), give it its own instance instead.

### Capacity budget: what actually fits

- **RAM:** comfortable. Three or four small app stacks idle well under 3.8 GB.
- **CPU:** the real limit. One core means all apps share one CPU; concurrent
  heavy requests contend. Fine for low-traffic portfolio apps and demos. Not
  fine for anything doing sustained concurrent work (or Adlign's own live
  crawls running at the same time as another app's load).
- **Rule of thumb:** treat this box as a home for **several low-traffic
  services**, not two busy ones. If a second app expects real traffic, either
  resize the VPS (Hostinger KVM 2, 2 vCPU) or move that app to its own box.

### How to manage it day to day

| Concern | Approach |
|---|---|
| Adding an app | New `/opt/<app>` dir, new repo with a `ci-cd.yml` cloned from Adlign's, a new subdomain (one Cloudflare record, see R1), attach to the `edge` network. |
| Deploys | Each app's pipeline touches only its own dir and its own compose project. The edge tier is deployed once and rarely changes. |
| Secrets | Per-app `.env` rendered from **that app's** GitHub secrets, exactly as Adlign does. Never share one `.env` across apps. |
| Isolation | Separate Docker networks per app; only the `edge` network is shared. Resource limits on every container. |
| Backups | Per-app `pg_dump` if the app holds real data (see accepted-risk note). |
| When to graduate off one box | When CPU contention shows up, or you want zero-downtime deploys, move to a 2+ vCPU box, or a managed Postgres, or a small container platform (Fly.io / Railway / a managed k8s). The shared-edge pattern ports directly to any of them. |

### Migration note

Restructuring Adlign onto a shared `edge` network is a **production change with
downtime risk** (it moves the live proxy). It is not done here, this document
is the plan. When you want to execute it, it should be its own branch, tested
against a throwaway second app or a staging box first, and cut over during a
quiet window. The `edge` tier ideally lives in its **own** infra repo once a
second app exists, rather than inside Adlign's.
