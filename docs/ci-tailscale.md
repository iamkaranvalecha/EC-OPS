# CI via Tailscale — setup guide

The EC-OPS CI workflow runs the test suite against the **developer's local
PostgreSQL** over a Tailscale tunnel — no hosted database is provisioned in
GitHub Actions. This keeps the CI environment identical to the local one.

---

## How it works

1. The GitHub Actions runner installs the Tailscale client and authenticates
   using a pre-authorised key (`TAILSCALE_AUTHKEY`).
2. Once the Tailscale network is up, the runner can reach the developer's
   machine directly (by its Tailscale IP or MagicDNS hostname).
3. The workflow waits until PostgreSQL is reachable on that address before
   running tests.
4. Tests run with `DATABASE_URL` and `TEST_DATABASE_URL` pointing at the local
   Postgres instance — exactly the same databases used during development.

---

## Prerequisites on your machine

- [Tailscale](https://tailscale.com/download) installed and logged in.
- Your machine must be **online and connected to Tailscale** whenever a CI
  run is triggered. If your machine is offline, the wait step times out after
  ~60 seconds and the test job fails.
- PostgreSQL must be running and accepting connections from the Tailscale
  network interface (see [Postgres Tailscale access](#postgres-tailscale-access)
  below).

---

## Step 1 — Create a Tailscale auth key

1. Open the [Tailscale admin console](https://login.tailscale.com/admin/settings/keys).
2. Click **Generate auth key**.
3. Options:
   - **Reusable**: yes (allows multiple CI runs).
   - **Ephemeral**: yes (runner nodes are removed from the tailnet automatically
     after they disconnect — keeps your device list clean).
   - **Tags**: add `tag:ci` (optional but recommended — lets you write ACL
     rules scoped to CI runners).
4. Copy the key — it is only shown once.

---

## Step 2 — Add GitHub Actions secrets

Go to your repository → **Settings → Secrets and variables → Actions → Secrets**
and add:

| Secret name | Value |
|---|---|
| `TAILSCALE_AUTHKEY` | The auth key from Step 1 |
| `DB_URL` | `postgresql+asyncpg://postgres:<password>@<tailscale-ip>:5432/ecops` |
| `TEST_DB_URL` | `postgresql+asyncpg://postgres:<password>@<tailscale-ip>:5432/ecops_test` |

Replace `<tailscale-ip>` with your machine's Tailscale IP address (found in
the Tailscale app or by running `tailscale ip -4` on your machine). You can
also use your MagicDNS hostname (e.g. `my-mac.tail1234.ts.net`).

> **Tip:** Use the same credentials as your local `.env` — just swap
> `localhost` for the Tailscale IP/hostname.

---

## Step 3 — Postgres Tailscale access

By default PostgreSQL only listens on `localhost`. To accept connections from
the Tailscale interface:

1. Find `postgresql.conf` (usually `/etc/postgresql/<version>/main/` on Linux,
   or check `SHOW config_file;` in psql).
2. Set:
   ```
   listen_addresses = 'localhost,<tailscale-ip>'
   ```
   Or use `'*'` to listen on all interfaces (then restrict via `pg_hba.conf`).
3. In `pg_hba.conf`, add a line allowing connections from the Tailscale CIDR
   (check `tailscale ip -4` and your subnet, typically `100.64.0.0/10`):
   ```
   host    all    all    100.64.0.0/10    scram-sha-256
   ```
4. Reload Postgres: `sudo pg_ctlcluster <version> main reload` (Linux) or
   restart the service on Windows/macOS.

---

## Skipping tests on a PR

The test job (`Test`) is controlled by a **repository variable** `RUN_TESTS`.

| `RUN_TESTS` value | Effect |
|---|---|
| *(not set)* or `true` | Tests run (default) |
| `false` | Test job is skipped; lint still runs |

To skip tests:
1. Go to **Settings → Secrets and variables → Actions → Variables**.
2. Set `RUN_TESTS` to `false`.
3. Set it back to `true` (or delete the variable) to re-enable.

This lets a maintainer gate off tests without editing `.github/workflows/ci.yml`.

> **Note:** Skipping tests suppresses the `Test` status check on PRs. If you
> have branch protection rules requiring this check, you may need to adjust them
> or use a different skip mechanism.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| *"Postgres not reachable after 60 seconds"* | Machine offline or Tailscale disconnected | Ensure Tailscale is running on your machine |
| *"FATAL: password authentication failed"* | Wrong password in `DB_URL` secret | Update the secret to match your local Postgres password |
| *"could not connect to server: Connection refused"* | Postgres not listening on Tailscale interface | Check `listen_addresses` and `pg_hba.conf` |
| Test job skipped unexpectedly | `RUN_TESTS` variable set to `false` | Delete the variable or set it to `true` |
| Auth key expired | Tailscale key not reusable or expired | Regenerate and update `TAILSCALE_AUTHKEY` secret |
