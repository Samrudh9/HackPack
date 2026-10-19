import { Check, FileCheck2, FileText, Github, Presentation } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { WorkflowStep } from '../types/hackpack'

const steps: Array<{ id: WorkflowStep; label: string; detail: string; Icon: LucideIcon }> = [
  { id: 'project', label: 'Project', detail: 'Define the pitch', Icon: Github },
  { id: 'analysis', label: 'Analysis', detail: 'Inspect evidence', Icon: FileText },
  { id: 'review', label: 'Review', detail: 'Shape the story', Icon: Presentation },
  { id: 'export', label: 'Export', detail: 'Download the pack', Icon: FileCheck2 },
]

export function StepNavigation({
  activeStep,
  unlocked,
  complete,
  onSelect,
}: {
  activeStep: WorkflowStep
  unlocked: WorkflowStep[]
  complete: WorkflowStep[]
  onSelect: (step: WorkflowStep) => void
}) {
  return (
    <nav className="step-navigation" aria-label="Pitch workflow">
      {steps.map(({ id, label, detail, Icon }, index) => {
        const active = activeStep === id
        const isComplete = complete.includes(id)
        const canSelect = unlocked.includes(id)
        return (
          <button
            type="button"
            key={id}
            className={`step-item ${active ? 'active' : ''} ${isComplete ? 'complete' : ''} ${!canSelect ? 'locked' : ''}`}
            onClick={() => canSelect && onSelect(id)}
            disabled={!canSelect}
            aria-current={active ? 'step' : undefined}
            aria-label={`${label}: ${detail}${!canSelect ? ', locked' : ''}`}
          >
            <span className="step-symbol">{isComplete && !active ? <Check size={16} /> : <Icon size={16} />}</span>
            <span className="step-copy"><strong>{label}</strong><small>{detail}</small></span>
            {index < steps.length - 1 && <span className="step-connector" aria-hidden="true" />}
          </button>
        )
      })}
    </nav>
  )
}
