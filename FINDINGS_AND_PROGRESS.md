# Findings & Progress — Crestline (formerly "GAF") Customer Service AI

This document is a handoff/continuation record written by Claude (the assistant working in
`C:\Users\vssva\OneDrive\Desktop\telecom\gaf_demo`, part of the `telecom-assistant` monorepo) for
whoever continues work in **this** folder (`gaf_final`), which is a separate, independently-evolved
team project that started from that codebase. It captures the architecture, the reasoning behind
every major decision, what was tried and abandoned, what actually shipped, and a chronological
narrative of the session that produced it — written so a fresh AI session or a new team member can
pick up full context without re-deriving any of it.

**Read this before changing the routing/grounding/orchestration architecture.** Several of the
decisions below look over-engineered until you know the specific failure they were fixing — the
"Why" lines are there so you don't re-introduce a bug that was already found and fixed once.

---

## 1. What this project is, and its relationship to `gaf_final`

- **Origin repo**: `telecom-assistant` (GitHub: `v-adityaram/telecom-assistant`, private), a mature,
  deployed "Telecom AI Assistant" demo. A second demo, "GAF Customer Service AI" (a roofing-company
  chatbot), was built inside it at `gaf_demo/`, deliberately reusing telecom-assistant's own
  architecture pattern and sharing its Azure infrastructure for cost reasons (this is a demo, not a
  product — no security-isolation requirement).
- **This folder (`gaf_final`)** is a **separate, independently-built team project** that started
  from an early snapshot of `telecom-assistant/gaf_demo`'s code (the README here is still
  word-for-word identical to that project's early README) and was then extended independently by a
  team of ~8 people for a demo presentation (see `demo_explanation.txt` — a spoken script split
  across "Person 0" through "Person 7": overview, frontend, backend, architecture ×2, agent
  orchestration ×2, dataset/testing). It has things the origin project doesn't (a Metrics tab, an
  editable order form with "Recheck Order", `data/demo_scenarios/`, a data-validation script) and is
  missing things the origin project has now (it still reads local JSON files instead of a live API,
  still says "GAF" and "Team Lead" — it predates the origin's order-lookup fix and its rebrand to
  "Crestline").
- A public GitHub repo, `v-adityaram/gaf-final`, was found to be a single-commit snapshot pushed
  from **this** local folder's lineage (or one like it) — created 2026-09-15, never updated since.
  It contains no real secrets (only `.env.example`), but is/was public. The user was advised to make
  it private via GitHub's UI (Settings → Danger Zone → Change visibility) since the assistant's
  GitHub token is scoped only to `telecom-assistant` and can't touch it.
- **Bottom line**: these are two parallel implementations of the same brief
  (`GAF_Prototype_Implementation_Plan.md`, present in both folders). Treat them as separate lineages,
  not as something to merge blindly — but the architectural lessons below (especially the grounding
  bug and the Foundry-Agent dead end) apply equally to both, since both are solving the same problem
  with the same underlying platform (Azure AI Foundry).

---

## 2. The core architectural pattern — and why

**Decision**: No "Agent" abstraction. Every assistant is: **one fast LLM call to classify/extract
structured fields → plain deterministic Python resolves business logic against a real API →
either a Python-built template or a second, tightly-grounded LLM call synthesizes the reply.**

This is the *same* pattern `telecom-assistant`'s own chat assistant already used, reused
deliberately rather than reinvented.

**Why not an Azure AI Foundry "Agent" with tool-calling** (this was tried first and abandoned —
important not to redo this):
- The first design had two Foundry Agents (an "order agent" and a "warranty agent") whose system
  prompts described tools like `resolve_customer`, `resolve_product`, `check_order_risks`,
  `create_technical_escalation`.
- **Live-tested finding**: those tools were never actually registered as real callable functions.
  Registering function tools on a Foundry Agent requires a **Foundry Portal step** — there is no way
  to script it with the installed `azure-ai-projects` SDK, which only exposes `get_openai_client`,
  `send_request`, `close`. No agent-management API.
- **Confirmed live**: passing `tools=` directly on `client.responses.create()` while `agent_name=` is
  set is flatly rejected by Foundry: `400 invalid_payload: "Not allowed when agent is specified"`.
- **Concrete failure this caused**: without real tools, the agent improvised — asked to resolve a
  customer, it fired a **web search** for `"resolve_customer Sunshine Roofing Tampa"` instead of
  calling anything real.
