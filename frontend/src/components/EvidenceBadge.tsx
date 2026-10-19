import { AlertTriangle, CheckCircle2, CircleHelp, FileCheck2, MessageSquareText, Sparkles } from 'lucide-react'
import { getEvidenceLabel } from '../lib/workflow'
import type { EvidenceStatus } from '../types/hackpack'

const icons = {
  repo_evidence: CheckCircle2,
  test_evidence_found: FileCheck2,
  team_provided: MessageSquareText,
  inferred: Sparkles,
  needs_verification: AlertTriangle,
  unknown: CircleHelp,
}

export function EvidenceBadge({ status }: { status: EvidenceStatus }) {
  const Icon = icons[status]
  return (
    <span className={`evidence-badge evidence-${status}`}>
      <Icon size={13} strokeWidth={2} aria-hidden="true" />
      <span>{getEvidenceLabel(status)}</span>
    </span>
  )
}
