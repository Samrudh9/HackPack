import { normalizePublicGithubUrl } from './workflow'
import type {
  ApiHealth,
  DownloadLink,
  EvidenceStatus,
  GenerationResult,
  PitchClaim,
  PitchDraft,
  PitchSlide,
  ProjectFormState,
  RepositoryAnalysis,
} from '../types/hackpack'

const configuredBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ?? ''
const HEALTH_PATH = (import.meta.env.VITE_API_HEALTH_PATH as string | undefined)?.trim() || '/api/health'
const ANALYZE_PATH = (import.meta.env.VITE_API_ANALYZE_PATH as string | undefined)?.trim() || '/api/analyze'
const PITCH_PATH = (import.meta.env.VITE_API_PITCH_PATH as string | undefined)?.trim() || '/api/pitch'
const GENERATE_PATH = (import.meta.env.VITE_API_GENERATE_PATH as string | undefined)?.trim() || '/api/generate'
const REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS || 45_000)

/** Backend EvidenceType values (hackpack.models.EvidenceType). */
const BACKEND_EVIDENCE_TYPES = new Set(['repo_evidence', 'test_evidence_found', 'team_provided', 'inferred', 'needs_verification'])

/** Backend field limits (hackpack.models): keep payloads inside them so the API never 422s on user input. */
const LIMITS = {
  slideCount: 6,
  projectName: 200,
  tagline: 300,
  slideTitle: 120,
  slideSubtitle: 240,
  bulletsPerSlide: 5,
  speakerNotes: 4000,
  secondsMin: 5,
  secondsMax: 900,
  totalDurationMin: 30,
  totalDurationMax: 1500,
  claimStatement: 400,
  claimSource: 400,
  claimAction: 500,
  claimsPerSlide: 30,
  unverifiedClaims: 100,
  generationWarnings: 30,
} as const

export class ApiError extends Error {
  readonly status?: number
  readonly detail?: unknown

  constructor(message: string, options?: { status?: number; detail?: unknown }) {
    super(message)
    this.name = 'ApiError'
    this.status = options?.status
    this.detail = options?.detail
  }
}

function getEndpoint(path: string): string {
  if (!configuredBase) {
    throw new ApiError('Backend URL is not configured. Set VITE_API_BASE_URL and restart the frontend.')
  }
  const base = configuredBase.endsWith('/') ? configuredBase : `${configuredBase}/`
  return new URL(path.replace(/^\//, ''), base).toString()
}

async function fetchWithTimeout(url: string, init: RequestInit = {}): Promise<Response> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  try {
    return await fetch(url, { ...init, signal: controller.signal })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(`The backend did not respond within ${Math.round(REQUEST_TIMEOUT_MS / 1000)} seconds.`)
    }
    throw new ApiError('Could not reach the backend. Check the API URL, server status, and CORS configuration.')
  } finally {
    window.clearTimeout(timeout)
  }
}

async function parseJsonResponse(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return {}
  try {
    return JSON.parse(text) as unknown
  } catch {
    throw new ApiError('The backend returned a response that was not valid JSON.', { status: response.status })
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function firstValue(record: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    if (record[key] !== undefined && record[key] !== null) return record[key]
  }
  return undefined
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : typeof value === 'number' ? String(value) : fallback
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => typeof item === 'string' ? item : asString(firstValue(asRecord(item), ['path', 'name', 'title', 'url']))).filter(Boolean)
}

function safeLink(value: unknown, name: string, baseUrl: string): DownloadLink | null {
  if (typeof value !== 'string' || !value.trim()) return null
  try {
    const url = new URL(value, baseUrl)
    if (url.protocol !== 'https:' && url.protocol !== 'http:') return null
    return { name, url: url.toString() }
  } catch {
    return null
  }
}