- **Conclusion**: for a small, fixed set of lookups like this, direct model calls (no "Agent"
  wrapper) are simpler, ~5x faster (no multi-turn tool-call round trip), fully unit-testable offline
  with zero live Azure credentials, and don't depend on a manual Portal step this environment can't
  automate. `az login` / Entra ID (`DefaultAzureCredential`) is also not usable in this environment —
  auth is API-key only throughout (`FOUNDRY_API_KEY`).

**Model selection**: benchmarked `gpt-5-mini`, `gpt-5.4-nano`, `gpt-4o-mini`, `gpt-4o`, `gpt-5-nano`,
`gpt-5` on the Foundry project actually available — only `gpt-5-mini` (~7-8s plain) and `gpt-5`
(~14s) exist as real deployments there; the rest 404'd (`DeploymentNotFound`). Chose `gpt-5-mini`.
**Critical latency finding**: `reasoning={"effort":"minimal"}` + `text={"verbosity":"low"}` on the
Responses API dropped `gpt-5-mini` from ~7-8s to **~1.7-1.8s** with no loss of correctness on
structured extraction/classification tasks. (Chat Completions API spells the same thing
`reasoning_effort="minimal"`; Responses API needs the nested object form.) Always use these settings
for the fast classify/extract calls.

---

## 3. The grounding bug — a real hallucination, found and fixed twice

This is the single most important lesson in this codebase. Read it before touching the Warranty
Advisor's logic.

**The bug**: asked "Exactly how many years does the StainGuard algae coverage last?" — a fact that
exists in **neither** approved data source — the synthesis model **invented "10 years"** despite an
explicit prompt instruction to use only the provided evidence and say so if it couldn't answer.

**First fix attempt (failed)**: had the *classifier* LLM itself decide booleans like
`needsWarrantyRules` before fetching evidence, trying to gate what evidence even reaches the
synthesis call. **This still failed** — the classifier still said `needsWarrantyRules: true` for the
StainGuard question purely on topical similarity ("coverage" sounds warranty-adjacent), so
irrelevant evidence still reached the synthesis call, which still hallucinated. **Lesson: an LLM's
own judgment about "is this evidence relevant" is not reliable enough to gate what it later sees.**

**Second fix (worked)**: replaced that judgment with **deterministic Python**:
- `needs_approval = bool(product)` — gated only on whether the extraction step found a product name
  (simple NER-style extraction, much more reliable than topical-relevance judgment).
- `needs_rules = bool(_WARRANTY_RULES_KEYWORDS.search(question))` — a **regex keyword match** against
  the question text itself (`warrant\w*|wind\s?proven|standard\s+limited|mph|layerlock|nail\w*|
  leak\s+barrier|deck\s+protection|starter\s+strip|ridge\s+cap|accessor\w*|tier`), not the
  classifier's opinion.
- If neither is true, the synthesis model is **never called at all** — it literally cannot
  hallucinate from evidence it was never given the chance to receive.
- Also hardened the synthesis prompt itself as defense-in-depth: "every fact/number/duration must be
  a literal value in the evidence JSON... if not, that counts as NOT answerable, even if topically
  related", with an explicit `NO_SOURCE` escape hatch the model must return verbatim.
- Also fixed a secondary bug found the same way: the model over-cited an unused "Florida Install
  Guide" document in its Source line even though no fact from it was used — fixed by only passing
  documents actually *tied to fetched evidence* into the synthesis prompt, not the full
  active-documents list.
- Locked in as a permanent regression test with an explicit "the synthesis call must never even be
  invoked" assertion, not just an output-correctness check.

**General principle extracted from this**: whenever an LLM's own judgment is used to decide *whether
something is safe/relevant/in-scope*, prefer a deterministic Python check (regex, presence/absence
of an extracted field, a live-data lookup) over a second LLM call's opinion, especially when that
decision gates what evidence reaches yet another model call. This pattern recurs throughout the
later features below (order-lookup routing, the urgent-escalation safety net, the general node's
`don't state facts` instruction).

---

## 4. Data & API architecture

- A brief (`GAF_Prototype_Implementation_Plan.md`) specified concrete "Data Sets": products,
  inventory, customers, orders, documents, product-approval, warranty-rules, escalation-rules.
