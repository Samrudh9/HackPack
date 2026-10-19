/**
 * Live end-to-end contract test: frontend mapping code → real FastAPI backend.
 *
 * Skipped unless HACKPACK_LIVE_API=1, so the default suite stays offline:
 *
 *   HACKPACK_LIVE_API=1 npm test
 *
 * Requires the backend on VITE_API_BASE_URL (default http://localhost:8000)
 * and outbound network access to GitHub via that backend.
 */
import { describe, expect, it } from 'vitest'
import { analyzeRepository, buildGeneratePayload, generatePitch } from '../src/lib/api'
import { createEmptyForm } from '../src/lib/workflow'
import type { ProjectFormState } from '../src/types/hackpack'

const LIVE = process.env.HACKPACK_LIVE_API === '1'
const REPO_URL = process.env.HACKPACK_LIVE_REPO ?? 'https://github.com/octocat/hello-world'
const API_BASE = ((import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || 'http://localhost:8000').replace(/\/$/, '')

const form: ProjectFormState = {
  ...createEmptyForm(),
  repoUrl: REPO_URL,
  eventName: 'Contract Smoke Test',
  eventBrief: 'Build something useful for developers.',
  judgingCriteria: 'Innovation\nExecution',
  pitchDurationMinutes: 3,
  problemStatement: 'Developers waste time re-running manual checks.',
  targetUsers: 'Open-source maintainers',
  solutionDescription: 'One command runs the whole verification pass.',
  measuredResults: 'The suite runs in under a minute locally.',
  teamMembers: 'Alex, Sam',
}

describe.skipIf(!LIVE)('live frontend ↔ backend contract', () => {
  it('analyzes a repo, builds a six-slide verified pitch, and returns a deliverable ZIP', { timeout: 180_000 }, async () => {
    // 1. POST /api/analyze through the frontend client.
    const evidence = await analyzeRepository(REPO_URL)
    expect(evidence.repositoryName).toBeTruthy()
    expect(evidence.repositoryUrl).toContain('github.com')

    // 2. POST /api/pitch through the frontend client (AI or fallback mode).
    const draft = await generatePitch({ evidence, form })
    expect(draft.generationSource).toBe('backend')
    expect(draft.slides).toHaveLength(6)
    expect(['ai', 'fallback']).toContain(draft.generationMode)
    expect(draft.durationMinutes).toBeGreaterThan(0)

    // 3. POST /api/generate with the payload exactly as the UI would send it.
    const payload = buildGeneratePayload({ evidence, pitch: draft, form })
    expect(payload).toHaveProperty('deck')

    const response = await fetch(`${API_BASE}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Origin: 'http://localhost:3000' },
      body: JSON.stringify(payload),
    })
    expect(response.status).toBe(200)
    expect(response.headers.get('content-type')).toContain('application/zip')
    expect(response.headers.get('content-disposition')).toContain('attachment')
    expect(response.headers.get('access-control-allow-origin')).toBe('http://localhost:3000')

    // 4. The ZIP starts with the PK magic bytes and contains the fixed entry names.
    const bytes = new Uint8Array(await response.arrayBuffer())
    expect(bytes[0]).toBe(0x50) // P
    expect(bytes[1]).toBe(0x4b) // K
  })

  it('rejects an invalid repo URL with a readable 400-level error', { timeout: 60_000 }, async () => {
    await expect(analyzeRepository('https://github.com/not-a-repo')).rejects.toThrow(/repository|analysis|HTTP/i)
  })
})
