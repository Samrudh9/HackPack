import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import {
  AlertCircle,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Clock3,
  Code2,
  FileArchive,
  FileText,
  Github,
  Info,
  Link2,
  LoaderCircle,
  Plus,
  Presentation,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  Users,
} from 'lucide-react'
import { EvidenceBadge } from '../components/EvidenceBadge'
import { StepNavigation } from '../components/StepNavigation'
import { analyzeRepository, checkBackendHealth, generateDeliverables, generatePitch, getApiConfiguration } from '../lib/api'
import { buildLocalPitchDraft, canAdvanceStep, createEmptyForm, getProjectValidation, normalizePublicGithubUrl } from '../lib/workflow'
import type { ApiHealth, DownloadLink, PitchDraft, PitchSlide, ProjectFormState, RepositoryAnalysis, WorkflowStep } from '../types/hackpack'

const openSourceUrl = (import.meta.env.VITE_OPEN_SOURCE_REPO_URL as string | undefined)?.trim() || ''

export const Route = createFileRoute('/')({
  head: () => ({
    meta: [
      { title: 'HackPack — Evidence-aware hackathon workspace' },
      { name: 'description', content: 'Turn a public GitHub repository and hackathon brief into evidence-aware pitch materials.' },
      { property: 'og:title', content: 'HackPack — Evidence-aware hackathon workspace' },
      { property: 'og:description', content: 'Review project evidence, shape your pitch, and export hackathon deliverables.' },
      { property: 'og:type', content: 'website' },
      { name: 'twitter:card', content: 'summary' },
      { name: 'twitter:title', content: 'HackPack — Evidence-aware hackathon workspace' },
      { name: 'twitter:description', content: 'Turn your hackathon build into a clear, evidence-aware pitch.' },
    ],
  }),
  component: HackPackWorkspace,
})

