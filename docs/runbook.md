# Runbook: environmentdashboard.org

Free-tier stack:
- **Cloudflare Pages**: the static Next.js export.
- **Cloudflare R2**: raw snapshots and the exports we may show but not redistribute.
- **Cloudflare** DNS, Single Redirect rules and Web Analytics.
- **GitHub Actions**: CI, the weekly data refresh and deploys.
- **Zenodo**: quarterly data releases with DOIs.
- **Internet Archive**: Wayback captures of source pages.

The target running cost is about $2/month, which is the domain renewals. Secrets live in the macOS Keychain and are
piped from it, never pasted.

## One-time setup

Do these in order. Steps marked **(owner)** need a person with the accounts; Claude can do the rest once the
tokens exist.

### 1. Domains onto Cloudflare (owner)

Both domains are registered at Moniker, use Moniker nameservers, and renew in April 2027.

1. In Cloudflare, add the zones `environmentdashboard.org` and `environmentdashboard.com` (free plan, same account).
2. At Moniker, turn DNSSEC off if it is on. Then replace the nameservers of both domains with the two Cloudflare
   gives for each zone.
3. When both zones show **Active**, delete any apex and `www` records Cloudflare imported from Moniker.

### 2. Cloudflare tokens and account (owner creates; Claude stores)

| Keychain service | What it is | Where it goes |
|---|---|---|
| `cloudflare-api-token-envdash-deploy` | API token: Account › Cloudflare Pages › Edit | GitHub secret `CLOUDFLARE_API_TOKEN` |
| `cloudflare-api-token-envdash-admin` | API token: Zone › DNS Edit, Zone › Single Redirect Edit, Zone › Zone Settings Edit (both zones); Account › R2 Edit; Account › Cloudflare Pages Edit | Local only (one-time setup below) |
| `r2-envdash-access-key-id`, `r2-envdash-secret-access-key` | R2 S3 API token (Object Read & Write on both envdash buckets) | GitHub secrets `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` |

The account ID is not secret. Store it as the repo variable `CLOUDFLARE_ACCOUNT_ID`.

```bash
security add-generic-password -U -a "$USER" -s cloudflare-api-token-envdash-deploy -w '<token>' -j "Cloudflare Pages edit, environmentdashboard"
security add-generic-password -U -a "$USER" -s cloudflare-api-token-envdash-admin -w '<token>' -j "Cloudflare DNS/redirects/R2 admin, environmentdashboard (local only)"
security add-generic-password -U -a "$USER" -s r2-envdash-access-key-id -w '<id>' -j "R2 S3 key id, envdash buckets"
security add-generic-password -U -a "$USER" -s r2-envdash-secret-access-key -w '<secret>' -j "R2 S3 secret, envdash buckets"
```

Also (owner):
- **Subscribe to R2** in the dashboard. It needs a payment method even within the free tier.
- Add a **billing notification at $5**.
- Create a **Web Analytics** site for `environmentdashboard.org` and put its token in the repo variable
  `NEXT_PUBLIC_CF_BEACON_TOKEN`.
- Turn on **Email Routing** for `hello@environmentdashboard.org` to your inbox.

### 3. Cloudflare resources (Claude, with the admin token)

- Pages project `environmentdashboard` (direct upload), with custom domain `environmentdashboard.org`.
- Redirect placeholders: proxied `AAAA 100::` records for `www.environmentdashboard.org`, `environmentdashboard.com` and
  `www.environmentdashboard.com`.
- Single Redirect rules, each a 301 that preserves the query string. Always Use HTTPS stays off in both zones so
  every case is one hop; HSTS comes from `_headers`.
  - `.org` zone: if the host is `www.environmentdashboard.org`, or the scheme is `http` on `environmentdashboard.org`,
    redirect to `concat("https://environmentdashboard.org", http.request.uri.path)`.
  - `.com` zone: redirect every host and scheme to the same target.
- R2 buckets `envdash-public` and `envdash-private`, with r2.dev access disabled on both.
- `envdash-public` gets the custom domain `files.environmentdashboard.org`, a Cache Rule (cache everything, edge TTL
  1 year, because keys are content-addressed) and one rate-limiting rule on that host. CORS on that bucket is GET/HEAD
  from any origin.

Then seed the private bucket once, from a machine that has run the pipeline (CI pulls these before every build):

```bash
cd pipeline
export R2_ACCESS_KEY_ID=$(security find-generic-password -s r2-envdash-access-key-id -w)
export R2_SECRET_ACCESS_KEY=$(security find-generic-password -s r2-envdash-secret-access-key -w)
export CLOUDFLARE_ACCOUNT_ID=<account id>
uv run envdash private push && uv run envdash archive
```

### 4. Data-source credentials (owner creates the accounts; Claude stores the keys)

| Keychain service | For | GitHub secret |
|---|---|---|
| `archive-org-s3-access`, `archive-org-s3-secret` | Internet Archive Save Page Now (archive.org/account/s3.php) | `IA_ACCESS`, `IA_SECRET` |
| `earthdata-envdash` | NASA Earthdata token (NASA-SSH sea level, GRACE) | `EARTHDATA_TOKEN` |
| `eia-api-key` | US EIA API v2 | `EIA_API_KEY` |
| `gfw-api-key` | Global Forest Watch Data API | `GFW_API_KEY` |
| `cmems-envdash` | Copernicus Marine (ocean pH) | `CMEMS_CREDENTIALS` |
| `zenodo-envdash` | Zenodo token with `deposit:write`, `deposit:actions` | `ZENODO_TOKEN` |