function asEvidenceItems(value: unknown, prefix: string): RepositoryAnalysis['techStack'] {
  if (!Array.isArray(value)) return []
  return value.map((raw, index) => {
    const item = asRecord(raw)
    const title = asString(firstValue(item, ['name', 'title', 'module', 'path']), `${prefix} ${index + 1}`)
    const source = asString(firstValue(item, ['evidence_file', 'source', 'file', 'path'])) || undefined
    const detail = asString(firstValue(item, ['purpose', 'description', 'detail', 'version', 'category']), source ? `Detected from ${source}` : 'Detected by repository analysis.')
    return {
      id: `${prefix}-${index}-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`,
      title,
      detail,
      status: 'repo_evidence' as const,
      source,
      lineStart: typeof item.line_start === 'number' ? item.line_start : undefined,
      lineEnd: typeof item.line_end === 'number' ? item.line_end : undefined,
    }
  })
}

export function normalizeAnalysisResponse(input: unknown, repoUrl: string): RepositoryAnalysis {
  const root = asRecord(input)
  const evidence = asRecord(firstValue(root, ['evidence', 'analysis', 'repository', 'repo_evidence']) ?? root)
  const repoName = asString(firstValue(evidence, ['repo_name', 'repository_name', 'repositoryName', 'name'])) ||
    normalizePublicGithubUrl(repoUrl)?.split('/').pop() || 'GitHub repository'
  const description = asString(firstValue(evidence, ['description', 'readme_description', 'summary']))
  const languagesRaw = asRecord(firstValue(evidence, ['languages', 'language_bytes']))
  const languages = Array.isArray(evidence.languages)
    ? (evidence.languages as unknown[]).map((entry) => {
        const language = asRecord(entry)
        return { name: asString(firstValue(language, ['name', 'language'])), bytes: typeof language.bytes === 'number' ? language.bytes : undefined }
      }).filter((entry) => entry.name)
    : Object.entries(languagesRaw).map(([name, bytes]) => ({ name, bytes: typeof bytes === 'number' ? bytes : undefined }))
  const techStack = asEvidenceItems(firstValue(evidence, ['tech_stack', 'techStack', 'technologies']), 'stack')
  const keyModules = asEvidenceItems(firstValue(evidence, ['key_modules', 'keyModules', 'modules']), 'module')
  const files = asStringArray(firstValue(evidence, ['file_tree', 'fileTree', 'files']))
  const demoUrls = asStringArray(firstValue(evidence, ['demo_urls', 'demoUrls', 'live_demo_urls']))
  const summaryRecord = asRecord(root.summary)
  const warningValues = [
    ...asStringArray(firstValue(root, ['warnings', 'errors'])),
    // The HackPack backend returns analyzer warnings on the evidence object and in the summary.
    ...asStringArray(firstValue(evidence, ['analysis_warnings', 'analyzer_warnings', 'warnings'])),
    ...asStringArray(firstValue(summaryRecord, ['warnings'])),
  ]
  const unknownValues = asStringArray(firstValue(root, ['unknowns', 'unknown', 'missing_information']))
  const signals = [
    { label: 'Tests', available: Boolean(firstValue(evidence, ['has_tests', 'hasTests', 'tests'])) },
    { label: 'CI workflows', available: Boolean(firstValue(evidence, ['has_ci', 'hasCi', 'ci_enabled'])) },
    { label: 'Docker', available: Boolean(firstValue(evidence, ['has_docker', 'hasDocker', 'docker'])) },
    { label: 'Live demo', available: Boolean(firstValue(evidence, ['has_demo', 'hasDemo', 'demo_url']) || demoUrls.length) },
  ]
  const warnings = [...warningValues]
  const unknowns = [...unknownValues]
  const hasReadmeContent = Boolean(firstValue(evidence, ['readme_content', 'readmeContent', 'readme']))
  const hasReadmePath = files.some((path) => /(^|\/)readme(?:\.[^/]+)?$/i.test(path))
  if (!hasReadmeContent && !hasReadmePath) unknowns.push('README content was not returned or detected in the file tree.')
  if (!techStack.length) unknowns.push('Technology stack could not be detected from the returned data.')
  return {
    repositoryUrl: asString(firstValue(evidence, ['repo_url', 'repoUrl', 'url']), repoUrl),
    repositoryName: repoName,
    description,
    primaryLanguage: asString(firstValue(evidence, ['primary_language', 'primaryLanguage', 'language'])) || null,
    languages,
    techStack,
    keyModules,
    files,
    signals,
    demoUrls,
    warnings: [...new Set(warnings)],
    unknowns: [...new Set(unknowns)],
    raw: evidence,
  }
}

