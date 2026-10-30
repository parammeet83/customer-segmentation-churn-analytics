# Deployment

## Target architecture (free tiers only)

| Component | Service and plan | Notes |
|---|---|---|
| Database | **Neon Free**, in a new project used only by CustomerPulse | 1 GB storage per project, 100 CU-hours per project per month, scale-to-zero after 5 minutes (checked against neon.com/docs/introduction/plans on 2026-10-30). The results data is a few MB. |
| API | **Vercel Hobby**, project `customerpulse-api`, root directory `backend/` | Zero-config FastAPI: Vercel finds `app` in `backend/app.py`. Core dependencies only (about 50 MB, well within the 500 MB function bundle limit). |
| Frontend | **Vercel Hobby**, project `customerpulse-web`, root directory `frontend/` | Static Vite build; SPA rewrites in `frontend/vercel.json` |
| Analysis | local machine, or the manual GitHub Actions workflow `Analysis (manual)` | Never on Vercel |
| CI | GitHub Actions (public repository) | |

**Rules:**

* Never enable billing, add a payment method, start a trial or upgrade.
* Don't reuse any other project's Neon database, Vercel project or secrets.
* If a step asks for payment, stop. Every step below works on the free plans.

## Current status

| Item | Status |
|---|---|
| Local end-to-end: pipeline → PostgreSQL 17 → API → dashboard | **Working and verified** |
| CI on GitHub Actions | **Green** (run `41064961471`) |
| Neon project | **Not created.** Needs the owner to sign in to Neon |
| Vercel projects | **Not created.** Needs the owner to sign in to Vercel |
| Live URLs | None yet; none are claimed |

Account authorisation can't be done by an automated assistant, and
credentials must never be pasted into chat. The owner completes the steps
marked 🔐 below.

## Step-by-step

### 1. Neon database 🔐

1. Sign in at https://console.neon.tech (Free plan).
2. **Create project.** Name it `customerpulse`, choose Postgres 17, and pick
   the region nearest to the Vercel functions (for example AWS
   `us-east-1`/`iad1`, or `eu-central-1` with Vercel `fra1`). Create the
   database `customerpulse`.
3. Open **Connect**. Copy the connection string for the default owner role.
   This is the *admin* URL. Paste it **only** into your local `.env` as
   `ADMIN_DATABASE_URL=...`. Don't paste it into chat or commit it.
4. In `.env`, set three new random passwords. Generate each one with:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(24))"
   ```

   Store them as `CP_MIGRATOR_PASSWORD`, `CP_WRITER_PASSWORD` and
   `CP_READER_PASSWORD`. Neon requires at least 60 bits of entropy; these
   are about 190 bits.
5. Create the roles and schema, then migrate. Run this from `backend/`:

   ```bash
   uv run customerpulse setup-roles
   ```

   Then build the role URLs in `.env`. Use the same host and database as the
   admin URL, with `?sslmode=require`:

   ```
   MIGRATOR_DATABASE_URL=postgresql://cp_migrator:<CP_MIGRATOR_PASSWORD>@<host>/customerpulse?sslmode=require
   WRITER_DATABASE_URL=postgresql://cp_writer:<CP_WRITER_PASSWORD>@<host>/customerpulse?sslmode=require
   DATABASE_URL=postgresql://cp_reader:<CP_READER_PASSWORD>@<pooler-host>/customerpulse?sslmode=require
   ```

   For the API (`DATABASE_URL`), use the **pooled** host, the one containing
   `-pooler`. Then run:

   ```bash
   uv run alembic upgrade head
   uv run --extra analysis customerpulse persist
   ```

### 2. GitHub `production` environment 🔐 (optional)

This is only needed to run `Analysis (manual)` with **persist** enabled.

1. Go to **Settings → Environments → production → Environment secrets**.
2. Add `WRITER_DATABASE_URL`, `MIGRATOR_DATABASE_URL` and
   `CUSTOMERPULSE_PSEUDONYM_SECRET`. Use the same secret as your local
   `.env`, so customer keys stay stable.
3. Optionally, add yourself as a *required reviewer* and limit the
   environment to the `main` branch.

### 3. Vercel API project 🔐

1. Sign in at https://vercel.com (Hobby).
2. **Add New → Project**, import
   `parammeet83/customer-segmentation-churn-analytics`, and name the project
   `customerpulse-api`.
3. Set **Root Directory** to `backend`. Vercel detects FastAPI from `app.py`.
4. Under **Environment Variables** (Production):
   * `DATABASE_URL`: the reader URL, using the pooled host.
   * `CORS_ORIGINS`: leave this as a placeholder for now. Set it to the
     frontend URL after step 4.
5. Deploy, then check `https://<api-domain>/api/v1/health`. It should return
   `{"status":"ok","database":"ok",...}`.

### 4. Vercel frontend project 🔐

1. **Add New → Project**, import the same repository again, and name it
   `customerpulse-web`.
2. Set **Root Directory** to `frontend`. Vercel detects Vite, and
   `vercel.json` provides the SPA rewrites and headers.
3. Add the environment variable `VITE_API_BASE_URL=https://<api-domain>`.
   This is a public URL, not a secret.
4. Deploy. Then set the API's `CORS_ORIGINS=https://<web-domain>` and
   redeploy the API.

### 5. Production smoke test

```bash
API=https://<api-domain>
curl -fsS $API/api/v1/health
curl -fsS "$API/api/v1/summary" | python -c "import json,sys; d=json.load(sys.stdin); print(d['run']['run_id'], d['kpis']['test_roc_auc'])"
curl -s -o /dev/null -w "%{http_code}\n" "$API/api/v1/customers?page_size=1000"    # expect 422
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$API/api/v1/summary"            # expect 405
curl -s -D - -o /dev/null -H "Origin: https://evil.example" "$API/api/v1/health" | grep -i access-control || echo "no CORS for foreign origin (good)"
```

Then open the dashboard and check every page on desktop and phone. The
sidebar should show the served run ID.

## Free-tier notes and limits

* **Neon scale-to-zero:** the first request after 5 idle minutes waits for
  the compute to start (cold start, typically under a few seconds). The API
  returns `503` with a safe message if the database is unreachable, and the
  dashboard offers a retry.
* **Neon compute:** 100 CU-hours per month is far more than this read-only,
  low-traffic API needs.
* **Vercel Hobby:** for personal, non-commercial use. Functions use Fluid
  compute with the plan's default duration limits; every API query here
  completes in under 1 second.
* **GitHub Actions:** free for public repositories. The analysis workflow
  takes a few minutes, with a 45-minute timeout.

## Rollback and re-analysis

* Each analysis run is stored separately. If a new run fails, the API keeps
  serving the previous successful run, and the sidebar warns about the failed
  attempt.
* To roll back, delete the bad run's row from `analysis_runs` using an admin
  or writer connection. Child rows cascade.