Also (owner), by email:
- ch.datainfo@idmc.ch: request an IDMC API key. Until it arrives, IDMC is a manual source.
- faostat@fao.org (not yet sent): ask which PRIMAP-hist version and terms apply to the non-farm items of Emissions
  totals (GT: Energy, IPPU, Waste, Other), which FAO's note says are PRIMAP-hist v2.4 (CC BY) while the October 2025
  values match v2.7 (CC BY-NC-SA); and whether the IEA and other third-party inputs behind pre- and post-production
  and on-farm energy use (IEA activity data and grid emission factors, EDGAR v7 cold-chain F-gases) carry
  restrictions. Record the answer in `docs/sources.md` and in `pipeline/sources/faostat.yaml` and
  `faostat-all-sectors.yaml`.

### 5. GitHub

- Create the Environment `production`, limited to `main`. Put every secret above in it.
- Pipe secrets from the Keychain, never paste them:
  `security find-generic-password -s cloudflare-api-token-envdash-deploy -w | gh secret set CLOUDFLARE_API_TOKEN --env production`
- Variables: `CLOUDFLARE_ACCOUNT_ID`, `NEXT_PUBLIC_CF_BEACON_TOKEN`.
- Never use `pull_request_target`.

### 6. Launch (milestone 7)

1. Make the repo public, after running gitleaks over the whole history.
2. In Zenodo › GitHub, switch on `abhartia/environment-dashboard`, then cut release `v2026.10`.
3. Add Search Console and Bing Webmaster properties for `https://environmentdashboard.org` (DNS TXT records) and
   submit the sitemap.

## Day to day

- **Local:**
  - `cd pipeline && uv run envdash refresh` (fetch → build → validate → status);
  - `cd web && npm run dev -- --port 3200`;
  - `npm run build && npx serve out` to see the static export.
- **Add a source:** read `docs/sources.md`. Licence first: write `pipeline/sources/<id>.yaml` with the terms quoted,
  then the transform and its fixture.
- **A file a host won't serve to scripts:** download it by hand, then run
  `uv run envdash snapshot add --source <id> --artifact <artifact> --file <path> --note "downloaded by <who> from <url>"`.
- **A refresh failed:** each failed source has one issue labelled `source:<id>`. The site keeps that source's last
  validated vintage, and `/status` says so. Fix the transform or the registry entry, then run
  `gh workflow run data-refresh.yml`.
- **Rollback a deploy:** in the dashboard, Pages › environmentdashboard › Deployments › Rollback (or redeploy an older
  commit with `gh workflow run deploy-web.yml --ref <sha>`). For a bad data vintage, also `git revert` the data
  commit so the next refresh does not redeploy it.
- **Correct a mistake:** add an entry to `data/errata.yaml` (kind `our-error` or `method-change`) in the same commit
  as the fix.
- **Rotate a key:** create the new key, `security add-generic-password -U …` to replace it, pipe it into
  `gh secret set …` again, then revoke the old key.

### Registry features and housekeeping commands

Every command is listed in `pipeline/README.md`; these are the ones that come up when adding or repairing a source.

- **A file whose name changes on a schedule** (a month or date in the name, a new folder each month): give the
  artifact a `discover` rule instead of a `url`: the listing page, a `link_pattern` with a named group `key` (or
  `year` and `month`), and optionally a `sublisting_pattern`. The largest key wins; a tie or no match fails the fetch,
  never a guess. `uv run envdash resolve --source <id>` shows what it resolves to today without downloading.
- **A zip rebuilt on every request** (two downloads seconds apart hash differently): set
  `content_key: zip-members` (plus `member_name_ignore` if the producer stamps the date into member names). A fetch
  whose member fingerprint is unchanged keeps the current snapshot, so no false new vintage is recorded.
- **An API that needs a key:** `access.auth: api-key`, `access.auth_env: <ENV_VAR>` and either `key_header` or
  `key_query`. The key lives in the Keychain (table in step 4), is exported into the environment for a local run
  (`export GFW_API_KEY=$(security find-generic-password -s gfw-api-key -w)`) and reaches CI as a GitHub secret. A
  missing variable fails that source with its name, never silently.
- **A new country, station or aggregate code:** declare it in `pipeline/src/envdash/geo.py` (`STATIONS`,
  `AGGREGATES`, `EXTRA_TERRITORIES`, or a source's alias table) and run `uv run envdash geo build`; unknown codes
  raise.
- **A fresh checkout or runner:** `uv run envdash snapshots pull` restores from R2 every snapshot the build and the
  snapshot tests need, each checked against its sha256 (R2 variables as in step 3). It fails, naming them, for
  snapshots never archived: run `uv run envdash archive` where those bytes are and commit
  `pipeline/manifests/snapshots/`. Do this once by hand before the first scheduled data refresh, which pulls before it
  fetches.
- **After a registry change:** `uv run envdash docs licensing` regenerates `docs/licensing.md`; a test fails until it
  matches the registry.
