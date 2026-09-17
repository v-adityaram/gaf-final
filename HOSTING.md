# Hosting this demo for free (Render + Vercel)

The repo is **private**, so GitHub Pages' free tier won't work (it only serves public repos).
Render and Vercel both deploy straight from a private repo instead and just give you a public
URL for the running app — the source stays private either way.

Both connect steps below are one-time, manual (need your GitHub OAuth login in a browser — not
something that can be scripted), and take about 2 minutes each.

## 1. Backend -> Render (`render.yaml` at the repo root)

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
currently down anyway; see the conversation history). Voice stays disabled unless you also fill in
the `AZURE_OPENAI_*` env vars in Render's dashboard.

## 2. Frontend -> Vercel (`frontend/vercel.json`)

1. Go to **vercel.com** -> sign in with GitHub -> **Add New** -> **Project**.
2. Import the `gaf-final` repo. When asked for **Root Directory**, set it to `frontend`.
   Vercel will pick up `frontend/vercel.json` and detect the Vite framework automatically.
3. Add two **Environment Variables** (Project Settings -> Environment Variables) before deploying:
   - `VITE_API_BASE_URL` = the Render URL from step 1 (e.g. `https://gaf-final-backend.onrender.com`)
   - `VITE_BASE_PATH` = `/` (without this the build assumes the `/gaf/` sub-path the original VM
     deploy used, and every asset 404s on a standalone domain)
4. Deploy. Vercel gives you a URL like `https://gaf-final.vercel.app` -- that's the live demo link.

## 3. Close the loop: let the backend accept requests from the frontend's origin

Back in Render's dashboard, open `gaf-final-backend` -> **Environment** -> set:
```
CORS_EXTRA_ORIGINS=https://gaf-final.vercel.app
```
(comma-separate if Vercel also gives you a preview-deployment domain you want to test from).
Save -> Render redeploys automatically. Without this step the frontend loads but every API call
fails with a CORS error in the browser console.

## 4. Verify

Open the Vercel URL. The Assistant tab should load, the header/sidebar should render, and sending
a message should get a real response (confirms both services + CORS are wired correctly). If a
request hangs for 30-50s the first time, that's Render's free-tier cold start, not a bug.

## Redeploying after future changes

Both Render and Vercel auto-redeploy on every `git push` to `main` once connected — no extra
steps needed for future updates, just push.