/**
 * This request mapper is the single place to align payload keys to an existing backend contract.
 * The current default uses the common `repo_url` shape from the HackPack implementation brief.
 */
export function buildAnalyzePayload(repoUrl: string): Record<string, unknown> {
  const normalized = normalizePublicGithubUrl(repoUrl)
  if (!normalized) throw new ApiError('Enter a valid public GitHub repository URL.')
  return { repo_url: normalized }
}

export async function checkBackendHealth(): Promise<ApiHealth> {
  if (!configuredBase) {
    return { connected: false, message: 'API URL not configured' }
  }
  try {
    const response = await fetchWithTimeout(getEndpoint(HEALTH_PATH), { method: 'GET', headers: { Accept: 'application/json' } })
    if (!response.ok) return { connected: false, message: `Backend returned HTTP ${response.status}` }
    const body = asRecord(await parseJsonResponse(response))
    return {
      connected: true,
      message: asString(firstValue(body, ['status', 'message']), 'Backend connected'),
      version: asString(body.version) || undefined,
    }
  } catch (error) {
    return { connected: false, message: error instanceof Error ? error.message : 'Backend is unreachable' }
  }
}

export async function analyzeRepository(repoUrl: string): Promise<RepositoryAnalysis> {
  const response = await fetchWithTimeout(getEndpoint(ANALYZE_PATH), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(buildAnalyzePayload(repoUrl)),
  })
  const body = await parseJsonResponse(response)
  if (!response.ok) {
    const record = asRecord(body)
    throw new ApiError(formatApiDetail(firstValue(record, ['detail', 'message', 'error'])) ?? `Repository analysis failed (HTTP ${response.status}).`, { status: response.status, detail: body })
  }
  const root = asRecord(body)
  const candidate = asRecord(firstValue(root, ['evidence', 'analysis', 'repository', 'repo_evidence']) ?? root)
  const recognizedKeys = ['repo_url', 'repoUrl', 'repo_name', 'repoName', 'repository_name', 'repositoryName', 'description', 'readme_content', 'readmeContent', 'file_tree', 'fileTree', 'tech_stack', 'techStack', 'primary_language', 'primaryLanguage', 'key_modules', 'keyModules']
  if (!recognizedKeys.some((key) => Object.prototype.hasOwnProperty.call(candidate, key))) {
    throw new ApiError('The backend returned HTTP success, but its analysis response shape was not recognized. Align normalizeAnalysisResponse() with the existing FastAPI schema.', { detail: body })
  }
  return normalizeAnalysisResponse(body, repoUrl)
}

function clampInt(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value)) return fallback
  return Math.max(min, Math.min(max, Math.round(value)))
}

function sliceText(value: string | undefined | null, max: number): string {
  const text = (value ?? '').trim()
  return text.length > max ? text.slice(0, max) : text
}

function splitLines(value: string): string[] {
  return value.split('\n').map((item) => item.trim()).filter(Boolean)
}

/** Render FastAPI/Pydantic error details (string or list) as readable text. */
export function formatApiDetail(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      const record = asRecord(item)
      const location = asString(firstValue(record, ['loc']))
      const message = asString(record.msg)
      if (!message) return ''
      return location ? `${location.replace(/^body\.,?/, '').replace(/\./g, ' ')}: ${message}` : message
    }).filter(Boolean)
    if (messages.length) return messages.join('; ')
  }
  return null
}

function normalizeEvidenceStatus(value: unknown): EvidenceStatus {
  if (typeof value === 'string' && (BACKEND_EVIDENCE_TYPES.has(value) || value === 'unknown')) {
    return value as EvidenceStatus
  }
  // Anything unrecognised is presented as needing verification, never as proven.
  return 'needs_verification'
}

