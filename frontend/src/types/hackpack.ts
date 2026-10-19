export type WorkflowStep = 'project' | 'analysis' | 'review' | 'export'

export type EvidenceStatus =
  | 'repo_evidence'
  | 'test_evidence_found'
  | 'team_provided'
  | 'inferred'
  | 'needs_verification'
  | 'unknown'

export interface ProjectFormState {
  repoUrl: string
  eventName: string
  eventBrief: string
  judgingCriteria: string
  pitchDurationMinutes: number
  requiredDeliverables: string[]
  additionalRules: string
  problemStatement: string
  targetUsers: string
  solutionDescription: string
  measuredResults: string
  expectedImpact: string
  futurePlans: string
  teamMembers: string
  demoUrl: string
}

export interface EvidenceItem {
  id: string
  title: string
  detail: string
  status: EvidenceStatus
  source?: string
  lineStart?: number
  lineEnd?: number
}

export interface RepositoryAnalysis {
  repositoryUrl: string
  repositoryName: string
  description: string
  primaryLanguage: string | null
  languages: Array<{ name: string; bytes?: number }>
  techStack: EvidenceItem[]
  keyModules: EvidenceItem[]
  files: string[]
  signals: Array<{ label: string; available: boolean; detail?: string }>
  demoUrls: string[]
  warnings: string[]
  unknowns: string[]
  raw: unknown
}

export interface PitchClaim {
  id: string
  statement: string
  status: EvidenceStatus
  source?: string
  lineStart?: number
  lineEnd?: number
  action?: string
}

export interface PitchSlide {
  id: string
  title: string
  subtitle: string
  bullets: string[]
  speakerNotes: string
  seconds: number
  claims: PitchClaim[]
}

export interface PitchDraft {
  projectName: string
  tagline: string
  durationMinutes: number
  slides: PitchSlide[]
  warnings: string[]
  /** 'ai' = backend model draft; 'fallback' = deterministic template or local draft. */
  generationMode?: 'ai' | 'fallback'
  /** Where the draft came from: the backend pitch endpoint or the in-browser fallback. */
  generationSource?: 'backend' | 'local'
}

export interface DownloadLink {
  name: string
  url: string
  description?: string
}

export interface GenerationResult {
  downloads: DownloadLink[]
  warnings: string[]
  summary?: Record<string, unknown>
  raw?: unknown
}

export interface ApiHealth {
  connected: boolean
  message: string
  version?: string
}

export const DEFAULT_PROJECT_FORM: ProjectFormState = {
  repoUrl: '',
  eventName: '',
  eventBrief: '',
  judgingCriteria: '',
  pitchDurationMinutes: 3,
  requiredDeliverables: ['Pitch deck', 'Demo checklist'],
  additionalRules: '',
  problemStatement: '',
  targetUsers: '',
  solutionDescription: '',
  measuredResults: '',
  expectedImpact: '',
  futurePlans: '',
  teamMembers: '',
  demoUrl: '',
}

export const EVIDENCE_LABELS: Record<EvidenceStatus, string> = {
  repo_evidence: 'Repository evidence',
  test_evidence_found: 'Test evidence found',
  team_provided: 'Team provided',
  inferred: 'Inferred',
  needs_verification: 'Needs verification',
  unknown: 'Unknown',
}
