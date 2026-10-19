import { describe, expect, it } from 'vitest'
import { canAdvanceStep, classifyEvidence, createEmptyForm, getProjectValidation, normalizePublicGithubUrl } from '../src/lib/workflow'
import type { PitchDraft, RepositoryAnalysis } from '../src/types/hackpack'

const validForm = () => ({
  ...createEmptyForm(),
  repoUrl: 'https://github.com/octocat/hello-world',
  eventBrief: 'Build a useful tool for the community.',
})

const analysis: RepositoryAnalysis = {
  repositoryUrl: 'https://github.com/octocat/hello-world',
  repositoryName: 'hello-world',
  description: 'A demo repository',
  primaryLanguage: 'TypeScript',
  languages: [{ name: 'TypeScript' }],
  techStack: [],
  keyModules: [],
  files: ['README.md'],
  signals: [],
  demoUrls: [],
  warnings: [],
  unknowns: [],
  raw: {},
}

const pitch: PitchDraft = {
  projectName: 'hello-world',
  tagline: 'A demo project',
  durationMinutes: 3,
  slides: [{ id: 'one', title: 'Problem', subtitle: '', bullets: [], speakerNotes: '', seconds: 30, claims: [] }],
  warnings: [],
}

describe('public repository validation', () => {
  it('accepts normal GitHub owner/repository URLs and removes .git', () => {
    expect(normalizePublicGithubUrl('https://github.com/octocat/hello-world.git')).toBe('https://github.com/octocat/hello-world')
  })

  it('rejects other hosts, non-HTTPS URLs, and non-repository paths', () => {
    expect(normalizePublicGithubUrl('https://gitlab.com/octocat/hello-world')).toBeNull()
    expect(normalizePublicGithubUrl('http://github.com/octocat/hello-world')).toBeNull()
    expect(normalizePublicGithubUrl('https://github.com/octocat')).toBeNull()
  })

  it('requires both a public GitHub URL and hackathon brief', () => {
    expect(Object.keys(getProjectValidation(createEmptyForm()))).toEqual(['repoUrl', 'eventBrief'])
    expect(getProjectValidation(validForm())).toEqual({})
  })
})

describe('workflow gating', () => {
  it('allows analysis only after required project inputs exist', () => {
    expect(canAdvanceStep('analysis', createEmptyForm(), null, null)).toBe(false)
    expect(canAdvanceStep('analysis', validForm(), null, null)).toBe(true)
  })

  it('locks review until analysis exists, and export until a pitch exists', () => {
    const form = validForm()
    expect(canAdvanceStep('review', form, null, null)).toBe(false)
    expect(canAdvanceStep('review', form, analysis, null)).toBe(false)
    expect(canAdvanceStep('review', form, analysis, pitch)).toBe(true)
    expect(canAdvanceStep('export', form, analysis, null)).toBe(false)
    expect(canAdvanceStep('export', form, analysis, pitch)).toBe(true)
  })
})

describe('evidence classification', () => {
  it('prioritizes explicit uncertainty over source hints', () => {
    expect(classifyEvidence({ hasRepositorySource: true, explicitlyUnverified: true })).toBe('needs_verification')
  })

  it('does not promote a team claim to repository evidence', () => {
    expect(classifyEvidence({ teamProvided: true })).toBe('team_provided')
  })

  it('keeps unknown claims unknown in the absence of evidence', () => {
    expect(classifyEvidence({})).toBe('unknown')
  })

  it('records test evidence separately from source-code evidence', () => {
    expect(classifyEvidence({ hasTestSource: true, hasRepositorySource: true })).toBe('test_evidence_found')
  })
})
