# AI Fitness App

An AI-powered food & exercise logging app you talk to in natural language —
*"I had 3 servings of chicken breast for lunch"*, *"bench press 3x10 at 185"* — built so the
**deterministic logic is in control and the LLM is an untrusted advisor**, not the other way
around.

This is a deliberate response to the common failure modes of "full AI" apps:

- **Hallucinated numbers** — a model inventing macros/calories.
- **Multi-turn state loss** — forgetting what you said a turn ago.
- **Narrated-but-not-real actions** — the classic bug where the assistant cheerfully says
  *"moved chicken to lunch, deleted the rest"* while making **zero** changes to storage.

The architecture makes those structurally hard rather than relying on better prompting.

## Core principles

1. **Deterministic-first, LLM-on-gaps.** A rule-based parser extracts everything it can
   justify (quantities, units, known foods + their macros, sets/reps/weights). The LLM is
   called *only* to fill what's left or to classify ambiguous intent, and its output can
   never override a parsed or user-confirmed value.
2. **Provenance + confidence on every field.** Each datum is tagged
   `USER > DETERMINISTIC > KNOWLEDGE_BASE > LLM > DEFAULT`. Conflicts resolve by that
   ranking — so the LLM loses to the parser by construction.
3. **The app owns the state machine, not the model.** Builders deterministically answer
   "do I have enough info to log this yet?" and drive clarifying questions across turns.
4. **Mutation integrity (hard rule).** The LLM has no access to storage. All writes go
   through deterministic use-cases, and every confirmation is built from a **re-read of
   what's actually persisted** — never from the model's narration. No write ⇒ no success
   message.
5. **Hexagonal architecture.** The domain and use-cases depend only on *ports*
   (interfaces). Storage (JSON now, SQL later) and the LLM (Gemma via Ollama or Anthropic
   Claude) are swappable *adapters* wired in at a single composition root.

## What it does

- **Natural-language logging** for food *and* exercise — casual phrasing, messy quantities,
  brand names, and multi-turn clarification all handled ("just had a sandwich" → asks what
  it needs; "bench 3x10 185" → logged directly).
- **Exercise domain** covering strength (sets/reps/weight, incl. mixed-weight sets and
  bodyweight moves), cardio (duration), and mobility, with name normalization
  (`ohp`→overhead press, `rdl`→romanian deadlift).
- **Workout plans + rotating calendar** — build custom plans or start a preset (PPL, upper/
  lower), then a self-advancing schedule with skip / push-back / align / complete.
- **Saved meals** — compose reusable meals and one-tap log them to a slot.
- **Daily summary & macros**, drag-and-drop food between meal slots, profile & settings
  editable by chat or form.
- **Web UI** — a single-page front end with light/dark themes (persisted, respects OS
  preference) and all user-data rendering HTML-escaped against XSS.

## Architecture (ports & adapters)

```
web (FastAPI)  ─┐
                ├─►  application (use-cases)  ─►  domain (entities, builders, value objects)
adapters       ─┘            │
 ├─ persistence (JSON)       └─ depends only on PORTS (Protocols):
 ├─ extraction (rule-based)        MealRepository, ExerciseRepository, PlanStore,
 └─ llm (Ollama/Anthropic)         ProfileStore, SavedMealStore, Extractor, LlmClient,
                                   FoodKnowledgeBase, Clock
```

- **`domain/`** — pure, stdlib-only. Immutable `Food`/`Meal`/`Exercise` entities,
  `Macros`/`Quantity` value objects, the `FieldValue`/`Provenance` machinery, the
  builder/completeness state machines, workout plans, and saved meals.
- **`application/`** — use-cases (`LogMeal`, `LogExercise`, `EditLog`, `EditExercise`,
  `BuildPlan`, `ManageCalendar`, `Query`, `DailySummary`, `ViewLog`) fronted by
  `HandleMessage` (intent routing), plus the `ports/` they depend on and the pure
  `reconciliation` function that merges extraction sources under deterministic-wins rules.