- **Cost decision**: rather than standing up a second Azure Function App, the GAF-POC routes were
  added as `/api/gaf/*` on the *same* shared Function App `telecom-assistant` already runs (separate
  route group from telecom's own `/api/*`). Reasoning: this is a demo, one Function App is cheaper
  than two, and there's no real security-isolation requirement between two demo apps. Zip-deployed by
  hand (not via CI); confirmed live that updating the zip never touched telecom's own existing
  endpoints.
- All 8 mock data sets were transcribed **verbatim** from the brief document — not invented.
  Concrete entities worth knowing if you're reading test fixtures: `Sunshine Roofing Supply`
  (ACC-1001, good standing), `Gulf Coast Distributors` (ACC-1002, **credit hold** — the
  blocked-order test case), `Bayline` (ACC-1003), product `Timberline HDZ` (SKU `TL-HDZ-CHAR` for
  Charcoal, sold in squares, 3 bundles/square, add-ons `PRO-START`/`SEAL-RIDGE`/`TIGER-PAW`/
  `COBRA-VENT`), warranty tiers `Standard Limited` vs `WindProven` (the latter needs the `LayerLock`
  nailing method + leak barrier + deck protection + starter strip + ridge cap), existing orders
  `ORD-77012` / `ORD-77013` (used for duplicate-order detection), documents `DOC-101`–`DOC-104`,
  Florida approval `FL-16254.3` / Miami-Dade NOA `22-0518.09`.
- **The origin project later moved off local JSON files entirely** and reads only from the live
  Function App at runtime (local `data/` there is kept only as historical reference, explicitly
  marked "not read at runtime" in its README). **This folder (`gaf_final`) still reads local JSON**
  — that's a real architectural difference between the two, not just a naming one; if unifying them,
  decide deliberately which data-access strategy to keep rather than silently picking whichever
  merges easier.

---

## 5. The Coordinator (a.k.a. "Team Lead") — multi-agent routing

Once both specialists worked standalone, a router was added so a rep doesn't have to pick the right
tab first — one conversation, routed per-turn.

- **Naming history**: first called "Team Lead" (matching the brief's own Section 2.5/3.5 wording),
  later renamed to **"Coordinator"** everywhere (code, UI, prompts, docs) at the user's explicit
  request — "Team Lead is a bad name". If this folder still says "Team Lead" anywhere, that's
  expected (it predates the rename) but worth doing the same rename here for consistency, since
  "Coordinator" reads better as a UI label.
- **Design**: one fast classification call per turn decides which specialist handles the message —
  deliberately **not a sticky session mode**, because the brief's own demo story explicitly switches
  topic mid-conversation (place an order, then immediately ask a warranty question). Whichever way it
  routes, the specialist orchestrator itself is called completely unchanged — the router adds no new
  tools, no new API calls, no new grounding logic of its own (beyond the general-fallback node,
  below).
- **A real bug this caught**: once conversation memory was added (see §6), asking *"Show me
  ORD-77012"* — a request to look up an existing order — got misrouted to the *new-order* agent,
  which used the memory of the prior turn to **re-build the earlier order as if it were a new one**,
  producing a duplicate-order warning against itself. Root cause: the router only knew "new order" vs
  "warranty question"; it had no concept of "existing order lookup".
  **Fix**: added a third specialist, **Order Lookup**, and a **deterministic override**: any message
  containing an order-number pattern (`ORD-\d{3,}`) is *always* routed to the lookup, regardless of
  what the classifier model said — never left to the model's judgment. The lookup specialist finds
  orders by number (regex on the message, never the model) or by customer name, and renders them
  straight from live data.
  **A second, subtler version of the same bug**: even the lookup specialist's own follow-up handling
  had to be hardened — "what did Bayline order recently?" was returning the *previous* order number
  from memory instead of the named customer's actual order, because the extraction model echoed a
  remembered order ID even though a *different* customer was now named. Fixed by only trusting a
  memory-derived order number when the message contains no named customer **and** the message
  actually contains a back-reference word ("that", "it", "again", "above", etc.) — otherwise it's
  dropped and the named customer wins. Also had to add a check that a memory-derived *customer name*
  is only trusted if it's literally present in the latest message (the model was copying the earlier
  customer's full name out of history even for messages that named someone else).
  **Lesson repeated from §3**: conversation memory reaching an LLM extraction call is a second,
  independent source of the same "don't trust the model's judgment about what's actually being asked
  right now" problem — every place memory was added needed its own deterministic guard against the
  model conflating "earlier in the conversation" with "right now".
- **Small talk / greetings**: initially handled with a hardcoded fixed reply (no model call) whenever
  the classifier said "OTHER". Later replaced (see §8) with a real conversational fallback.
- **Tone & handoff**: the same routing call also reads customer tone (`neutral` | `frustrated`) and
  sets a `handoff_suggested` flag the UI turns into an "offer a human handoff" banner. An **explicit
  ask for a person** ("can I talk to a manager", "real person", etc.) is caught by its own regex and
  always wins regardless of what tone the model read — same deterministic-override principle again.

---

## 6. Conversation memory

The frontend sends the last ~8 turns with every chat request; the backend folds them into the
extraction/classification prompts as an "Earlier in this conversation" block. This is the *only*
thing memory does — it's an **input to an LLM step**, never a change to how business logic works.
Nothing is stored server-side (no session store, no database) — the frontend owns and resends the
transcript each turn. This unlocked real follow-ups ("actually make it 20 squares", "and near
Miami-Dade?") but is also exactly what caused the order-lookup bugs in §5 — memory and deterministic
guards against misreading it have to be added together, not memory alone.

---

## 7. AI features layered on top (all additive, none changed a business decision)

Added together in one pass, each is an extra *input* to an existing LLM step or a wholly separate,
non-grounded synthesis call — deliberately **never** a change to what data or business rule Python
uses to actually decide something:

- **Feedback** — thumbs up/down on every answer, appended to a JSONL file (gitignored) for later
  review. Thumbs-down opens an optional "what was wrong?" free-text box.
- **Recap email** — one grounded synthesis call drafts a customer-facing email from the transcript
  **only** — explicitly instructed never to add a price/date/term that wasn't literally said. Same
  grounding discipline as §3.
- **Roof photo intake** — a vision call (same model deployment, `input_image` on the Responses API)
  describes what's visible in an uploaded photo, then Python composes a question for the Warranty
  Advisor, which answers exactly as it would for a typed question (same protections apply).
  **Two guards added after live testing found real problems**:
  1. The vision model initially classified a plain **UI screenshot** as "roofing-related" because it
     mentioned the word "Timberline HDZ" — tightened the prompt to require an actual physical
     roof/product in frame, not text/documents/screenshots that merely *mention* roofing.
  2. Anything the vision model flags as showing possible active leaks/damage is **forced** through
     the existing urgent-escalation path deterministically (by injecting trigger words the safety-net
     regex already looks for), rather than trusting the vision model's own severity judgment.
- **Multi-turn voice + text parity** — the voice assistant calls the *exact same* Coordinator
  orchestration function as text (see §9), so every guard above applies identically to a spoken
  conversation.

---

## 8. General-conversation fallback node

Originally, anything the classifier couldn't confidently place got a hardcoded canned reply
("Happy to help, I can prepare an order..."). At the user's request ("let it have some natural
language... if unable to determine it goes to natural language... but nothing outside the roofing
scope"), this was replaced with a **real conversational LLM node**:

- Added a fourth route, `GENERAL`, for greetings, "what can you do", and general roofing questions
  that aren't a specific cite-able fact.
- The *only* protection is a **prompt-level scope rule** — explicitly told to talk about the
  business's roofing services only, and to decline (in one sentence) anything else: other brands,
  coding help, trivia, current events. This is the same class of control telecom-assistant's own
  voice mode already used for its own SCOPE rule — a prompt instruction, not a data-grounding
  guarantee.
- Crucially, this node is **told never to state a specific price/SKU/warranty term/order detail as
  fact** — "you don't have that data here; offer to look it up if given specifics." Since it fetches
  no live data at all, it has structurally nothing to hallucinate business facts *about* — the only
  residual risk is off-topic drift, which the scope rule handles.
- **Live-tested and confirmed working**: refuses "what's the capital of France?" and "write me a
  python function" in one sentence and redirects to roofing; answers general questions like "what
  should I think about before picking a shingle color?" helpfully; correctly identifies itself as the
  business's assistant when asked "who am I talking to?".

---

## 9. Voice (WebRTC realtime)

Full parity with `telecom-assistant`'s own voice architecture, deliberately copied rather than
reinvented, with one simplification:

- **Architecture**: browser opens a WebRTC connection **directly** to Azure's Realtime API. The
  backend's only two jobs are (1) mint a short-lived ephemeral token
  (`POST /api/voice/session`) so the long-lived API key never reaches the browser, and (2) execute
  function-tool calls the realtime model requests (`POST /api/voice/tool`) — audio itself never
  round-trips through the backend.
- **Critical infra finding**: the Foundry project this app's *chat* uses has **no realtime-capable
  model deployed** (only `gpt-5-mini`/`gpt-5` exist there). Rather than provision a second Azure
  OpenAI resource just for voice, voice **reuses telecom-assistant's own existing Azure OpenAI
  resource and realtime deployment** — same cost-sharing reasoning as the Function App decision in
  §4. Configure via `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` /
  `AZURE_OPENAI_REALTIME_DEPLOYMENT` / `AZURE_OPENAI_TRANSCRIBE_DEPLOYMENT`, copied from that other
  project's own `.env`.
- **Realtime API quirk found live**: the session's `audio.input.transcription` field must **never**
  be sent in the initial mint-time payload — Azure's `client_secrets` endpoint returns
  `DeploymentNotFound` if it's present there, even with a perfectly valid deployment name.
  Transcription must be enabled *after* connecting instead, via a `session.update` event sent over
  the data channel once the WebRTC connection is live.
- **Another quirk**: that post-connect `session.update` must re-send the **entire** session object
  (voice, instructions, tools, turn_detection — not just the transcription field) — Azure appears to
  replace nested objects wholesale rather than deep-merge them; sending a partial update was
  confirmed live to silently reset the configured voice to something else.
- **Simplification vs telecom-assistant**: that project supports several Indian languages and gates
  when the model is allowed to respond on first receiving a transcript, so it can tell the model
  which language the caller just switched to before it replies. This app is English-only, so that
  whole gate is unnecessary — `turn_detection.create_response` stays `true` always, and the live
  transcript is purely a UI caption, not something anything else waits on.
- **Two function tools** exposed to the realtime model: `handle_customer_request(message, location)`
  (forwards the caller's own words to the *same* Coordinator function text chat uses, and speaks back
  whatever it returned) and `confirm_pending_order(order_session_id)` (the spoken equivalent of the
  text UI's "Confirm Order" button — can only confirm a session id the model was actually handed by
  the first tool in the same call, never one it invents; same human-in-the-loop rule as text).
- **Known unresolved limitation, inherited as-is, not masked**: `telecom-assistant`'s own
  `PROGRESS.md` documents that its self-hosted TURN relay (coturn, reused here — same VM, same
  instance) is deployed but **not yet confirmed to fix voice on Zscaler-managed corporate networks**
  — diagnosis was still in progress there as of this writing. Voice may simply not connect on such a
  network; this is a platform-level networking issue, not specific to this app.

---

## 10. UI/UX

- Initial branding matched the real GAF website's own palette/logo layout (red square 3-letter
  wordmark, `#c8102e` red) at the user's explicit request, screenshot-referenced from the real site.
- Later **fully redesigned** at the user's request after seeing it looked "childish": moved to a
  neutral enterprise palette (GAF red kept only as the single accent), removed all emoji in favor of
  real inline SVG icons, added a persisted light/dark theme toggle (respects system preference,
  applied pre-paint to avoid a flash), made the header a compact sticky bar with a segmented tab
  control, made the chat fill the viewport height on phones with a bottom-pinned composer
  (safe-area-aware), and rendered the Smart Order Agent's structured reply as a labeled
  summary/definition-list instead of a wall of text.
- Replaced starter-prompt "chips" on the empty state with three capability tiles (Orders / Warranty &
  Approvals / Voice & Photos) plus one example line, after the user asked for the chips to be removed
  and "decorated with something else."
- The origin project's frontend build is done **locally** and the `dist/` folder uploaded via SFTP to
  the VM's static path — the deployment VM has no `node`/`npm` installed at all (1GB RAM, kept
  minimal; only nginx + Python `uvicorn` processes run there). If this folder ever needs deploying to
  that same style of VM, expect the same constraint.

---

## 11. Rebrand: "GAF" → "Crestline Roofing"

At the user's explicit request ("change the gaf mentions all over the project to some neutral
name"), all **user-visible and model-facing** text was renamed from "GAF" to a fictional
"Crestline Roofing" — including, importantly, the *voice assistant's own persona instructions* and
every LLM prompt that described the business by name (order extraction, warranty classification,
photo-intake, recap-email sign-off), not just UI copy. Live-verified the model actually adopted the
new identity when asked "who am I talking to?".

**Deliberately left unchanged** (infrastructure identifiers, not brand text — renaming these means
recreating/redeploying live Azure resources or breaking working URLs, for zero user-visible benefit):
the `gaf_demo` directory name, the `/gaf/` URL path, the `gaf-demo-backend` systemd service name, the
`GAF_MODEL`/`GAF_API_BASE_URL` env var names, the `gaf-foundry` Azure AI Foundry project name, and
the shared Function App's `/api/gaf/*` route prefix.

**If unifying branding with this folder**: this folder still says "GAF" throughout (it predates the
rebrand) — decide deliberately whether to repeat the same rename here, and reuse the same
scoping rule (rename prose/prompts, leave infra identifiers alone) rather than re-deciding it from
scratch.

---

## 12. Testing & deployment discipline (apply the same rigor here)

Every change in the origin project followed the same loop, worth repeating here:
1. Write/update **offline unit tests** (httpx/model calls mocked) covering the actual business logic
   and the specific bug being fixed, including a **regression test with a "must never be called"
   assertion** for anything safety/grounding related (see §3) — not just an output-correctness check.
2. Run the full suite locally.
3. **Live-verify against the real Azure AI Foundry endpoint and real API** locally before deploying —
   never trust mocked tests alone for anything involving model behavior (routing correctness, scope
   refusal, grounding).
4. Deploy, then **live-verify again through the actual public URL** — and always re-check that
   *unrelated, already-working* endpoints/features still work (nothing regressed a sibling feature).
5. Only report a feature "done" after both the local and live-deployed checks pass.

This project ended with 80+ backend tests, all offline/mocked, plus a repeated pattern of live
scripted checks (via direct HTTP calls, and via a headless-browser Playwright script for UI-level
verification including screenshots in both themes and at phone/desktop widths) before and after every
deploy.

---

## 13. What was ruled out / abandoned (don't redo these without new evidence)

- **Foundry Agents with tool-calling** — needs a manual Portal step to register real function tools;
  no scriptable path with the installed SDK. See §2.
- **LLM-judgment gating of evidence relevance** — tried once for warranty grounding, provably failed
  live (StainGuard hallucination). See §3. Always prefer a deterministic Python check when the
  question is "should this evidence/data even be fetched/shown."
- **Trusting conversation memory verbatim in extraction calls** — caused the order-lookup duplicate
  bug and the "Bayline" customer-name bug. See §5. Any new memory-dependent feature should assume the
  model will sometimes echo something from history that no longer applies to the current turn, and
  needs its own deterministic guard.
- **A second Azure OpenAI/Function App resource "for cleanliness"** — rejected twice (API hosting,
  realtime voice) purely on cost grounds for a demo with no isolation requirement; the shared-resource
  pattern was reused deliberately both times rather than re-litigated.
- **Sending a partial `session.update` to the Realtime API** — confirmed live to silently corrupt
  the configured voice. Always resend the full session object.
- **Sending `audio.input.transcription` at realtime-session mint time** — confirmed live to break the
  ephemeral-token mint call outright (`DeploymentNotFound`). Enable it post-connect only.

---

## 14. Session narrative (chronological, best-effort reconstruction)

This is the order events actually happened in the working session against
`telecom-assistant/gaf_demo`, for continuity/context even though it's a different codebase folder:

1. Existing telecom-assistant Azure Function App zip explained; decided to combine GAF's info-APIs
   into the *same* Function App as telecom's, purely for cost (§4).
2. Built the 8 GAF-POC read-only API endpoints from the brief's Data Sets, for both agents; verified
   telecom's own existing endpoints were completely unaffected.
3. Given two Foundry Agent system prompts (order + warranty) that referenced unregistered tools,
   diagnosed and live-confirmed the Foundry Agent tool-registration dead end (§2), then rebuilt both
   agents on telecom-assistant's own router → deterministic Python → template/synthesis pattern,
   picking `gpt-5-mini` after benchmarking (§2).
4. Found and fixed the StainGuard grounding hallucination the hard way — first attempt failed live,
   second (deterministic) attempt verified working, locked in as a regression test (§3).
5. Manual test walkthrough with the user; confirmed a full order-to-confirmation flow worked
   end-to-end live, including a client typo ("timberline hex charcoal") still resolving correctly.
6. Built the Coordinator/"Team Lead" classifier tying both agents into one Assistant tab/conversation
   (§5), plus full WebRTC realtime voice reusing telecom's own Azure OpenAI resource (§9) — both
   live-verified via direct HTTP calls and via a live phone test (screenshots from the user's own
   phone confirmed a full spoken order flow, including a "don't proceed" refusal working correctly).
7. Full UI redesign after user feedback that the original looked "childish" — light/dark themes,
   mobile-first layout, real icons instead of emoji (§10).
8. Added five more AI features in one pass: conversation memory, tone/handoff detection, thumbs
   up/down feedback, a grounded recap-email drafter, and roof-photo intake (§6, §7) — user explicitly
   said "add whatever new AI features... I give you freedom, don't ask, just push, we'll roll back if
   needed," so this batch was built and deployed without incremental confirmation, per that standing
   instruction for that batch of work.
9. User reported three real problems from actually using it: the Coordinator's name ("Team Lead") was
   bad, the empty-state starter chips needed to be "decorated with something else," and — the
   important one — asking to see an existing order ("Show me ORD-77012") was incorrectly re-creating
   the order from memory instead of looking it up. All three fixed: renamed to "Coordinator" (§5),
   replaced chips with capability tiles (§10), and added the Order Lookup specialist with
   deterministic order-number routing (§5) — including two follow-up bugs found during the *same*
   live-testing pass (the "Bayline" customer-name-from-memory bug, and small-talk being wrongly routed
   to an agent instead of getting a direct reply) (§5, §8).
10. Added the general-conversation fallback node (§8) and rebranded "GAF" → "Crestline Roofing"
    throughout user/model-facing text (§11), in the same request/turn — both live-verified,
    committed, and deployed.
11. User asked about "someone pushing from another laptop" — investigated: no divergence on
    `telecom-assistant`'s own remote, but found a separate public repo `v-adityaram/gaf-final`
    (single commit, 2026-09-15, no leaked secrets, stale/pre-rebrand snapshot) and, in a later
    message, this local folder (`C:\Users\vssva\OneDrive\Desktop\gaf_final`) — determined to be a
    team's independent, more-extended fork of the same origin code (§1). Advised making the public
    repo private (assistant's own GitHub token doesn't have access to that repo to do it directly).
12. This document was written at that point, into this folder, so a fresh session picking up work
    here has full context without needing the original conversation transcript.

---

## 15. Suggested next steps for whoever continues here

Pick based on what this folder's own state actually needs — not prescriptive, just what's visibly
outstanding relative to the origin project:

- Decide whether to move this folder off local JSON data onto a live API (like the origin project
  did) or keep local JSON deliberately (e.g. if the team's demo depends on being fully offline).
- Consider the same "Team Lead" → "Coordinator" rename here for consistency, if this codebase's
  router is still called that.
- Consider porting the deterministic order-lookup fix (§5) if this folder's own Coordinator/router
  has (or could have, once memory is added) the same duplicate-order-from-memory failure mode.
- Consider porting the general-conversation fallback (§8) if this folder's router still uses a fixed
  canned reply for unmatched messages.
- If this folder's public repo (`gaf-final`) is meant to stay public long-term, at minimum verify no
  real `.env` or credentials are anywhere in its git history (not just the current tree) before
  relying on that.
- Whatever is built next, keep the same testing discipline from §12 — it's what caught every real bug
  described in this document before it reached a live demo.

---

## 16. Session 2026-09-17 -- sales-rep assistant build-out (this folder)

Written by the session that turned this folder from the customer-service demo above into the
**GAF Sales Assistant**. Everything below happened in `gaf_final`, not in `gaf_demo`.

### What changed

- **Dataset = the workbook.** `GAF_AI_Prototype_Synthetic_Datasets 1.xlsx` is now the source of truth;
  `scripts/build_dataset.py` regenerates `data/*.json` (24 priced products, 18 accounts with trade names /
  ZIPs / reps, 6 DCs, 144 inventory rows, 45 priced orders, 12 knowledge docs **with full text** plus 27
  citable passages, add-on rules, counties/ZIPs) and the synthetic extensions (contractors, discounts,
  sales reps, inbox emails, demo use cases). `scripts/validate_demo_data.py` checks referential integrity.
  Old SKUs (`TL-HDZ-CHAR`) are gone -- workbook SKUs (`TL-HDZ-01`) everywhere.
- **One catalogue module for both transports.** `backend/app/services/gaf_catalog.py` builds every
  envelope; `local_data_repository.py` wraps it for `GAF_DATA_SOURCE=local`, and
  `scripts/build_function_app_zip.py` copies the same file + `gaf_data/*.json` into
  `Telecom-POC-deploy-with-GAF-v2.zip` (telecom section of `function_app.py` byte-identical; GAF section
  rewritten with 18 routes). Deploying that zip makes `live` mode return exactly what `local` returns.
- **Pricing & discounts** (`services/pricing_service.py`): unit price x base quantity per line, volume
  tiers (highest only), one seasonal promo, Complete-System bonus (needs all four WindProven categories),
  distributor allowance, rep commission; credit is now checked against the priced total.
- **Add-ons** (`services/add_on_service.py`): rule quantities from `add_on_rules.json`; named/"WindProven
  set" -> included lines, otherwise suggested with a checkbox; ridge cap colour-matched or flagged. All
  "accessory" wording renamed to "add-on" (`add_ons_required`, `add_on_note`, ...).
- **Bulk orders**: extraction returns `items[]`; every line resolved, priced, stock-checked; the order
  form is a multi-line editor and recheck sends `lines[]`.
- **Roof estimator** (`services/roof_estimator.py`): living area / storeys x pitch factor + waste -> squares;
  asks for storeys / living area (lot size is deliberately not a proxy); rep confirms via quick reply.
- **Warranty confidence + human-in-the-loop** (`warranty_orchestrator.py`, `services/review_queue.py`):
  deterministic 0-100 score (evidence found + classifier confidence - penalties for missing county,
  mixed-manufacturer, specific-building, multi-intent, injection). >= 95 auto-answers; below that the
  draft is queued (`data/review_queue/warranty_reviews.jsonl`) and the Metrics tab shows an
  approve/edit/reject queue. Passage retrieval (`kb-passages?q=`) replaced the metadata-only documents.
- **Contractor Finder** (`contractor_orchestrator.py`): ZIP/city regex + tier keywords -> directory search;
  LLM extraction only as a fallback. New Coordinator route `CONTRACTOR` plus deterministic overrides
  (`ORD-nnnnn` lookup wording -> General; "contractors near <zip>" -> Contractor).
- **Email Agent** (`email_orchestrator.py`, `POST /api/email/intake`, `GET /api/inbox`): each selected
  email -> one extraction call -> the same Coordinator as typed text. Email bodies are data.
- **Sales rep layer**: `GET /api/reps`, `/api/reps/{id}/dashboard` (accounts, orders, booked sales,
  commission, quota, session confirmations); confirmations now record lines, totals, rep and commission.
- **Frontend**: GAF logo/palette header, left rail (Inbox window, Live call window, Review queue),
  top-right rep badge with dashboard popover, "Demo scenarios" menu, product tiles (generated swatches;
  `image_url` overrides), contractor cards, pricing table, confidence meter, quick-reply chips, estimate
  card, "Draft email" instead of "Recap". "Team Lead" -> "Coordinator" everywhere.
- **Tests**: suite rewritten, 160 offline tests. Verified live end-to-end with Playwright against the real
  Foundry model (every screen, zero console errors).

### Bugs found during live testing (and the fixes)

- Extraction returned the customer as `"Sunshine Roofing Supply (ACC-1001)"` -> exact-match lookup
  failed. Fix: an embedded `ACC-nnnn` always wins; parentheticals stripped from name lookups.
- Extraction listed "starter / underlayment / ridge cap" as quantity-less *items* -> "quantity missing".
  Fix: quantity-less add-on mentions are folded into add-on categories deterministically
  (`add_on_service.category_for`) and the prompt says so.
- Synthesis returned `NO_SOURCE` **plus** a "Source:" line, so the exact-string check missed it and a
  NO_SOURCE draft landed in the review queue. Fix: startswith check.
- AR-004/AR-005 (both "Ridge cap") produced two ridge lines; vent heuristic over-ordered. Fixed in
  `add_on_service` (one line per category, 1.2 ridge ft per square).
- Float noise made a 3,000 sq ft roof 34 squares instead of 33 (`roof_estimator._squares`).
- Backend must run with `--reload` (or be restarted) when editing -- an un-reloaded server masked two
  of the fixes above for a while.

### Still open / judgement calls

- Product photos are generated swatch tiles, not gaf.com images (copyright); drop real URLs into
  `products.json.image_url` to replace them.
- The review queue is a JSONL file with no reviewer identity; the "Sales manager" reviewer name is a
  placeholder.
- Live voice was not exercised in the automated run (no microphone in headless Chromium); the tool
  plumbing is unchanged apart from the persona/instructions.
- `backend/.venv` was created on another machine and does not run here; `backend/.venv-win` (gitignored)
  is the working one on this laptop.