function HackPackWorkspace() {
  const [step, setStep] = useState<WorkflowStep>('project')
  const [form, setForm] = useState<ProjectFormState>(() => createEmptyForm())
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [analysis, setAnalysis] = useState<RepositoryAnalysis | null>(null)
  const [pitch, setPitch] = useState<PitchDraft | null>(null)
  const [health, setHealth] = useState<ApiHealth>({ connected: false, message: 'Checking backend…' })
  const [checkingHealth, setCheckingHealth] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisError, setAnalysisError] = useState('')
  const [generating, setGenerating] = useState(false)
  const [generationError, setGenerationError] = useState('')
  const [generationWarnings, setGenerationWarnings] = useState<string[]>([])
  const [downloads, setDownloads] = useState<DownloadLink[]>([])
  const analysisRequestId = useRef(0)

  const clearDownloads = () => {
    downloads.forEach((download) => {
      if (download.url.startsWith('blob:')) URL.revokeObjectURL(download.url)
    })
    setDownloads([])
  }

  const validation = useMemo(() => getProjectValidation(form), [form])
  const validProject = Object.keys(validation).length === 0
  const completedSteps = useMemo<WorkflowStep[]>(() => {
    const done: WorkflowStep[] = []
    if (validProject) done.push('project')
    if (analysis) done.push('analysis')
    if (pitch) done.push('review')
    if (downloads.length) done.push('export')
    return done
  }, [validProject, analysis, pitch, downloads.length])
  const unlockedSteps = useMemo<WorkflowStep[]>(() => {
    const unlocked: WorkflowStep[] = ['project']
    if (canAdvanceStep('analysis', form, analysis, pitch)) unlocked.push('analysis')
    if (canAdvanceStep('review', form, analysis, pitch)) unlocked.push('review')
    if (canAdvanceStep('export', form, analysis, pitch)) unlocked.push('export')
    return unlocked
  }, [form, analysis, pitch])

  const refreshHealth = useCallback(async () => {
    setCheckingHealth(true)
    const result = await checkBackendHealth()
    setHealth(result)
    setCheckingHealth(false)
  }, [])

  useEffect(() => {
    void refreshHealth()
  }, [refreshHealth])

  const updateField = <K extends keyof ProjectFormState>(key: K, value: ProjectFormState[K]) => {
    const nextForm = { ...form, [key]: value }
    setForm(nextForm)
    setFieldErrors((current) => ({ ...current, [key]: '' }))
    // A backend-generated draft is only rebuilt by re-running analysis; form
    // edits here would silently discard the verified deck and slide edits.
    const keepBackendDraft = pitch?.generationSource === 'backend'
    if (key === 'repoUrl') {
      const nextRepository = typeof value === 'string' ? normalizePublicGithubUrl(value) : null
      const analyzedRepository = analysis ? normalizePublicGithubUrl(analysis.repositoryUrl) : null
      if (nextRepository !== analyzedRepository) {
        setAnalysis(null)
        setPitch(null)
      } else if (analysis && !keepBackendDraft) {
        setPitch(buildLocalPitchDraft(nextForm, analysis))
      }
    } else if (analysis && !keepBackendDraft) {
      setPitch(buildLocalPitchDraft(nextForm, analysis))
    }
    clearDownloads()
  }

  const toggleDeliverable = (label: string) => {
    const selected = form.requiredDeliverables.includes(label)
    updateField('requiredDeliverables', selected
      ? form.requiredDeliverables.filter((item) => item !== label)
      : [...form.requiredDeliverables, label])
  }

  const startNewPitch = () => {
    analysisRequestId.current += 1
    clearDownloads()
    setAnalyzing(false)
    setForm(createEmptyForm())
    setStep('project')
    setFieldErrors({})
    setAnalysis(null)
    setPitch(null)
    setAnalysisError('')
    setGenerationError('')
    setGenerationWarnings([])
  }

  const leaveAnalysis = () => {
    analysisRequestId.current += 1
    setAnalyzing(false)
    setStep('project')
  }

  const runAnalysis = async () => {
    const errors = getProjectValidation(form)
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0) {
      setStep('project')
      return
    }
    const normalizedUrl = normalizePublicGithubUrl(form.repoUrl)
    if (!normalizedUrl) return
    updateField('repoUrl', normalizedUrl)
    const requestId = ++analysisRequestId.current
    setStep('analysis')
    setAnalyzing(true)
    setAnalysisError('')
    setAnalysis(null)
    setPitch(null)
    clearDownloads()
    setGenerationError('')
    try {
      const result = await analyzeRepository(normalizedUrl)
      if (requestId !== analysisRequestId.current) return
      setAnalysis(result)
      const context = { ...form, repoUrl: normalizedUrl }
      let draft: PitchDraft
      try {
        // Backend pitch engine: AI draft or deterministic fallback, claims verified server-side.
        draft = await generatePitch({ evidence: result, form: context })
      } catch (pitchError) {
        // Honest degradation: keep working, but label where the draft came from.
        draft = buildLocalPitchDraft(context, result)
        const message = pitchError instanceof Error ? pitchError.message : 'Pitch generation failed.'
        draft.warnings = [
          `Backend pitch generation unavailable — ${message} Showing the in-browser draft built from repository evidence instead.`,
          ...draft.warnings,
        ]
      }
      if (requestId !== analysisRequestId.current) return
      setPitch(draft)
    } catch (error) {
      if (requestId === analysisRequestId.current) setAnalysisError(error instanceof Error ? error.message : 'Repository analysis failed. Please try again.')
    } finally {
      if (requestId === analysisRequestId.current) setAnalyzing(false)
    }
  }

  const navigateTo = (target: WorkflowStep) => {
    if (!canAdvanceStep(target, form, analysis, pitch)) return
    setStep(target)
  }

  const updateSlide = (slideId: string, updates: Partial<PitchSlide>) => {
    setPitch((current) => current ? {
      ...current,
      slides: current.slides.map((slide) => slide.id === slideId ? { ...slide, ...updates } : slide),
    } : current)
    clearDownloads()
    setGenerationError('')
  }

  const runGeneration = async () => {
    if (!analysis || !pitch) {
      setGenerationError('Analyze a repository and review the pitch before generating deliverables.')
      return
    }
    setGenerating(true)
    setGenerationError('')
    setGenerationWarnings([])
    clearDownloads()
    try {
      const result = await generateDeliverables({ evidence: analysis, pitch, form })
      setDownloads(result.downloads)
      setGenerationWarnings(result.warnings)
      if (!result.downloads.length) setGenerationError('The backend completed without returning downloadable files.')
    } catch (error) {
      setGenerationError(error instanceof Error ? error.message : 'Generation failed. Try again after checking the backend.')
    } finally {
      setGenerating(false)
    }
  }

  return (
    <main className="app-frame">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true"><TerminalSquare size={19} /></div>
          <div className="brand-name">hackpack<span className="brand-dot">.</span><span className="brand-version">BETA</span></div>
        </div>
        <div className="topbar-actions">
          {openSourceUrl ? <a className="subtle-link source-link" href={openSourceUrl} target="_blank" rel="noreferrer" aria-label="Open HackPack source repository">
            <Github size={16} /> <span>Open source</span>
          </a> : <span className="subtle-link source-link source-link-disabled" title="Set VITE_OPEN_SOURCE_REPO_URL to your public repository URL" aria-disabled="true"><Github size={16} /> <span>Open source URL not set</span></span>}
          <div className={`connection-pill ${health.connected ? 'is-connected' : 'is-disconnected'}`} title={health.message}>
            <span className="connection-dot" />
            <span>{checkingHealth ? 'Checking API' : health.connected ? 'API connected' : 'API disconnected'}</span>
            <button type="button" className="icon-button tiny" onClick={() => void refreshHealth()} disabled={checkingHealth} aria-label="Retry backend connection">
              <RefreshCw size={12} className={checkingHealth ? 'spin' : ''} />
            </button>
          </div>
          <button type="button" className="button button-secondary button-small" onClick={startNewPitch}><Plus size={15} /> New pitch</button>
        </div>
      </header>

      <section className="workspace-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> HACKATHON WORKSPACE</div>
          <h1>Make the build <span>easy to believe.</span></h1>
          <p>Turn your repository and event brief into a clear pitch, grounded in what your team actually built.</p>
        </div>
        <div className="heading-note"><ShieldCheck size={17} /><span>Evidence first. Claims reviewed.</span></div>
      </section>

      <StepNavigation activeStep={step} unlocked={unlockedSteps} complete={completedSteps} onSelect={navigateTo} />

      <section className="workspace-panel" aria-live="polite">
        {step === 'project' && (
          <ProjectStep
            form={form}
            errors={fieldErrors}
            validation={validation}
            onUpdate={updateField}
            onToggleDeliverable={toggleDeliverable}
            onAnalyze={() => void runAnalysis()}
          />
        )}
        {step === 'analysis' && (
          <AnalysisStep
            analysis={analysis}
            form={form}
            analyzing={analyzing}
            error={analysisError}
            onRetry={() => void runAnalysis()}
            onBack={leaveAnalysis}
            onContinue={() => navigateTo('review')}
          />
        )}
        {step === 'review' && (
          <ReviewStep
            pitch={pitch}
            analysis={analysis}
            form={form}
            onUpdateSlide={updateSlide}
            onBack={() => setStep('analysis')}
            onContinue={() => navigateTo('export')}
          />
        )}
        {step === 'export' && (
          <ExportStep
            pitch={pitch}
            generating={generating}
            error={generationError}
            warnings={generationWarnings}
            downloads={downloads}
            onBack={() => setStep('review')}
            onGenerate={() => void runGeneration()}
            onNewPitch={startNewPitch}
          />
        )}
      </section>

      <footer className="workspace-footer">
        <span><span className="footer-status" /> Your work stays in this browser until you send it to your configured API.</span>
        <span>HackPack <span className="footer-separator">/</span> Open source by design</span>
      </footer>
    </main>
  )
}

