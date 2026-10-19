# HackPack Frontend

React 19 + TanStack Start web app for the HackPack workspace. It talks to the FastAPI backend in the repository root over HTTP and keeps all state in React memory — no accounts, database, or browser persistence.

## Requirements

- Node.js 22.12+ (see `package.json` engines)
- npm
- The FastAPI backend running and reachable (default `http://localhost:8000`)

## Run locally

```bash
npm install
cp .env.example .env
npm run dev
```

Open the URL Vite prints (default port 3000). Start the backend from the repository root:

```bash
uvicorn api.main:app --reload
```

If the backend is unreachable the UI stays usable and shows a truthful disconnected/error state. It never fabricates successful API results.

## Backend configuration

Configure `.env` with the backend base URL and endpoint paths:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_API_HEALTH_PATH=/api/health
VITE_API_ANALYZE_PATH=/api/analyze
VITE_API_PITCH_PATH=/api/pitch
VITE_API_GENERATE_PATH=/api/generate
VITE_API_TIMEOUT_MS=90000
VITE_OPEN_SOURCE_REPO_URL=https://github.com/your-actual-org/your-actual-repository
```

These defaults match the backend in this repository (`api/schemas.py`, `hackpack/models.py`) and are exercised by `tests/e2e.contract.test.ts`. All request/response mapping lives in `src/lib/api.ts`:

- `buildAnalyzePayload()` / `normalizeAnalysisResponse()` — repository analysis request and response adapter.
- `buildPitchPayload()` — maps the form onto the backend `HackathonBrief` + `TeamContext` within their field limits.
- `mapBackendDeckToDraft()` — converts the backend `PitchDeck` into the editable draft shape.
- `buildGeneratePayload()` — sanitizes the edited draft to the backend's validation limits and sends it under the `deck` key.
- `generateDeliverables()` — normalizes the ZIP response into a browser download.

Keep `VITE_API_TIMEOUT_MS` above the backend's `ANALYSIS_TIME_BUDGET_SECONDS` (default 60) so large repositories never time out client-side.

### CORS

The backend allows **exact** origins only (wildcards are rejected). Its defaults include `http://localhost:3000`, `http://localhost:3001`, `http://localhost:5173`, and `http://localhost:8501`. Add your deployed origin to `CORS_ALLOW_ORIGINS` on the backend before shipping. A deployed frontend cannot reach `localhost` on a developer machine — point `VITE_API_BASE_URL` at a deployed backend.

Do not put backend secrets in `VITE_*` variables: they are embedded in browser code.

## Workflow behavior

1. **Project:** collects a public GitHub URL and hackathon brief; team context is optional.
2. **Analysis:** `POST /api/analyze`, then shows repository evidence, warnings, and unknowns.
3. **Pitch:** the backend `POST /api/pitch` produces the six-slide deck and the verifier assigns every claim's evidence label. If that call fails, the app falls back to an in-browser draft built only from returned repository data and explicitly labels it as a local fallback.
4. **Review:** slides are editable. Claim evidence labels do not change when slide wording is edited, and the cover shows whether the draft is `ai` (backend model) or `fallback` (template or local draft).
5. **Export:** the reviewed deck is sanitized into the backend contract and submitted to `POST /api/generate`. Files appear only when the backend returns a ZIP.

## Tests and checks

```bash
npm test          # vitest unit + contract mapping tests
npm run typecheck # vite build + tsc --noEmit
npm run build
```

An opt-in live end-to-end contract test drives the real frontend mapping code against a running backend:

```bash
# with `uvicorn api.main:app` running on :8000
HACKPACK_LIVE_API=1 npm test
```

It skips automatically (so the default suite stays offline).

## Current limitations

- Public GitHub repositories only in this UI iteration.
- The backend must be reachable over HTTP; there is no offline/mock data mode.
- PDF output is not produced unless the backend returns one in an archive.
- Repository evidence means content was detected — not that a feature is tested or working in production.
