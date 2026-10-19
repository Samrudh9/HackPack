# HackPack

**Open-source, domain-independent hackathon deliverables generator.** Give it a public GitHub repository, the event brief, and a few team answers — it returns an editable six-slide PowerPoint, a timed pitch script, a demo checklist, and a downloadable ZIP.

HackPack works for **any hackathon domain, language, or project type**. Its central differentiator is the **Evidence-to-Pitch Engine**: it analyzes real repository evidence, classifies every claim as repository evidence, test evidence, team-provided, or needing verification, and refuses to invent metrics, users, or completed features.

> **v0.1 notice:** this is an early release. Repository analysis and claim checks are conservative heuristics — they do not prove that code works at runtime. Review all generated content before presenting.

## What v0.1 does

- Analyzes a public GitHub repository **without executing its code**: README, recursive file tree, dependency manifests, selected source files, and test files.
- Detects technologies (requirements.txt, pyproject.toml, package.json, Cargo.toml, go.mod, Gradle, Maven, and more), tests, CI workflows, Docker files, licenses, and demo URLs.
- Generates a **six-slide deck** (Problem · Solution · How It Works · Demo Highlights · Impact & Results · What's Next) with speaker notes and per-slide time allocations that sum exactly to the requested pitch duration.
- Produces a timed Markdown pitch script with evidence references and claim-review warnings, plus a demo checklist that only includes evidence-backed steps.
- Bundles everything into a ZIP with a `generation_summary.json` that records warnings and the generation mode.
- Runs **without any AI provider**: a deterministic template fallback produces a labeled, usable deck when no model is configured or reachable.
- Optionally uses a local Ollama model or any LiteLLM-supported hosted provider for richer narrative generation — with structured-output validation, up to two repair retries, and honest fallback labeling.

### Current limitations

- Public GitHub repositories only (no private-repo auth in v0.1).
- Six slides, fixed storyline (v0.1).
- Claim verification is conservative and heuristic: it can downgrade or omit unsupported claims, but it cannot certify that a feature runs.
- PDF export is deferred to v0.2.
- No background jobs: `/api/generate` completes within the request; keep repository sizes modest.

## Architecture

```text
                        ┌────────────────────────────────────────────┐
                        │  Frontends                                  │
                        │  • React app in frontend/ (primary, HTTP)   │
                        │  • Optional local Streamlit UI              │
                        └───────────────┬────────────────────────────┘
                                        │ HTTP (JSON / ZIP)
┌───────────────────────────────────────▼───────────────────────────────┐
│ api/  FastAPI (thin handlers, sync endpoints in the threadpool)       │
│   GET  /api/health      POST /api/analyze   POST /api/pitch           │
│   POST /api/generate →  ZIP: pitch_deck.pptx, pitch_script.md,        │
│                         demo_checklist.md, generation_summary.json    │
└───────────────┬───────────────────────────────────────────────────────┘
                │ plain Python calls (hackpack is FastAPI-independent)
┌───────────────▼───────────────────────────────────────────────────────┐
│ hackpack/  core library                                                │
│  engine/repo_analyzer   read-only GitHub analysis, bounded, redacted  │
│  engine/verifier        claim categorisation + candidate retrieval    │
│  engine/pitch_builder   AI draft or deterministic 6-slide fallback    │
│  llm_client             LiteLLM adapter, validated JSON, 1+2 retries  │
│  generators/            pptx · script · demo · zip bundle             │
│  models.py              Pydantic v2 contracts shared everywhere       │
└───────────────┬───────────────────────────────────────────────────────┘
                │ HTTPS (read-only)              │ optional
        GitHub REST / raw CDN            Ollama (localhost) or a
        (no code execution)             LiteLLM-hosted provider
```

## Quick start

Requirements: Python 3.10+, internet access for repository analysis, and optionally [Ollama](https://ollama.com/) for local AI. **No AI provider is required** — the fallback generator works offline.

```bash
git clone https://github.com/YOUR-USERNAME/HackPack.git
cd HackPack
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env             # optional; defaults work out of the box
```

Run the API:

```bash
uvicorn api.main:app --reload
```

Open **http://localhost:8000/docs** for interactive API documentation. Verify the installation:

```bash
curl http://localhost:8000/api/health
```

### Run the web frontend

The React app in `frontend/` (React 19 + TanStack Start + Vite) drives the whole pipeline: analyze → backend pitch → review/edit → ZIP download.

```bash
cd frontend
npm install
cp .env.example .env     # VITE_API_BASE_URL defaults to http://localhost:8000
npm run dev              # http://localhost:3000
```

Keep the backend running in another terminal — the default CORS allow-list already includes `http://localhost:3000`. Frontend scripts: `npm run dev`, `npm run typecheck` (`vite build` + `tsc --noEmit`), `npm test` (vitest). See [`frontend/README.md`](frontend/README.md).

### Optional: local model on an 8 GB laptop

HackPack never requires a large model. Small models that work within ~8 GB RAM (CPU-only is acceptable for short pitch drafts):

| Model | Notes |
|---|---|
| `llama3.2:3b` | Good quality/size balance; recommended default for 8 GB |
| `qwen2.5:3b` | Strong structured-output compliance |
| `gemma2:2b` | Lightest option |

```bash
ollama pull llama3.2:3b
ollama serve
```

Then in `.env`:

```env
LLM_MODEL=ollama/llama3.2:3b
LLM_API_BASE=http://localhost:11434
```

Model identifiers and LiteLLM's `ollama/` prefix compatibility change over time — verify your combination with a request to `/api/pitch` once after upgrading. If the model is unreachable or returns invalid JSON, HackPack automatically falls back to the deterministic template and labels the output `generation_mode: fallback`.

### Optional: hosted provider

Any LiteLLM-supported provider works. Example for OpenAI:

```env
LLM_MODEL=openai/gpt-4o-mini
OPENAI_API_KEY=your-key-here
LLM_API_BASE=
```

Never commit real credentials. Set provider keys through your deployment secret store, not the repository.

## API

| Method & path | Purpose | Success | Errors |
|---|---|---|---|
| `GET /api/health` | App/version/model info | `200` | — |
| `POST /api/analyze` | `{repo_url}` → repository evidence + summary | `200` | `400` bad/inaccessible repo, `422` invalid body |
| `POST /api/pitch` | evidence + brief + team → verified six-slide deck | `200` | `422`, `503` model down *and* fallback disabled |
| `POST /api/generate` | deck (+ optional evidence) → deliverable ZIP | `200 application/zip` | `422` invalid deck |

Limits (configurable in `.env`): request bodies capped by `MAX_REQUEST_BODY_BYTES` (default 2 MB, answered with `413`), repository traversal capped by `MAX_FILES_TO_ANALYZE`/`ANALYSIS_TIME_BUDGET_SECONDS`, model calls by `LLM_TIMEOUT_SECONDS`. Handlers are synchronous by design so blocking GitHub/model calls run in FastAPI's worker threadpool and never block the event loop.

Example flow:

```bash
curl -s -X POST localhost:8000/api/analyze -H 'Content-Type: application/json' \
  -d '{"repo_url":"https://github.com/owner/repo"}' > evidence.json
# feed evidence.evidence plus your brief/team into /api/pitch, then the deck into /api/generate
```

## Frontend (`frontend/`)

The shipped React app exercises all three endpoints and treats the backend as the source of truth for claim labels:

1. **Analyze** — `POST /api/analyze`, then normalizes the evidence (tech stack, tests/CI/Docker badges, demo URLs, analyzer warnings).
2. **Generate pitch** — `POST /api/pitch` with the form mapped onto `HackathonBrief` + `TeamContext`. The returned six-slide deck is authoritative, including the verifier-assigned `evidence_type` label on every claim. If the pitch call fails, the app falls back to a clearly-labelled in-browser draft and states so in the warnings; it never pretends the backend produced it.
3. **Review** — slides are editable. The cover shows whether the draft is `ai` (backend model, claims verified server-side) or `fallback` (deterministic template or local draft).
4. **Export** — the edited deck is sanitized to the backend's validation limits (six slides, clamped speaking times, valid evidence enums) and sent to `POST /api/generate`; the returned ZIP is offered as a download.

Frontend environment (`frontend/.env`, copied from `frontend/.env.example`):

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | empty (same origin) | Backend base URL, e.g. `http://localhost:8000` |
| `VITE_API_HEALTH_PATH` | `/api/health` | Health endpoint path |
| `VITE_API_ANALYZE_PATH` | `/api/analyze` | Repository analysis path |
| `VITE_API_PITCH_PATH` | `/api/pitch` | Evidence-to-pitch path |
| `VITE_API_GENERATE_PATH` | `/api/generate` | Deliverable ZIP path |
| `VITE_API_TIMEOUT_MS` | `90000` | Request timeout; keep it above `ANALYSIS_TIME_BUDGET_SECONDS` |
| `VITE_OPEN_SOURCE_REPO_URL` | empty | Optional source-repo link shown in the header |

CORS uses **exact** origins only. The defaults cover local development on ports 3000, 3001, 5173, and 8501; add your deployed frontend origin to `CORS_ALLOW_ORIGINS` before shipping. A deployed frontend **cannot** reach `localhost` on your machine — for shared demos, deploy the backend (a single container on Render/Railway/Fly.io is enough), set `VITE_API_BASE_URL` to the public URL, and add the frontend origin to `CORS_ALLOW_ORIGINS`.

### Building your own frontend (Lovable prompt)

Paste this prompt into Lovable if you'd rather generate a separate UI:

```text
Build a single-page web app called "HackPack" that generates hackathon pitch deliverables
from a GitHub repository. It talks to a FastAPI backend with these exact endpoints:

- GET  {BASE_URL}/api/health -> {status, app, version, llm_model, llm_fallback_enabled}
- POST {BASE_URL}/api/analyze  body {repo_url: string}
    -> {evidence: {repo_url, repo_name, description, file_tree: string[],
        tech_stack: [{name, version, category, evidence_file}], has_tests, has_ci,
        has_docker, demo_urls: string[], license, primary_language,
        analysis_warnings: string[], ...}, summary: object}
    Errors: 400 {detail: string}, 422 FastAPI validation error.
- POST {BASE_URL}/api/pitch  body {evidence, brief: {event_name, theme,
    judging_criteria: string[], pitch_duration_minutes, additional_rules},
    team: {problem_statement, solution_summary, target_users, key_results, impact_claims: string[],
    future_plans, team_members: string[]}}
    -> {deck: {project_name, tagline, slides: [{slide_number, title, subtitle,
    bullet_points: string[], speaker_notes, speaking_time_seconds,
    claims: [{statement, category, evidence_type, source, needs_action,
    confidence}]}], total_duration_seconds, generation_mode: "ai"|"fallback",
    generation_warnings: string[], unverified_claims}, generation_mode, warnings}
- POST {BASE_URL}/api/generate  body {deck, evidence?, demo_duration_seconds}
    -> ZIP file (application/zip) containing pitch_deck.pptx, pitch_script.md,
    demo_checklist.md, generation_summary.json.

UI flow, in one page with four steps:
1. Form: GitHub URL (validated client-side as https://github.com/owner/repo),
   event name, theme, judging criteria, pitch duration slider (1-20 min),
   problem statement, target users, key results, next steps.
2. "Analyze repository" button → progress spinner → show detected technologies,
   tests/CI/Docker badges, demo URLs, and analysis warnings in cards.
3. "Generate pitch" → render the six slides as an editable preview (title,
   bullets, per-slide time badge), a claims panel listing every claim with its
   evidence_type badge (repo_evidence=green, test_evidence_found=teal,
   team_provided=amber, needs_verification=red) and needs_action text.
   If generation_mode is "fallback", show a prominent amber banner explaining
   the AI model was unavailable and the deck came from a template.
4. "Download ZIP" button that saves the response of /api/generate.

Design: dark theme with background #0F0C29, electric violet (#6C63FF) and cyan
(#00D9FF) accents, rounded panels (#1B203A), Aptos or Inter typography.
Show real loading states for every request, surface {detail} error strings
from the API honestly, and never invent data the API did not return. The app
is stateless: send the analyze response straight back into /api/pitch.
```

An optional Streamlit UI (`streamlit run app/main.py`, `make run-ui`) exists for local use.

## Configuration

Copy `.env.example` to `.env`. Highlights:

| Variable | Default | Description |
|---|---|---|
| `LLM_MODEL` | `ollama/llama3.1` | LiteLLM model string (`ollama/<model>` for local) |
| `LLM_API_BASE` | `http://localhost:11434` | Ollama URL or provider base URL |
| `LLM_MAX_RETRIES` | `2` | Repair retries after the first structured-output attempt (0–2) |
| `LLM_FALLBACK_ENABLED` | `true` | Deterministic template deck when the model fails |
| `GITHUB_TOKEN` | empty | Optional; raises anonymous GitHub rate limits |
| `MAX_FILES_TO_ANALYZE` | `50` | Repository traversal bound |
| `ANALYSIS_TIME_BUDGET_SECONDS` | `60` | Wall-clock cap for one analysis |
| `CORS_ALLOW_ORIGINS` | dev origins on ports 3000, 3001, 5173, 8501 | Comma-separated **exact** origins; wildcards rejected |
| `MAX_REQUEST_BODY_BYTES` | `2000000` | Request size guard (413) |
| `SAVE_GENERATED_ZIPS` | `false` | Keep a debug copy of each ZIP under `OUTPUT_DIR` |

## Outputs

- `pitch_deck.pptx` — editable 16:9 deck, dark theme, speaker notes embedded
- `pitch_script.md` — slide-by-slide timed script with timestamps, evidence references, and claim warnings
- `demo_checklist.md` — evidence-backed demo steps, prerequisites, backup plan
- `generation_summary.json` — generation mode, warnings, flagged claims

Sample files from a **synthetic** project are in [`sample_output/`](sample_output/) (regenerate with `make samples`).

## Safety and claim quality

Repository text is **untrusted input**. HackPack skips secret-bearing files (`.env` except examples, private keys, credential folders, lockfiles, `node_modules`), redacts common token formats, enforces file-size/count/time budgets, and never executes repository code.

The verifier applies strict rules: numerical claims need the value, the metric name, and a test/evaluation context in inspected content before they are upgraded beyond `needs_verification`; README-only support counts as team-authored text, not proof; deployment, adoption, user counts, and business impact are never inferred from code existence. Unsupported numeric claims are omitted from exported slides and listed for review instead.

Prompt injection through READMEs or comments cannot be fully prevented; the system prompt instructs the model to treat repository content as data, but **review the generated result**. Errors returned by the API never include API keys or repository text.

An internet-facing deployment needs abuse protection (rate limiting, auth, a reverse proxy) that v0.1 intentionally does not ship.

## Tests

```bash
python -m pytest tests/ -v      # core library + API (98 tests, offline)
cd frontend && npm test         # frontend unit + contract mapping (21 tests)
cd frontend && npm run typecheck
```

Both suites run without a GitHub token, API key, network access, or an installed model — provider and network calls are mocked in the default run.

The frontend suite also includes an opt-in live end-to-end contract test that drives the real frontend mapping code against a running backend (analyze → pitch → generate):

```bash
# with `uvicorn api.main:app` running on :8000
cd frontend && HACKPACK_LIVE_API=1 npm test
```

## Repository layout

```text
HackPack/
├── api/                       # FastAPI app, schemas, routes
│   ├── main.py                # create_app(), CORS, size guard, health
│   ├── schemas.py
│   └── routes/                # analyze · pitch · generate
├── hackpack/                  # core library (no FastAPI dependency)
│   ├── models.py              # Pydantic v2 contracts
│   ├── llm_client.py          # LiteLLM adapter + fallback contract
│   ├── engine/
│   │   ├── repo_analyzer.py   # read-only, bounded GitHub analysis
│   │   ├── verifier.py        # conservative claim verification
│   │   ├── pitch_builder.py   # AI draft + deterministic fallback
│   │   └── evidence_store.py
│   └── generators/            # pptx · script · demo · zip bundle
├── app/main.py                # optional local Streamlit UI
├── frontend/                  # React 19 + TanStack Start web app
│   ├── src/lib/api.ts         # typed API client + contract mapping
│   ├── src/lib/workflow.ts    # step gating + local draft fallback
│   ├── src/routes/index.tsx   # four-step workspace UI
│   └── tests/                 # vitest unit + opt-in live E2E
├── config.py                  # pydantic-settings configuration
├── scripts/make_sample_output.py
├── tests/                     # pytest suite (offline)
└── sample_output/             # synthetic, labelled examples
```

## Roadmap

- [x] Public repository analysis foundation
- [x] Evidence-classified six-slide pitch pipeline with fallback
- [x] FastAPI backend + ZIP deliverables
- [x] Editable PowerPoint and Markdown outputs
- [ ] Private repository authorization
- [ ] PDF export (v0.2)
- [ ] Job-based progress polling for large repositories
- [ ] User-editable slide layouts and themes
- [ ] Stronger static analysis for more languages
- [ ] Evaluation dataset of human-reviewed pitches

## Contributing

Issues and pull requests are welcome. Useful contributions include dependency parsers for more ecosystems, verification heuristics with fixtures proving they stay conservative, accessible slide layouts, and local-model compatibility notes.

Please do not contribute private repositories or secret-bearing data to sample fixtures. Keep tests deterministic and offline; do not execute imported project code.

## License

[MIT](LICENSE). Third-party dependencies and model weights (Ollama models, hosted-provider terms) carry their own licenses; review them independently. LiteLLM is Apache-2.0, `python-pptx` is MIT, PyGithub is LGPL-3.0 (usage via network API does not impose obligations on this repository).