/**
 * Map the hackathon form onto the backend's HackathonBrief + TeamContext
 * contracts (hackpack.models), respecting their field limits.
 */
export function buildPitchPayload(form: ProjectFormState): { brief: Record<string, unknown>; team: Record<string, unknown> } {
  const brief = {
    event_name: sliceText(form.eventName, 200) || 'Hackathon',
    theme: sliceText(form.eventBrief, 400) || undefined,
    judging_criteria: splitLines(form.judgingCriteria).slice(0, 20),
    pitch_duration_minutes: clampInt(form.pitchDurationMinutes, 1, 20, 3),
    required_deliverables: form.requiredDeliverables.slice(0, 20),
    additional_rules: sliceText(form.additionalRules, 1000) || undefined,
  }
  const team = {
    problem_statement: sliceText(form.problemStatement, 2000),
    solution_summary: sliceText(form.solutionDescription, 2000),
    target_users: sliceText(form.targetUsers, 1000),
    key_results: sliceText(form.measuredResults, 2000) || null,
    impact_claims: [sliceText(form.expectedImpact, 1000)].filter(Boolean),
    future_plans: sliceText(form.futurePlans, 1500) || null,
    team_members: form.teamMembers.split(',').map((item) => item.trim()).filter(Boolean).slice(0, 20),
  }
  return { brief, team }
}

/** Convert a backend PitchDeck (snake_case) into the editable PitchDraft shape. */
export function mapBackendDeckToDraft(input: unknown, responseWarnings: string[] = []): PitchDraft {
  const deck = asRecord(input)
  const slidesRaw = Array.isArray(deck.slides) ? deck.slides : []
  const slides: PitchSlide[] = slidesRaw.map((raw, index) => {
    const slide = asRecord(raw)
    const number = typeof slide.slide_number === 'number' ? slide.slide_number : index + 1
    const claimsRaw = Array.isArray(slide.claims) ? slide.claims : []
    return {
      id: `slide-${number}`,
      title: asString(slide.title, `Slide ${number}`),
      subtitle: asString(slide.subtitle),
      bullets: asStringArray(slide.bullet_points),
      speakerNotes: asString(slide.speaker_notes),
      seconds: typeof slide.speaking_time_seconds === 'number' ? slide.speaking_time_seconds : 30,
      claims: claimsRaw.map((rawClaim, claimIndex) => {
        const claim = asRecord(rawClaim)
        const lineStart = typeof claim.line_start === 'number' && claim.line_start >= 1 ? claim.line_start : undefined
        const lineEnd = typeof claim.line_end === 'number' && claim.line_end >= 1 ? claim.line_end : undefined
        return {
          id: `claim-${number}-${claimIndex}`,
          statement: asString(claim.statement, 'Unnamed claim'),
          status: normalizeEvidenceStatus(claim.evidence_type),
          source: asString(claim.source) || undefined,
          lineStart,
          lineEnd,
          action: asString(claim.needs_action) || undefined,
        }
      }),
    }
  })
  const totalSeconds = typeof deck.total_duration_seconds === 'number'
    ? deck.total_duration_seconds
    : slides.reduce((sum, slide) => sum + slide.seconds, 0)
  return {
    projectName: asString(deck.project_name, 'Your project'),
    tagline: asString(deck.tagline),
    durationMinutes: Math.max(1, Math.round(totalSeconds / 60)),
    slides,
    warnings: [...new Set([...responseWarnings, ...asStringArray(deck.generation_warnings)])],
    generationMode: deck.generation_mode === 'ai' ? 'ai' : 'fallback',
    generationSource: 'backend',
  }
}

/**
 * Ask the backend for a verified pitch deck: AI draft when a model is
 * configured, deterministic template fallback otherwise. Callers should fall
 * back to buildLocalPitchDraft() when this throws.
 */
