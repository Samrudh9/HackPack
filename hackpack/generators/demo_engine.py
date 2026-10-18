"""Generate a conservative demo checklist from repository evidence and the pitch.

Only features supported by inspected repository evidence (or explicitly
confirmed by the team) appear as demo steps. A file's existence is never
presented as proof that a feature runs; every step that depends on runtime
behaviour carries a rehearsal requirement.
"""
from hackpack.models import DemoPlan, DemoStep, PitchDeck, RepoEvidence


def build_demo_plan(
    evidence: RepoEvidence | None,
    deck: PitchDeck,
    demo_duration_seconds: int = 120,
) -> DemoPlan:
    evidence = evidence or RepoEvidence(repo_url="(not provided)", repo_name=deck.project_name)
    steps: list[DemoStep] = []
    steps.append(DemoStep(
        order=1,
        action="Open the project and show its main user-facing entry point.",
        expected_result="The audience can see where a user interacts with the project.",
        talking_point="Explain the user journey before showing implementation details.",
        estimated_seconds=min(25, max(10, demo_duration_seconds // 5)),
        requires="Confirm the application starts and the demo environment is prepared.",
        evidence_basis="Always included; verify the entry point manually before judging.",
    ))
    if evidence.demo_urls:
        steps.append(DemoStep(
            order=len(steps) + 1,
            action=f"Open the available demo link: {evidence.demo_urls[0]}",
            expected_result="Show the deployed or hosted project if the link is still live.",
            talking_point="Narrate the user-visible behavior. Do not assume the link is working until tested.",
            estimated_seconds=25,
            requires="Check the link and prepare a backup screenshot or recording.",
            evidence_basis=f"URL found in repository content ({evidence.demo_urls[0]}); liveness not verified by HackPack.",
        ))
    if evidence.key_modules:
        module = evidence.key_modules[0]
        path = module.get("path", "a key source file")
        purpose = module.get("purpose", "implementation detail")
        steps.append(DemoStep(
            order=len(steps) + 1,
            action=f"Show the relevant implementation in `{path}`.",
            expected_result=f"A judge can see the code associated with: {purpose}.",
            talking_point="Connect this implementation to the visible feature. A source file alone does not prove end-to-end behavior.",
            estimated_seconds=25,
            requires="Use a prepared code excerpt; avoid browsing the entire repository live.",
            evidence_basis=f"Static inspection of `{path}`; runtime behaviour not verified.",
        ))
    if evidence.test_files:
        steps.append(DemoStep(
            order=len(steps) + 1,
            action=f"Run one automated test suite, for example `{evidence.test_files[0]}`.",
            expected_result="Judges see automated verification the team can reproduce.",
            talking_point="Explain what the test covers and, just as importantly, what it does not cover.",
            estimated_seconds=25,
            requires="Run the tests before the event and confirm they pass in the demo environment.",
            evidence_basis=f"Test file `{evidence.test_files[0]}` was inspected; passing status not verified by HackPack.",
        ))
    remaining = demo_duration_seconds - sum(s.estimated_seconds for s in steps) - 20
    steps.append(DemoStep(
        order=len(steps) + 1,
        action="Demonstrate one core user flow from input to result.",
        expected_result="Show the most important outcome the project currently supports.",
        talking_point="Choose a flow that works reliably today. Clearly distinguish implemented functionality from planned work.",
        estimated_seconds=max(15, remaining),
        requires="Prepare test data and rehearse the flow; the generator cannot confirm that runtime behavior works.",
        evidence_basis="Team-rehearsed flow; not verified from repository evidence alone.",
    ))
    steps.append(DemoStep(
        order=len(steps) + 1,
        action="Close with the current limitation and the next improvement.",
        expected_result="The judges understand the current scope and realistic next step.",
        talking_point="Be direct about what has and has not been validated.",
        estimated_seconds=15,
        evidence_basis="Presentation structure, not a repository claim.",
    ))
    total = sum(step.estimated_seconds for step in steps)
    return DemoPlan(
        steps=steps,
        prerequisites=[
            "Run and test the demo before judging begins.",
            "Have a backup screenshot or short recording ready.",
            "Confirm all claims in the pitch can be explained by the team.",
        ]
        + ([f"Repository: {evidence.repo_url}"] if evidence.repo_url != "(not provided)" else []),
        total_duration_seconds=total,
        backup_plan=(
            "If the live demo fails, show a prepared screenshot or recording and explain the "
            "intended flow without claiming a successful live run."
        ),
    )


def generate_demo_checklist(plan: DemoPlan, project_name: str = "Project") -> str:
    lines = [
        f"# {project_name} — Demo Checklist",
        "",
        f"**Estimated duration:** {plan.total_duration_seconds // 60}m {plan.total_duration_seconds % 60:02d}s",
        "",
        "## Before presenting",
    ]
    lines.extend(f"- [ ] {item}" for item in plan.prerequisites)
    lines.extend(["", "## Demo flow", ""])
    for step in plan.steps:
        lines.extend([
            f"### {step.order}. {step.action}",
            f"- **Show:** {step.expected_result}",
            f"- **Say:** {step.talking_point}",
            f"- **Time:** {step.estimated_seconds} seconds",
        ])
        if step.requires:
            lines.append(f"- **Check first:** {step.requires}")
        if step.evidence_basis:
            lines.append(f"- **Evidence basis:** {step.evidence_basis}")
        lines.append("")
    lines.extend(["## Backup plan", "", plan.backup_plan, ""])
    return "\n".join(lines)