- **`adapters/`** — concrete implementations: JSON stores for meals/exercises/plans/
  profile/saved-meals, `RuleBasedExtractor`, `StaticFoodKnowledgeBase`, `SystemClock`, and
  three `LlmClient`s (`Ollama`, `Anthropic`, `Null`).
- **`config/`** — `Settings` (env-driven) and the `Container` composition root, the only
  module that imports both adapters and the application layer.

The dependency rule: `domain` and `application` never import `adapters` or `web`.

## How a message flows

1. **Intent routing** — `HandleMessage` classifies the message
   (`LOG` / `QUERY` / `EDIT` / `EXERCISE` / `CALENDAR` / `CHAT`) with a rule-based
   classifier first, falling back to the LLM only when heuristics are inconclusive.
2. For a food `LOG`: the **rule-based extractor** parses text → a `CandidateMeal` (per-field
   provenance). Known foods get macros from the **knowledge base**.
3. If gaps remain, the **LLM** is asked to fill only those; results are **reconciled** with
   deterministic values winning.
4. The result is projected into a **builder**; if required fields are missing, the app asks
   one focused clarifying question. User answers are *sticky* (highest provenance) and
   preserved across turns.
5. When complete, the entity is built and **persisted**; the response reflects a re-read of
   stored state.

Exercise logging follows the same shape through `LogExercise` — a regex-first parser with
LLM fallback, multi-turn clarification, and a builder that knows when it has enough.

## Development

Requires Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Unix: source .venv/bin/activate
pip install -e ".[dev]"
pytest                 # ~565 tests (LLM-backed e2e tests are excluded by default)
```

Tests are organized as `tests/unit`, `tests/integration`, and `tests/e2e`. The hexagonal
boundaries mean the entire core is testable with in-memory fakes and zero IO.

### Running the web app

```bash
# Localhost only (default — only accessible on this machine):
set PYTHONPATH=src && py -3 -B -m uvicorn fitness.web.app:create_app --factory --reload

# LAN-accessible (reachable from other devices on your network):
set PYTHONPATH=src && py -3 -B -m uvicorn fitness.web.app:create_app --factory --reload --host 0.0.0.0 --port 8000

# LAN over HTTPS — what the Android app expects (see "HTTPS on the LAN" below):
set PYTHONPATH=src && py -3 -B -m uvicorn fitness.web.app:create_app --factory --reload --host 0.0.0.0 --port 8443 --ssl-keyfile certs/server.key --ssl-certfile certs/server.crt
```

- **Localhost:** open http://127.0.0.1:8000/static/index.html
- **LAN:** open `http://<your-ip>:8000/static/index.html` from any device on the network
  (e.g. `http://192.168.1.x:8000/static/index.html`)
- **LAN over HTTPS:** open `https://<your-ip>:8443/static/index.html`. Requires
  `py -3 scripts/make_certs.py` first; add `?token=<your-token>` on the first visit if
  `FITNESS_AUTH_TOKEN` is set.

### Using it on your phone

The backend stays on your PC — the phone is only a client, so it must be able to reach the
server. There are three options, depending on how "app-like" you want it.

**1. Just a browser tab (no setup).** Start the server with `--host 0.0.0.0` and open
`http://<your-pc-ip>:8000/static/index.html` on any device on the same wifi. The full app
works; it just lives in a Chrome tab.

**2. A real Android app, LAN-only (recommended).** Build the APK in [`android/`](android/):

```bash
bash android/build.sh          # -> android/fittrack.apk
```

Then install it over the LAN (copy the APK into `src/fitness/web/static/` and open
`http://<your-pc-ip>:8000/static/fittrack.apk` on the phone) or over USB with
`adb install -r android/fittrack.apk`. You get an app-drawer icon, fullscreen, no browser
UI — and no HTTPS anywhere, because a native `WebView` has no secure-origin requirement.
See [android/README.md](android/README.md) for details.

