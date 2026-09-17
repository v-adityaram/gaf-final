# GAF Sales Assistant Prototype

An AI assistant for **GAF sales reps** (not customers): one conversation where a rep
types, pastes, forwards an email, or talks, and the right specialist prepares a
priced order, answers a product/warranty question from approved documents, or finds
certified contractors near a customer. Built on the same pattern as `telecom-assistant`:
a fast LLM call classifies/extracts structured fields, then plain Python makes every
business decision against the synthetic GAF catalogue -- pricing, discounts,
inventory, credit, duplicates, confidence gating -- and either templates the reply or
synthesizes it from evidence only. A human always confirms.

```text
Frontend (React/Vite) -> FastAPI backend -> Azure AI Foundry (gpt-5-mini, direct calls)
                                          -> GAF catalogue  (local data/ OR the Function App's /api/gaf/*)
                                          -> Azure OpenAI Realtime API (live call / voice)
```

## What the rep can do

| Feature | Where | How it works |
|---|---|---|
| **Price an order** (single or bulk) | Assistant / Smart Order Helper | Every line priced from `products.json` (unit price x base qty; squares -> bundles), automatic discounts as separate lines (volume 30/60/100+ sq, seasonal promos, Complete-System bonus, distributor allowance), rep commission, credit checked against the order total. |
| **Add-ons** | order form | Rule-based quantities from `add_on_rules.json` (starter 1/10 sq, deck 1/10, leak barrier 1/20, colour-matched ridge cap 1/3, optional vent). Named or "WindProven set" -> included; otherwise suggested with a checkbox. Missing WindProven category is called out. |
| **Roof estimate** | order | "4,000 sq ft two-storey, 6/12 pitch" -> footprint x pitch factor + waste -> proposed squares with assumptions; the rep confirms via quick-reply before an order is built. Lot size alone triggers a clarifying question. |
| **Clarifications** | order | Ambiguous customer/product, missing quantity/unit, unknown ridge-cap colour -> a question with quick replies, never a guess. |
| **Warranty / product answers** | Assistant / Product & Warranty Advisor | Grounded synthesis over KB passages + approval registry + warranty tiers. Deterministic **confidence score**: >= 95 auto-answers, below that the draft goes to the **human review queue** (Metrics tab). Leak/defect -> urgent escalation; nailing/HVHZ/code -> expert escalation. |
| **Contractors** | Assistant | "Certified roofers near 30061, Master Elite" -> directory search by distance/tier with ratings, phone and the warranties each tier can offer. |
| **Customer inbox** | left sidebar | Synthetic emails for the signed-in rep; select one or many -> the Email Agent extracts the request and runs it through the Coordinator like a typed message. |
| **Live call** | left sidebar / mic | WebRTC realtime voice with the same Coordinator tools; live transcript window. |
| **Draft customer email** | right panel | Professional follow-up email from the transcript only, signed by the rep. |
| **Sales rep** | top right | Signed-in rep with accounts, booked sales, commission, quota progress, pipeline and this session's confirmed orders. Orders are credited to the account's own rep. |
| **Demo scenarios** | top right | Prefilled prompts for every use case (`data/demo_scenarios/use_cases.json`). |
| **Product tiles** | inline | Colour swatch, price per square/bundle, website badges. `image_url` in `products.json` swaps in a real photo. |

## Data

`GAF_AI_Prototype_Synthetic_Datasets 1.xlsx` is the source of truth. `python scripts/build_dataset.py`
regenerates `data/*.json` from it (24 products with prices, 18 accounts, 6 DCs, 144 inventory rows,
45 priced orders, knowledge docs **with full text and citable passages**, add-on rules, counties/ZIPs)
plus the synthetic extensions it needs (76 contractors across 15 ZIPs, discounts, 4 sales reps, inbox
emails, use cases). `python scripts/validate_demo_data.py` checks it all adds up.
See `data/DEMO_DATA_GUIDE.md` for a presenter's tour.

Both transports serve identical envelopes through one shared module, `backend/app/services/gaf_catalog.py`:

- `GAF_DATA_SOURCE=local` (default) reads `data/` from disk -- fully offline.
- `GAF_DATA_SOURCE=live` calls the Function App. `python scripts/build_function_app_zip.py` produces
  `Telecom-POC-deploy-with-GAF-v2.zip` from the original deploy zip: telecom routes byte-identical,
  GAF routes rewritten over `gaf_catalog.py` + `gaf_data/*.json`. Deploy that zip to the Function App.

```text
/api/gaf/products  inventory  customers  orders  documents (full content)  kb-passages
/api/gaf/product-approval  warranty-rules  escalation-rules  warehouses  add-on-rules
/api/gaf/discounts  contractors?zip=  zips  counties  sales-reps  emails  use-cases
```

## Quick start

```bash
# backend
cd backend && python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001

# frontend
cd frontend && npm install && npm run dev      # http://localhost:5173/gaf/
```

Copy `.env.example` to `.env` at the repo root and set `FOUNDRY_API_KEY` (and the `AZURE_OPENAI_*`
values for voice). `python scripts/reset_demo_state.py` clears metrics, the confirmed-orders ledger
and the review queue between demos.

## Backend routes (app)

```text
POST /api/assistant/chat        Coordinator -> order | warranty | contractor | general | chat
POST /api/order/chat|recheck|confirm    Smart Order (multi-line, priced), editable-form recheck, human confirm
POST /api/warranty/chat         Product & Warranty (confidence + review queue)
GET  /api/reviews  POST /api/reviews/{id}/resolve
POST /api/email/intake  GET /api/inbox          Email Agent
GET  /api/contractors  /api/reps  /api/reps/{id}/dashboard  /api/demo/use-cases
POST /api/assistant/draft-email  /api/assistant/photo  /api/feedback
GET  /api/metrics/*  /api/orders/confirmed
```

## Tests

```bash
cd backend && pytest        # 160 tests, fully offline (LLM and HTTP mocked)
```

## Postman

`postman/GAF_Sales_Assistant.postman_collection.json` covers every backend route (order, warranty,
Coordinator, contractors, reps, inbox/email agent, review queue, metrics, feedback, voice), with
realistic example bodies and a `baseUrl` collection variable (defaults to `http://localhost:8001`
-- point it at a hosted backend instead once you have one). Import it directly into Postman, or
run it headlessly with `npx newman run postman/GAF_Sales_Assistant.postman_collection.json`.

## Hosting a live demo for free

See [HOSTING.md](HOSTING.md) -- Render (backend, either way) + GitHub Pages or Vercel (frontend).
All auto-redeploy on every push once connected.

## Safety behaviours

- An order is never submitted by the model -- `POST /api/order/confirm` is the human gate and a
  confirmable session only exists when Python's own checks say READY.
- No dollar figure, SKU, quantity, stock level or credit figure is ever produced by a model; all
  come from the catalogue and deterministic arithmetic.
- Warranty answers use only fetched evidence; NO_SOURCE is withheld; below-threshold confidence is
  queued for a human; leak/defect/nailing/HVHZ wording overrides the classifier.
- Emails and chat text are data, never instructions (prompt-injection attempts are flagged).