function SectionHeader({ eyebrow, title, description, aside }: { eyebrow: string; title: string; description: string; aside?: ReactNode }) {
  return (
    <div className="section-header">
      <div>
        <div className="section-eyebrow">{eyebrow}</div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {aside && <div className="section-aside">{aside}</div>}
    </div>
  )
}

function FormField({ label, htmlFor, required, hint, error, children }: { label: string; htmlFor: string; required?: boolean; hint?: string; error?: string; children: ReactNode }) {
  return (
    <div className={`form-field ${error ? 'has-error' : ''}`}>
      <label htmlFor={htmlFor}>{label}{required && <span className="required-mark"> *</span>}</label>
      {children}
      {error ? <span className="field-error"><AlertCircle size={13} /> {error}</span> : hint ? <span className="field-hint">{hint}</span> : null}
    </div>
  )
}

function ProjectStep({
  form, errors, validation, onUpdate, onToggleDeliverable, onAnalyze,
}: {
  form: ProjectFormState
  errors: Record<string, string>
  validation: Record<string, string>
  onUpdate: <K extends keyof ProjectFormState>(key: K, value: ProjectFormState[K]) => void
  onToggleDeliverable: (label: string) => void
  onAnalyze: () => void
}) {
  const [contextOpen, setContextOpen] = useState(true)
  const deliverableOptions = ['Pitch deck', 'Pitch script', 'Demo checklist', 'Technical report']
  return (
    <>
      <SectionHeader eyebrow="STEP 01 / PROJECT" title="Start with the project." description="A few useful details help HackPack shape a pitch for this specific event." aside={<span className="required-legend"><span className="required-mark">*</span> Required</span>} />
      <div className="form-layout">
        <div className="form-main-column">
          <div className="form-section-title"><span className="section-icon"><Github size={17} /></span><div><h3>Repository</h3><p>We'll inspect source and configuration files without running the code.</p></div></div>
          <FormField label="Public GitHub repository URL" htmlFor="repo-url" required hint="Public repositories only in this version." error={errors.repoUrl}>
            <div className="input-with-icon"><Github size={17} /><input id="repo-url" type="url" autoComplete="url" placeholder="https://github.com/owner/project" value={form.repoUrl} onChange={(event) => onUpdate('repoUrl', event.currentTarget.value)} aria-invalid={Boolean(errors.repoUrl)} /></div>
          </FormField>
          <div className="form-grid two-columns">
            <FormField label="Hackathon / event name" htmlFor="event-name" hint="Optional">
              <input id="event-name" type="text" placeholder="e.g. Open Innovation Challenge" value={form.eventName} onChange={(event) => onUpdate('eventName', event.currentTarget.value)} />
            </FormField>
            <FormField label="Pitch duration" htmlFor="pitch-duration" required hint="We'll split the time across six slides.">
              <div className="select-with-icon"><Clock3 size={16} /><select id="pitch-duration" value={form.pitchDurationMinutes} onChange={(event) => onUpdate('pitchDurationMinutes', Number(event.currentTarget.value))}>{[1, 1.5, 3, 5, 10].map((duration) => <option key={duration} value={duration}>{duration < 2 ? `${duration * 60} seconds` : `${duration} minutes`}</option>)}</select><ChevronDown size={15} /></div>
            </FormField>
          </div>
          <FormField label="Hackathon brief or challenge" htmlFor="event-brief" required hint="Paste the problem statement or event theme. It can be from any domain." error={errors.eventBrief}>
            <textarea id="event-brief" rows={4} placeholder="What challenge is the event asking teams to solve? Include any important context…" value={form.eventBrief} onChange={(event) => onUpdate('eventBrief', event.currentTarget.value)} aria-invalid={Boolean(errors.eventBrief)} />
          </FormField>
          <FormField label="Judging criteria" htmlFor="judging-criteria" hint="Optional — one criterion per line">
            <textarea id="judging-criteria" rows={3} placeholder={'Innovation\nTechnical implementation\nImpact and feasibility'} value={form.judgingCriteria} onChange={(event) => onUpdate('judgingCriteria', event.currentTarget.value)} />
          </FormField>
          <FormField label="Event rules and submission instructions" htmlFor="event-rules" hint="Optional">
            <textarea id="event-rules" rows={2} placeholder="Required sections, restrictions, or submission notes…" value={form.additionalRules} onChange={(event) => onUpdate('additionalRules', event.currentTarget.value)} />
          </FormField>
          <div className="divider-row" />
          <button className="accordion-trigger" type="button" aria-expanded={contextOpen} onClick={() => setContextOpen((open) => !open)}>
            <span className="section-icon"><Users size={17} /></span><span className="accordion-copy"><strong>Team context</strong><small>Optional details that code alone cannot explain</small></span><ChevronDown size={17} className={contextOpen ? 'rotate-chevron' : ''} />
          </button>
          {contextOpen && <div className="context-fields">
            <FormField label="What problem are you solving?" htmlFor="problem-statement" hint="Your own words are best.">
              <textarea id="problem-statement" rows={3} placeholder="Describe the real-world problem…" value={form.problemStatement} onChange={(event) => onUpdate('problemStatement', event.currentTarget.value)} />
            </FormField>
            <FormField label="Who is this for?" htmlFor="target-users">
              <input id="target-users" type="text" placeholder="e.g. small farmers, independent developers" value={form.targetUsers} onChange={(event) => onUpdate('targetUsers', event.currentTarget.value)} />
            </FormField>
            <FormField label="What does your solution do?" htmlFor="solution-description">
              <textarea id="solution-description" rows={3} placeholder="Describe the main thing a person can do with it…" value={form.solutionDescription} onChange={(event) => onUpdate('solutionDescription', event.currentTarget.value)} />
            </FormField>
            <FormField label="Measured results" htmlFor="measured-results" hint="Team-provided until evidence is checked. Never add made-up metrics.">
              <textarea id="measured-results" rows={2} placeholder="What have you tested or measured so far? Leave blank if none." value={form.measuredResults} onChange={(event) => onUpdate('measuredResults', event.currentTarget.value)} />
            </FormField>
            <FormField label="Intended impact" htmlFor="expected-impact">
              <textarea id="expected-impact" rows={2} placeholder="What outcome do you hope to achieve?" value={form.expectedImpact} onChange={(event) => onUpdate('expectedImpact', event.currentTarget.value)} />
            </FormField>
            <FormField label="Future plans" htmlFor="future-plans">
              <input id="future-plans" type="text" placeholder="What would you build or validate next?" value={form.futurePlans} onChange={(event) => onUpdate('futurePlans', event.currentTarget.value)} />
            </FormField>
            <div className="form-grid two-columns">
              <FormField label="Team members" htmlFor="team-members" hint="Separate names with commas.">
                <input id="team-members" type="text" placeholder="Alex, Sam, Taylor" value={form.teamMembers} onChange={(event) => onUpdate('teamMembers', event.currentTarget.value)} />
              </FormField>
              <FormField label="Live demo URL" htmlFor="demo-url">
                <input id="demo-url" type="url" placeholder="https://your-demo.example" value={form.demoUrl} onChange={(event) => onUpdate('demoUrl', event.currentTarget.value)} />
              </FormField>
            </div>
          </div>}
        </div>
        <aside className="form-side-column">
          <div className="side-card deliverable-card">
            <div className="side-card-heading"><FileArchive size={17} /><strong>Deliverables</strong></div>
            <p>Choose what your team needs to submit.</p>
            <div className="checkbox-list">{deliverableOptions.map((label) => <label className="checkbox-row" key={label}><input type="checkbox" checked={form.requiredDeliverables.includes(label)} onChange={() => onToggleDeliverable(label)} /><span className="custom-check"><Check size={12} /></span><span>{label}</span></label>)}</div>
          </div>
          <div className="side-card trust-card">
            <div className="trust-icon"><ShieldCheck size={19} /></div>
            <strong>Evidence before polish</strong>
            <p>Repository facts, team statements, and assumptions stay distinct throughout the workflow.</p>
            <div className="mini-evidence-list"><EvidenceBadge status="repo_evidence" /><EvidenceBadge status="team_provided" /><EvidenceBadge status="needs_verification" /></div>
          </div>
          <div className="side-note"><Info size={15} /><span>Your entries stay in this browser until a request is sent to the configured backend.</span></div>
        </aside>
      </div>
      <div className="step-actions step-actions-end">
        <span className="action-hint">{Object.keys(validation).length ? 'Complete the required fields to continue.' : 'Ready to inspect your repository.'}</span>
        <button type="button" className="button button-primary" onClick={onAnalyze}><span>Analyze repository</span><ArrowRight size={16} /></button>
      </div>
    </>
  )
}