**3. An installed PWA (needs HTTPS).** The web app *is* a PWA — manifest, service worker,
maskable icons — so Chrome can install it to the home screen. But Chrome only mints a real
standalone app for an `https://` origin. Over plain LAN HTTP, "Install app" silently
degrades to a bookmark that opens in a browser tab, even with `chrome://flags` →
"Insecure origins treated as secure" enabled (that grants a secure *context*, enough for
the service worker, but Chrome checks the URL scheme separately).

So this path needs real HTTPS. The easiest way is **Tailscale**, which also makes the app
reachable off your wifi:

1. Install Tailscale on the PC and phone (same tailnet); enable **MagicDNS** and
   **HTTPS Certificates** in the admin console.
2. Run the server normally, then `tailscale serve --bg 8000`.
3. On the phone, open `https://<machine>.<tailnet>.ts.net/static/index.html` →
   **⋮ → Install app**.

Settings → **Install Status** in the app reports whether the current origin is secure, if
the service worker registered, and whether you're running installed or in a tab — useful
for diagnosing why an install didn't stick.

### HTTPS on the LAN

Plain HTTP on a local network is readable and modifiable by anything else on that
network. To encrypt it, generate a local certificate authority and a server certificate:

```bash
py -3 scripts/make_certs.py            # auto-detects your LAN IP
```

That writes `certs/` (gitignored — it holds private keys). The server certificate carries
Subject Alternative Names for your LAN IP, `localhost` and `127.0.0.1`; the name you
connect to has to be in that list, and an IP has to be an `IPAddress` entry rather than a
DNS one.

Then serve over TLS:

```bash
set PYTHONPATH=src && py -3 -B -m uvicorn fitness.web.app:create_app --factory --host 0.0.0.0 --port 8443 --ssl-keyfile certs/server.key --ssl-certfile certs/server.crt
```

(Kept on one line on purpose: `^` continuations are cmd.exe syntax and are a parse
error in PowerShell, which uses a backtick.)

- **Android app:** rebuild it (`bash android/build.sh`) — the CA is bundled into the APK
  as a trust anchor, so nothing needs installing on the phone. See
  [android/README.md](android/README.md).
- **Browser:** import `certs/ca.crt` as a trusted authority, otherwise you'll get a
  warning. On Android that's Settings → Security → Encryption & credentials → Install a
  certificate → CA certificate.

Regenerating certificates means rebuilding and reinstalling the APK, since the CA is
compiled in.

### Requiring an access token

HTTPS stops eavesdropping, but on its own anyone who can reach the server can still read
and write your log. Set a shared secret to require one:

```bash
FITNESS_AUTH_TOKEN=some-long-random-string
```

Leave it unset (the default) and auth is disabled entirely, so local development and the
test suite are unaffected.

When set, every API request must present the token as an `X-Auth-Token` header, a
`?token=` query parameter, or a `fittrack_token` cookie. The web UI stores it in
`localStorage` and prompts for it on the first 401. The easiest way to hand it to your
phone is to open the app once as:

```
https://<your-ip>:8443/static/index.html?token=some-long-random-string
```

The token is saved and stripped from the URL. Static assets stay reachable without it —
the page has to load in order to prompt — but every data endpoint is protected.

### LLM configuration

The LLM is optional and off by default (`FITNESS_LLM_PROVIDER=none` uses a `NullLlmClient`,
so the deterministic core runs fully offline). To enable it, set env vars (or a `.env`,
prefix `FITNESS_`):

```bash
# Local, offline — Gemma via Ollama:
FITNESS_LLM_PROVIDER=ollama
FITNESS_OLLAMA_HOST=http://localhost:11434
FITNESS_OLLAMA_MODEL=gemma4:26b

# Hosted — Anthropic Claude (same LlmClient port, swapped at the composition root):
FITNESS_LLM_PROVIDER=anthropic
FITNESS_ANTHROPIC_API_KEY=sk-ant-...
FITNESS_ANTHROPIC_MODEL=claude-haiku-4-5-20251001
```

The LLM-backed end-to-end tests are opt-in and require a running provider:

```bash
pytest -m llm        # runs the e2e suite against the configured LLM
```