export async function generatePitch(input: { evidence: RepositoryAnalysis; form: ProjectFormState }): Promise<PitchDraft> {
  const { brief, team } = buildPitchPayload(input.form)
  const response = await fetchWithTimeout(getEndpoint(PITCH_PATH), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ evidence: input.evidence.raw, brief, team }),
  })
  const body = await parseJsonResponse(response)
  if (!response.ok) {
    const record = asRecord(body)
    throw new ApiError(
      formatApiDetail(firstValue(record, ['detail', 'message', 'error'])) ?? `Pitch generation failed (HTTP ${response.status}).`,
      { status: response.status, detail: body },
    )
  }
  const record = asRecord(body)
  const draft = mapBackendDeckToDraft(record.deck, asStringArray(record.warnings))
  if (draft.slides.length !== LIMITS.slideCount) {
    throw new ApiError('The backend returned a pitch without exactly six slides.', { status: response.status, detail: body })
  }
  return draft
}

function buildClaimPayload(claim: PitchClaim, confidence?: number): Record<string, unknown> | null {
  const statement = sliceText(claim.statement, LIMITS.claimStatement)
  if (!statement) return null
  const lineStart = typeof claim.lineStart === 'number' && claim.lineStart >= 1 ? claim.lineStart : null
  const lineEnd = typeof claim.lineEnd === 'number' && claim.lineEnd >= 1 ? claim.lineEnd : null
  return {
    statement,
    evidence_type: BACKEND_EVIDENCE_TYPES.has(claim.status) ? claim.status : 'needs_verification',
    source: sliceText(claim.source, LIMITS.claimSource) || null,
    line_start: lineStart,
    line_end: lineEnd,
    needs_action: sliceText(claim.action, LIMITS.claimAction) || null,
    ...(confidence !== undefined ? { confidence } : {}),
  }
}

/**
 * Map the editable draft onto the backend GenerateRequest (`deck` + `evidence`),
 * sanitizing every field to the backend's validation limits so user edits can
 * never produce a 422.
 */
export function buildGeneratePayload(input: {
  evidence: RepositoryAnalysis
  pitch: PitchDraft
  form: ProjectFormState
}): Record<string, unknown> {
  const slides = input.pitch.slides.slice(0, LIMITS.slideCount).map((slide, index) => ({
    slide_number: index + 1,
    title: sliceText(slide.title, LIMITS.slideTitle) || `Slide ${index + 1}`,
    subtitle: sliceText(slide.subtitle, LIMITS.slideSubtitle) || null,
    bullet_points: slide.bullets.map((bullet) => bullet.trim()).filter(Boolean).slice(0, LIMITS.bulletsPerSlide),
    speaker_notes: slide.speakerNotes.slice(0, LIMITS.speakerNotes),
    speaking_time_seconds: clampInt(slide.seconds, LIMITS.secondsMin, LIMITS.secondsMax, LIMITS.secondsMin),
    claims: slide.claims
      .map((claim) => buildClaimPayload(claim))
      .filter((claim): claim is Record<string, unknown> => claim !== null)
      .slice(0, LIMITS.claimsPerSlide),
  }))
  const unverifiedClaims = input.pitch.slides
    .flatMap((slide) => slide.claims)
    .filter((claim) => claim.status === 'needs_verification' || claim.status === 'unknown' || claim.status === 'inferred')
    .map((claim) => buildClaimPayload(claim, 0))
    .filter((claim): claim is Record<string, unknown> => claim !== null)
    .slice(0, LIMITS.unverifiedClaims)
    .map((claim) => ({ ...claim, needs_action: claim.needs_action ?? 'Confirm this claim before presenting.' }))

  return {
    deck: {
      project_name: sliceText(input.pitch.projectName, LIMITS.projectName) || 'Hackathon project',
      tagline: sliceText(input.pitch.tagline, LIMITS.tagline) || 'A hackathon project',
      total_duration_seconds: clampInt(
        slides.reduce((sum, slide) => sum + slide.speaking_time_seconds, 0),
        LIMITS.totalDurationMin,
        LIMITS.totalDurationMax,
        LIMITS.totalDurationMin,
      ),
      slides,
      // Honest labeling: only decks the backend model produced are marked "ai".
      generation_mode: input.pitch.generationMode === 'ai' ? 'ai' : 'fallback',
      generation_warnings: input.pitch.warnings.map((warning) => warning.trim()).filter(Boolean).slice(0, LIMITS.generationWarnings),
      unverified_claims: unverifiedClaims,
    },
    evidence: input.evidence.raw,
    demo_duration_seconds: 120,
  }
}