function AnalysisStep({ analysis, form, analyzing, error, onRetry, onBack, onContinue }: {
  analysis: RepositoryAnalysis | null; form: ProjectFormState; analyzing: boolean; error: string; onRetry: () => void; onBack: () => void; onContinue: () => void
}) {
  if (analyzing) return <div className="state-panel loading-state"><div className="loading-orbit"><LoaderCircle size={27} className="spin" /></div><div className="section-eyebrow">STEP 02 / ANALYSIS</div><h2>Reading the repository.</h2><p>Fetching project metadata and selected files. We don't execute repository code.</p><div className="loading-checklist"><div><span className="loading-dot active" /> Validating public repository URL</div><div><span className="loading-dot active delay-one" /> Inspecting files and dependencies</div><div><span className="loading-dot delay-two" /> Preparing evidence summary</div></div><button type="button" className="button button-secondary" onClick={onBack}>Back to project</button></div>
  if (error) return <div className="state-panel error-state"><div className="large-state-icon error-icon"><AlertCircle size={25} /></div><div className="section-eyebrow">STEP 02 / ANALYSIS</div><h2>We couldn't analyze this repository.</h2><p>{error}</p><div className="error-actions"><button type="button" className="button button-secondary" onClick={onBack}><ArrowLeft size={15} /> Edit inputs</button><button type="button" className="button button-primary" onClick={onRetry}><RefreshCw size={15} /> Try again</button></div></div>
  if (!analysis) return <div className="state-panel empty-state"><div className="large-state-icon"><Github size={25} /></div><div className="section-eyebrow">STEP 02 / ANALYSIS</div><h2>Your workspace is ready to inspect.</h2><p>Run repository analysis to load actual file and technology evidence. Nothing will be faked if the backend is unavailable.</p><div className="config-summary"><span>Repository</span><strong>{normalizePublicGithubUrl(form.repoUrl) || 'Not set'}</strong><span>Event brief</span><strong>{form.eventBrief || 'Not set'}</strong></div><div className="error-actions"><button type="button" className="button button-secondary" onClick={onBack}><ArrowLeft size={15} /> Back to project</button><button type="button" className="button button-primary" onClick={onRetry}>Analyze repository <ArrowRight size={15} /></button></div></div>

  return <>
    <SectionHeader eyebrow="STEP 02 / ANALYSIS" title="Here's what we found." description="Review the detected evidence before turning it into a story." aside={<span className="repo-count"><span className="live-indicator" /> Analysis complete</span>} />
    <div className="repo-summary-card"><div className="repo-avatar"><Github size={23} /></div><div className="repo-summary-copy"><div className="repo-name-row"><h3>{analysis.repositoryName}</h3><a href={analysis.repositoryUrl} target="_blank" rel="noreferrer" className="external-inline">View repo <Link2 size={13} /></a></div><p>{analysis.description || 'No repository description was returned. Confirm the project overview with your team.'}</p><div className="repo-meta"><span><Code2 size={14} /> {analysis.primaryLanguage || 'Language unknown'}</span><span><FileText size={14} /> {analysis.files.length} paths returned</span><span><ShieldCheck size={14} /> Read-only scan</span></div></div></div>
    <div className="analysis-grid">
      <div className="analysis-main">
        <div className="content-card"><div className="card-heading-row"><div><h3>Detected technology</h3><p>Based on repository metadata and dependency files.</p></div><span className="count-badge">{analysis.techStack.length}</span></div>{analysis.techStack.length ? <div className="tech-list">{analysis.techStack.map((item) => <div className="tech-row" key={item.id}><div className="tech-icon"><Code2 size={16} /></div><div className="tech-main"><strong>{item.title}</strong><span>{item.detail}</span>{item.source && <small>Source: {item.source}</small>}</div><EvidenceBadge status={item.status} /></div>)}</div> : <InlineEmpty message="No technology details were returned. Check the repository response mapping." />}</div>
        <div className="content-card"><div className="card-heading-row"><div><h3>Key modules</h3><p>Files or modules the analyzer identified as important.</p></div><span className="count-badge">{analysis.keyModules.length}</span></div>{analysis.keyModules.length ? <div className="module-list">{analysis.keyModules.map((item) => <div className="module-row" key={item.id}><FileText size={15} /><div><strong>{item.title}</strong><p>{item.detail}</p>{item.source && <small>{item.source}</small>}</div></div>)}</div> : <InlineEmpty message="No module summary was returned; the pitch can still use repository metadata and team context." />}</div>
        <div className="content-card"><div className="card-heading-row"><div><h3>Repository signals</h3><p>Presence is not a guarantee that a component works.</p></div></div><div className="signal-grid">{analysis.signals.map((signal) => <div className="signal-item" key={signal.label}><span className={`signal-dot ${signal.available ? 'available' : ''}`} /><div><strong>{signal.label}</strong><span>{signal.available ? 'Detected' : 'Not detected in returned evidence'}</span></div></div>)}</div>{analysis.demoUrls.length > 0 && <div className="demo-url-list"><strong>Demo links found</strong>{analysis.demoUrls.map((url) => <a key={url} href={url} target="_blank" rel="noreferrer"><Link2 size={13} /> {url}</a>)}</div>}</div>
      </div>
      <aside className="analysis-side">
        <div className="content-card side-content-card"><div className="card-heading-row"><div><h3>Evidence snapshot</h3><p>How information is sourced.</p></div></div><div className="evidence-explainer"><div><EvidenceBadge status="repo_evidence" /><p>Detected in the repository response; feature behavior may still need testing.</p></div><div><EvidenceBadge status="team_provided" /><p>Supplied by your team, not independently verified.</p></div><div><EvidenceBadge status="unknown" /><p>Information not available in the current response.</p></div></div></div>
        <div className="content-card side-content-card"><div className="card-heading-row"><div><h3>Needs confirmation</h3><p>Unknowns we won't fill in for you.</p></div><span className="count-badge warning-count">{analysis.unknowns.length}</span></div>{analysis.unknowns.length ? <ul className="warning-list">{analysis.unknowns.map((unknown) => <li key={unknown}><CircleHelp size={14} />{unknown}</li>)}</ul> : <div className="small-success"><CheckCircle2 size={15} /> No unknowns were reported by the adapter.</div>}</div>
        {analysis.warnings.length > 0 && <div className="warning-card"><div className="warning-title"><AlertCircle size={15} /> Analyzer warnings</div><ul>{analysis.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}
        <div className="content-card side-content-card"><div className="card-heading-row"><div><h3>Your context</h3><p>Shown separately from repository evidence.</p></div></div><div className="team-context-preview"><span>Hackathon brief</span><p>{form.eventBrief}</p>{form.problemStatement && <><span>Problem statement</span><p>{form.problemStatement}</p></>}{form.measuredResults && <><span>Team-reported results</span><p>{form.measuredResults}</p><EvidenceBadge status="team_provided" /></>}</div></div>
      </aside>
    </div>
    <div className="step-actions"><button type="button" className="button button-secondary" onClick={onBack}><ArrowLeft size={15} /> Back</button><span className="action-hint">Review the source signals before finalizing your story.</span><button type="button" className="button button-primary" onClick={onContinue}>Review pitch <ArrowRight size={16} /></button></div>
  </>
}

function InlineEmpty({ message }: { message: string }) {
  return <div className="inline-empty"><Info size={16} /><span>{message}</span></div>
}

function ReviewStep({ pitch, analysis, form, onUpdateSlide, onBack, onContinue }: {
  pitch: PitchDraft | null; analysis: RepositoryAnalysis | null; form: ProjectFormState; onUpdateSlide: (id: string, updates: Partial<PitchSlide>) => void; onBack: () => void; onContinue: () => void
}) {
  if (!pitch || !analysis) return <div className="state-panel empty-state"><div className="large-state-icon"><Presentation size={25} /></div><h2>No pitch draft yet.</h2><p>Run repository analysis first. The editor never pretends that generated content exists when it doesn't.</p><button type="button" className="button button-secondary" onClick={onBack}><ArrowLeft size={15} /> Back to analysis</button></div>
  const totalSeconds = pitch.slides.reduce((sum, slide) => sum + Math.max(0, slide.seconds), 0)
  return <>
    <SectionHeader eyebrow="STEP 03 / REVIEW" title="Shape the story." description="Edit each slide before export. The evidence status stays separate from the wording you change." aside={<span className="duration-chip"><Clock3 size={14} /> {formatSeconds(totalSeconds)} total</span>} />
    <div className="review-notice"><ShieldCheck size={17} /><div><strong>This is a draft built from returned repository evidence and your context.</strong><p>Review every claim. Editing a sentence does not independently verify it.</p></div></div>
    <div className="pitch-cover-card"><div className="pitch-cover-mark"><Sparkles size={21} /></div><div className="pitch-cover-copy"><span className="section-eyebrow">PITCH PREVIEW</span><h3>{pitch.projectName}</h3><p>{pitch.tagline}</p>
      {pitch.generationMode && (
        <span
          className="duration-chip"
          title={pitch.generationSource === 'backend'
            ? 'Produced by the backend pitch engine; every claim was checked against repository evidence.'
            : 'Produced in the browser because the backend pitch call was unavailable — review every slide.'}
        >
          {pitch.generationMode === 'ai' ? 'AI draft · backend verified' : 'Template fallback'}
        </span>
      )}
    </div><div className="cover-stat"><strong>{pitch.slides.length.toString().padStart(2, '0')}</strong><span>slides</span></div></div>
    {pitch.warnings.length > 0 && <div className="warning-card pitch-warnings"><div className="warning-title"><AlertCircle size={15} /> Review before presenting</div><ul>{pitch.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}
    <div className="slides-review-list">{pitch.slides.map((slide, index) => <article className="slide-editor-card" key={slide.id}><div className="slide-editor-top"><div className="slide-number">{String(index + 1).padStart(2, '0')}</div><div className="slide-editor-head"><span>SLIDE {String(index + 1).padStart(2, '0')}</span><strong>{formatSeconds(slide.seconds)} speaking time</strong></div><div className="slide-time-edit"><label htmlFor={`slide-time-${slide.id}`}>Seconds</label><input id={`slide-time-${slide.id}`} type="number" min={0} max={600} value={slide.seconds} onChange={(event) => onUpdateSlide(slide.id, { seconds: Math.max(0, Math.min(600, Number(event.currentTarget.value) || 0)) })} /></div></div>
      <div className="slide-editor-fields"><FormField label="Slide title" htmlFor={`slide-title-${slide.id}`}><input id={`slide-title-${slide.id}`} value={slide.title} onChange={(event) => onUpdateSlide(slide.id, { title: event.currentTarget.value })} /></FormField><FormField label="Subtitle" htmlFor={`slide-subtitle-${slide.id}`}><input id={`slide-subtitle-${slide.id}`} value={slide.subtitle} onChange={(event) => onUpdateSlide(slide.id, { subtitle: event.currentTarget.value })} /></FormField><FormField label="Bullet points" htmlFor={`slide-bullets-${slide.id}`} hint="One point per line."><textarea id={`slide-bullets-${slide.id}`} rows={Math.min(6, Math.max(3, slide.bullets.length))} value={slide.bullets.join('\n')} onChange={(event) => onUpdateSlide(slide.id, { bullets: event.currentTarget.value.split('\n').map((item) => item.trim()).filter(Boolean) })} /></FormField><FormField label="Speaker notes" htmlFor={`slide-notes-${slide.id}`}><textarea id={`slide-notes-${slide.id}`} rows={3} value={slide.speakerNotes} onChange={(event) => onUpdateSlide(slide.id, { speakerNotes: event.currentTarget.value })} /></FormField></div>
      <div className="claim-section"><div className="claim-section-title"><ShieldCheck size={14} /><span>Claims on this slide</span></div>{slide.claims.length ? <div className="claim-list">{slide.claims.map((claim) => <div className="claim-row" key={claim.id}><div className="claim-text"><p>{claim.statement}</p>{claim.source && <small>Source: {claim.source}{claim.lineStart ? ` · line ${claim.lineStart}${claim.lineEnd && claim.lineEnd !== claim.lineStart ? `–${claim.lineEnd}` : ''}` : ''}</small>}{claim.action && <small className="claim-action">{claim.action}</small>}</div><EvidenceBadge status={claim.status} /></div>)}</div> : <div className="inline-empty compact"><Info size={14} /><span>No explicit claims attached to this slide.</span></div>}</div>
    </article>)}</div>
    <div className="review-summary-row"><div><Clock3 size={16} /><span>Current script allocation: <strong>{formatSeconds(totalSeconds)}</strong></span></div><span className={totalSeconds === form.pitchDurationMinutes * 60 ? 'duration-ok' : 'duration-warning'}>{totalSeconds === form.pitchDurationMinutes * 60 ? 'Matches requested duration' : `Requested ${formatSeconds(form.pitchDurationMinutes * 60)} — adjust slide seconds as needed`}</span></div>
    <div className="step-actions"><button type="button" className="button button-secondary" onClick={onBack}><ArrowLeft size={15} /> Back to analysis</button><span className="action-hint">Review content and unverified claims before export.</span><button type="button" className="button button-primary" onClick={onContinue}>Continue to export <ArrowRight size={16} /></button></div>
  </>
}

function ExportStep({ pitch, generating, error, warnings, downloads, onBack, onGenerate, onNewPitch }: {
  pitch: PitchDraft | null; generating: boolean; error: string; warnings: string[]; downloads: DownloadLink[]; onBack: () => void; onGenerate: () => void; onNewPitch: () => void
}) {
  const apiConfig = getApiConfiguration()
  return <>
    <SectionHeader eyebrow="STEP 04 / EXPORT" title="Package it for the judges." description="Generate the deliverables through your configured backend. Files appear here only after a real response." />
    <div className="export-layout">
      <div className="export-main">
        <div className="export-summary-card"><div className="export-summary-icon"><FileArchive size={21} /></div><div><span className="section-eyebrow">READY TO GENERATE</span><h3>{pitch?.projectName || 'Your pitch pack'}</h3><p>{pitch ? `${pitch.slides.length} slides · ${formatSeconds(pitch.slides.reduce((sum, slide) => sum + slide.seconds, 0))} pitch allocation` : 'No pitch content available yet.'}</p></div><span className={`export-state ${downloads.length ? 'done' : ''}`}>{downloads.length ? 'Generated' : 'Not generated'}</span></div>
        {generating && <div className="generation-progress"><LoaderCircle size={19} className="spin" /><div><strong>Generating deliverables</strong><span>Waiting for the configured backend to prepare your files…</span></div></div>}
        {error && <div className="export-error"><AlertCircle size={17} /><div className="export-error-copy"><strong>Generation could not complete</strong><p>{error}</p></div><button type="button" className="button button-secondary button-small export-retry" onClick={onGenerate} disabled={generating}><RefreshCw size={13} /> Retry</button></div>}
        {!downloads.length && !generating && !error && <div className="export-empty"><div className="empty-illustration"><FileArchive size={27} /></div><h3>Your deliverables will appear here.</h3><p>HackPack will send the reviewed content to the configured API and show only the files returned by the backend.</p><button type="button" className="button button-primary" onClick={onGenerate} disabled={!pitch}><Sparkles size={16} /> Generate deliverables</button></div>}
        {downloads.length > 0 && <div className="download-results"><div className="download-success-heading"><CheckCircle2 size={19} /><div><h3>Deliverables are ready</h3><p>Download the actual files returned by your backend.</p></div></div>{downloads.map((file) => <div className="download-file-card" key={file.url}><div className="download-file-icon"><FileText size={18} /></div><div className="download-file-copy"><strong>{file.name}</strong><span>{file.description || 'Generated file'}</span></div><a className="button button-secondary button-small" href={file.url} download={file.name}><ArrowDownToLine size={14} /> Download</a></div>)}<button type="button" className="button button-primary full-width" onClick={onGenerate} disabled={generating}><RefreshCw size={15} /> Generate again</button></div>}
        {warnings.length > 0 && <div className="warning-card"><div className="warning-title"><AlertCircle size={15} /> Generation warnings</div><ul>{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}
        <div className="step-actions"><button type="button" className="button button-secondary" onClick={onBack}><ArrowLeft size={15} /> Back to review</button><button type="button" className="button button-quiet" onClick={onNewPitch}><Plus size={15} /> Start a new pitch</button></div>
      </div>
      <aside className="export-side">
        <div className="content-card"><div className="card-heading-row"><div><h3>What you'll get</h3><p>Depending on the backend response.</p></div></div><div className="deliverable-preview-list"><div><span className="deliverable-preview-icon ppt"><PresentationIcon /></span><div><strong>Pitch deck</strong><small>Editable PowerPoint</small></div></div><div><span className="deliverable-preview-icon script"><FileText size={16} /></span><div><strong>Pitch script</strong><small>Timed Markdown notes</small></div></div><div><span className="deliverable-preview-icon demo"><CheckCircle2 size={16} /></span><div><strong>Demo checklist</strong><small>Prerequisites and walkthrough</small></div></div></div><p className="export-note">PDF export is not assumed in this version. If the backend doesn't provide a file or download URL, HackPack will show an error rather than a fake download.</p></div>
        <div className={`api-config-card ${apiConfig.baseUrl ? '' : 'not-configured'}`}><div className="api-config-head"><span className={`connection-dot ${apiConfig.baseUrl ? 'connected' : ''}`} /><strong>{apiConfig.baseUrl ? 'API endpoint configured' : 'API endpoint not configured'}</strong></div><code>{apiConfig.baseUrl || 'VITE_API_BASE_URL is empty'}</code><p>Endpoint paths are configurable for compatibility with the existing FastAPI contract.</p></div>
      </aside>
    </div>
  </>
}

function formatSeconds(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds))
  const minutes = Math.floor(safe / 60)
  const remaining = safe % 60
  return minutes ? `${minutes}:${String(remaining).padStart(2, '0')}` : `${remaining}s`
}

function PresentationIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M12 17v4M8 21h8M8 9h8M8 13h4" /></svg>
}
