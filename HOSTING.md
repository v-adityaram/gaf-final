# Hosting this demo for free

Two ways to host the **frontend**: GitHub Pages (needs the repo public) or Vercel (works with the
repo staying private). Either way the **backend** needs Render -- both frontend options are
static-only and can't run the FastAPI server.

Every step below is one-time and manual (needs your GitHub OAuth login in a browser -- not
something that can be scripted), and takes about 2 minutes.

## 1. Backend -> Render (`render.yaml` at the repo root, needed either way)

1. Go to **render.com** -> sign in with GitHub -> **New** -> **Blueprint**.
2. Pick the `gaf-final` repo. Render reads `render.yaml` and proposes one service:
   `gaf-final-backend` (free plan, Python, root dir `backend/`).
3. Before the first deploy it'll prompt for the env vars marked `sync: false`. Copy these two
   values from your local `.env` (never commit that file):
   - `FOUNDRY_PROJECT_ENDPOINT`
   - `FOUNDRY_API_KEY`
4. Click **Apply** / **Create**. First deploy takes a few minutes (installs `requirements.txt`).
5. Once live, note the URL Render assigns, e.g. `https://gaf-final-backend.onrender.com`.
   Check `https://<that-url>/api/health` -> should return
   `{"status":"ok","foundry_configured":true,...}`.

**Free-tier catch:** the service spins down after ~15 min idle and cold-starts in 30-50s on the
next request — normal for a demo, just means the first click after a break is slow.

`GAF_DATA_SOURCE` is set to `local` in `render.yaml` -- the backend serves everything from the
`data/*.json` files baked into the repo, no live Azure Function App needed (that Function App is
currently down anyway). Voice stays disabled unless you also fill in the `AZURE_OPENAI_*` env
vars in Render's dashboard.

## 2a. Frontend -> GitHub Pages -- once the repo is public

`.github/workflows/deploy-pages.yml` is already in the repo and builds+deploys the frontend
automatically on every push to `main` that touches `frontend/**`. You still need to:

1. Make the repo public (Settings -> General -> Danger Zone -> Change visibility) -- GitHub
   Pages' free tier only serves public repos.
2. **Settings -> Pages -> Build and deployment -> Source: "GitHub Actions"** (one-time toggle;
   can't be set from a workflow file).
3. **Settings -> Secrets and variables -> Actions -> Variables tab** -> add a repository variable
   `VITE_API_BASE_URL` = the Render URL from step 1 (e.g. `https://gaf-final-backend.onrender.com`).
4. Push anything to `frontend/`, or go to the **Actions** tab -> "Deploy frontend to GitHub Pages"
   -> **Run workflow** to trigger the first deploy without waiting for a push.
5. Once it finishes (green check on the Actions run), the site is at:
   **`https://v-adityaram.github.io/gaf-final/`**

If you skip step 3, the site still deploys and loads, but every chat/order/warranty request
fails in the browser console -- the page would be trying to reach `localhost:8001` on the
*visitor's* own machine, not a real server. Set the variable, then re-run the workflow.

## 2b. Frontend -> Vercel -- works with the repo staying private

1. Go to **vercel.com** -> sign in with GitHub -> **Add New** -> **Project**.
2. Import the `gaf-final` repo. When asked for **Root Directory**, set it to `frontend`.
   Vercel will pick up `frontend/vercel.json` and detect the Vite framework automatically.
3. Add two **Environment Variables** (Project Settings -> Environment Variables) before deploying:
   - `VITE_API_BASE_URL` = the Render URL from step 1
   - `VITE_BASE_PATH` = `/` (without this the build assumes the `/gaf/` sub-path the original VM
     deploy used, and every asset 404s on a standalone domain)
4. Deploy. Vercel gives you a URL like `https://gaf-final.vercel.app` -- that's the live demo link.

## 3. Close the loop: let the backend accept requests from the frontend's origin

Back in Render's dashboard, open `gaf-final-backend` -> **Environment** -> set:
```
CORS_EXTRA_ORIGINS=https://v-adityaram.github.io,https://gaf-final.vercel.app
```
(use whichever origin(s) you actually deployed to; comma-separate if using both, or add a Vercel
preview-deployment domain too). Save -> Render redeploys automatically. Without this step the
frontend loads but every API call fails with a CORS error in the browser console.

## 4. Verify

Open the frontend URL. The Assistant tab should load, the header/sidebar should render, and
sending a message should get a real response (confirms both services + CORS are wired
correctly). If a request hangs for 30-50s the first time, that's Render's free-tier cold start,
not a bug.

## Redeploying after future changes

Render and Vercel both auto-redeploy on every `git push` to `main`. GitHub Pages redeploys on
every push that touches `frontend/**`, or via the manual "Run workflow" button. No extra steps
needed for future updates either way -- just push.
