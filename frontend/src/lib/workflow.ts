import {
  DEFAULT_PROJECT_FORM,
  EVIDENCE_LABELS,
  type EvidenceStatus,
  type PitchClaim,
  type PitchDraft,
  type PitchSlide,
  type ProjectFormState,
  type RepositoryAnalysis,
  type WorkflowStep,
} from '../types/hackpack'

const STEP_ORDER: WorkflowStep[] = ['project', 'analysis', 'review', 'export']

export function normalizePublicGithubUrl(value: string): string | null {
  try {
    const parsed = new URL(value.trim())
    if (parsed.protocol !== 'https:' || parsed.hostname.toLowerCase() !== 'github.com') return null
    const parts = parsed.pathname.replace(/\.git$/i, '').split('/').filter(Boolean)
    if (parts.length !== 2 || parts.some((part) => part === '.' || part === '..')) return null
    return `https://github.com/${parts[0]}/${parts[1]}`
  } catch {
    return null
  }
}

export function getProjectValidation(form: ProjectFormState): Record<string, string> {
  const errors: Record<string, string> = {}
  if (!normalizePublicGithubUrl(form.repoUrl)) {
    errors.repoUrl = 'Enter a public GitHub URL in the format https://github.com/owner/repository.'
  }
  if (!form.eventBrief.trim()) {
    errors.eventBrief = 'Add the hackathon brief or the challenge you are building for.'
  }
  return errors
}

export function canAdvanceStep(
  target: WorkflowStep,
  form: ProjectFormState,
  analysis: RepositoryAnalysis | null,
  pitch: PitchDraft | null,
): boolean {
  const targetIndex = STEP_ORDER.indexOf(target)
  if (targetIndex <= 0) return true
  if (Object.keys(getProjectValidation(form)).length > 0) return false
  if (targetIndex >= 2 && (!analysis || !pitch || pitch.slides.length === 0)) return false
  return true
}

export function classifyEvidence(input: {
  hasRepositorySource?: boolean
  hasTestSource?: boolean
  teamProvided?: boolean
  inferred?: boolean
  explicitlyUnverified?: boolean
}): EvidenceStatus {
  if (input.explicitlyUnverified) return 'needs_verification'
  if (input.hasTestSource) return 'test_evidence_found'
  if (input.hasRepositorySource) return 'repo_evidence'
  if (input.teamProvided) return 'team_provided'
  if (input.inferred) return 'inferred'
  return 'unknown'
}

function makeClaim(statement: string, status: EvidenceStatus, source?: string): PitchClaim {
  return {
    id: `${status}-${statement.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 48)}`,
    statement,
    status,
    source,
    action: status === 'needs_verification' || status === 'unknown' ? 'Confirm this before presenting.' : undefined,
  }
}

function compactList(items: string[], max = 4): string[] {
  return items.map((item) => item.trim()).filter(Boolean).slice(0, max)
}