export async function generateDeliverables(input: {
  evidence: RepositoryAnalysis
  pitch: PitchDraft
  form: ProjectFormState
}): Promise<GenerationResult> {
  const response = await fetchWithTimeout(getEndpoint(GENERATE_PATH), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/zip, application/octet-stream, application/json' },
    body: JSON.stringify(buildGeneratePayload(input)),
  })

  if (!response.ok) {
    let detail: unknown
    try { detail = await parseJsonResponse(response) } catch { detail = await response.text().catch(() => '') }
    const record = asRecord(detail)
    throw new ApiError(formatApiDetail(firstValue(record, ['detail', 'message', 'error'])) ?? `Deliverable generation failed (HTTP ${response.status}).`, { status: response.status, detail })
  }

  const contentType = response.headers.get('content-type')?.toLowerCase() ?? ''
  if (!contentType.includes('application/json')) {
    const blob = await response.blob()
    const disposition = response.headers.get('content-disposition') ?? ''
    const match = /filename\*?=(?:UTF-8''|\")?([^\";]+)/i.exec(disposition)
    const filename = match?.[1] ? decodeURIComponent(match[1].replace(/"/g, '')) : (contentType.includes('presentation') ? 'hackpack-pitch.pptx' : 'hackpack-deliverables.zip')
    const objectUrl = URL.createObjectURL(blob)
    return { downloads: [{ name: filename, url: objectUrl, description: 'Generated by the HackPack backend.' }], warnings: [] }
  }

  const body = await parseJsonResponse(response)
  const root = asRecord(body)
  const downloads: DownloadLink[] = []
  const baseUrl = getEndpoint(GENERATE_PATH)
  const directDownload = firstValue(root, ['download_url', 'downloadUrl', 'url', 'archive_url'])
  const directLink = safeLink(directDownload, asString(firstValue(root, ['filename', 'file_name']), 'hackpack-deliverables.zip'), baseUrl)
  if (directLink) downloads.push(directLink)

  const filesRaw = firstValue(root, ['files', 'downloads', 'artifacts'])
  if (Array.isArray(filesRaw)) {
    filesRaw.forEach((file, index) => {
      const record = asRecord(file)
      const link = safeLink(firstValue(record, ['url', 'download_url', 'href']), asString(firstValue(record, ['name', 'filename', 'label']), `Download ${index + 1}`), baseUrl)
      if (link) downloads.push(link)
    })
  } else {
    Object.entries(asRecord(filesRaw)).forEach(([name, value]) => {
      const record = asRecord(value)
      const candidate = typeof value === 'string' ? value : firstValue(record, ['url', 'download_url', 'href'])
      const link = safeLink(candidate, asString(firstValue(record, ['name', 'filename']), name), baseUrl)
      if (link) downloads.push(link)
    })
  }

  if (!downloads.length) {
    throw new ApiError('The backend responded, but no downloadable file URL was found. Align normalize generation response in src/lib/api.ts with the FastAPI response schema.', { detail: body })
  }

  const warningValues = asStringArray(firstValue(root, ['warnings', 'errors']))
  return { downloads: downloads.filter((link, index, all) => all.findIndex((other) => other.url === link.url) === index), warnings: warningValues, summary: asRecord(root.summary), raw: body }
}

export function getApiConfiguration(): { baseUrl: string; healthPath: string; analyzePath: string; pitchPath: string; generatePath: string } {
  return { baseUrl: configuredBase, healthPath: HEALTH_PATH, analyzePath: ANALYZE_PATH, pitchPath: PITCH_PATH, generatePath: GENERATE_PATH }
}