export function buildLocalPitchDraft(
  form: ProjectFormState,
  analysis: RepositoryAnalysis,
): PitchDraft {
  const projectName = analysis.repositoryName || normalizePublicGithubUrl(form.repoUrl)?.split('/').pop() || 'Your project'
  const stack = analysis.techStack.slice(0, 5)
  const stackNames = stack.map((item) => item.title)
  const moduleDetails = analysis.keyModules.slice(0, 3).map((item) => `${item.title}: ${item.detail}`)
  const teamProblem = form.problemStatement.trim()
  const brief = form.eventBrief.trim()
  const solution = form.solutionDescription.trim() || analysis.description.trim()
  const audience = form.targetUsers.trim()
  const results = form.measuredResults.trim()
  const durationSeconds = Math.max(60, Math.min(600, form.pitchDurationMinutes * 60))
  const secondsPerSlide = Math.floor(durationSeconds / 6)
  const remainder = durationSeconds % 6

  const slides: PitchSlide[] = [
    {
      id: 'problem', title: 'The problem', subtitle: audience ? `Designed for ${audience}` : 'Who needs a better solution?',
      bullets: compactList([teamProblem || brief, audience ? `Intended audience: ${audience}` : '', 'Add a concrete example or evidence of this problem before presenting.']),
      speakerNotes: `Introduce the challenge in simple language. Explain who is affected and why this matters. Replace assumptions with evidence from your team or event brief.`,
      seconds: secondsPerSlide + (remainder > 0 ? 1 : 0),
      claims: [makeClaim(teamProblem || brief, teamProblem ? 'team_provided' : 'team_provided', 'Team context / hackathon brief')],
    },
    {
      id: 'solution', title: 'Our solution', subtitle: solution ? 'What the team is building' : 'Describe the solution in one sentence',
      bullets: compactList([solution || 'Add a short description of what your product does.', ...analysis.techStack.slice(0, 2).map((item) => `Uses ${item.title}`)]),
      speakerNotes: `Explain the solution and the primary action a user can take. Focus on what has been built, not only what is planned.`,
      seconds: secondsPerSlide + (remainder > 1 ? 1 : 0),
      claims: [makeClaim(solution || 'The solution description has not been provided.', solution ? (form.solutionDescription.trim() ? 'team_provided' : 'repo_evidence') : 'needs_verification', form.solutionDescription.trim() ? 'Team context' : 'README or repository description')],
    },
    {
      id: 'how-it-works', title: 'How it works', subtitle: 'Implementation at a glance',
      bullets: compactList([
        analysis.primaryLanguage ? `Primary language: ${analysis.primaryLanguage}` : '',
        stackNames.length ? `Detected stack: ${stackNames.join(', ')}` : 'Technology stack needs review.',
        ...moduleDetails,
      ]),
      speakerNotes: `Walk judges through the main implementation flow. Treat detected dependencies as repository evidence, not proof that every feature runs correctly.`,
      seconds: secondsPerSlide,
      claims: [
        ...(analysis.primaryLanguage ? [makeClaim(`The repository's detected primary language is ${analysis.primaryLanguage}.`, 'repo_evidence', 'Repository metadata')] : []),
        ...stack.map((item) => makeClaim(`${item.title} is listed in the repository.`, 'repo_evidence', item.source)),
      ],
    },
    {
      id: 'demo', title: 'Demo highlights', subtitle: 'Show the clearest working path',
      bullets: compactList([
        ...analysis.demoUrls.map((url) => `Demo: ${url}`),
        ...analysis.signals.filter((signal) => signal.available).slice(0, 2).map((signal) => `${signal.label} detected`),
        form.demoUrl.trim() ? `Team-provided demo: ${form.demoUrl.trim()}` : '',
        'Rehearse the main user journey and prepare a backup recording or screenshots.',
      ]),
      speakerNotes: `Show one complete user journey. Confirm each feature works in the environment you will present from.`,
      seconds: secondsPerSlide,
      claims: [
        ...analysis.demoUrls.map((url) => makeClaim(`A demo link was found: ${url}`, 'repo_evidence', 'README or repository metadata')),
        ...(form.demoUrl.trim() ? [makeClaim(`The team supplied this demo link: ${form.demoUrl.trim()}`, 'team_provided', 'Team context')] : []),
      ],
    },
    {
      id: 'impact', title: 'Impact and results', subtitle: 'Be specific about what is proven',
      bullets: compactList([
        results ? `Team-reported result: ${results}` : 'No measured results have been supplied yet.',
        form.expectedImpact.trim() ? `Intended impact: ${form.expectedImpact.trim()}` : '',
        'Only include measured outcomes when the team can explain how they were measured.',
      ]),
      speakerNotes: results
        ? `Describe the result supplied by the team and explain how it was measured. It is team-provided until supported by relevant evaluation evidence.`
        : `Do not invent numbers or claim impact that has not been measured. State what still needs validation and what the team will measure next.`,
      seconds: secondsPerSlide,
      claims: [
        makeClaim(results || 'No measured result was provided.', results ? 'team_provided' : 'needs_verification', results ? 'Team-provided results — not independently verified' : undefined),
        ...(form.expectedImpact.trim() ? [makeClaim(form.expectedImpact.trim(), 'team_provided', 'Team-stated intended impact')] : []),
      ],
    },
    {
      id: 'next', title: "What's next", subtitle: 'The next milestone',
      bullets: compactList([form.futurePlans.trim() || 'Add the next milestone or experiment the team intends to complete.', ...analysis.unknowns.slice(0, 2).map((unknown) => `Confirm: ${unknown}`)]),
      speakerNotes: `Close with the next milestone and the outcome you want to validate. Keep the ask clear and realistic.`,
      seconds: secondsPerSlide + (remainder > 2 ? 1 : 0),
      claims: [makeClaim(form.futurePlans.trim() || 'Future plans have not been supplied.', form.futurePlans.trim() ? 'team_provided' : 'needs_verification', form.futurePlans.trim() ? 'Team context' : undefined)],
    },
  ]

  const warnings = [...analysis.warnings]
  if (!teamProblem) warnings.push('Problem statement came from the event brief rather than a team-confirmed description.')
  if (!results) warnings.push('No measured results were provided. Do not add numerical outcome claims without evidence.')
  if (analysis.unknowns.length) warnings.push(`${analysis.unknowns.length} repository detail(s) still need confirmation.`)

  return {
    projectName,
    tagline: solution || brief.slice(0, 120) || 'A project built for a hackathon challenge',
    durationMinutes: form.pitchDurationMinutes,
    slides,
    warnings: [...new Set(warnings)],
    generationMode: 'fallback',
    generationSource: 'local',
  }
}

export function getEvidenceLabel(status: EvidenceStatus): string {
  return EVIDENCE_LABELS[status]
}

export function createEmptyForm(): ProjectFormState {
  return { ...DEFAULT_PROJECT_FORM, requiredDeliverables: [...DEFAULT_PROJECT_FORM.requiredDeliverables] }
}
