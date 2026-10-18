"""HackPack — open-source, domain-independent hackathon deliverables generator.

Public API surface for library use::

    from hackpack import (
        analyze_repository, build_pitch, verify_claims,
        generate_pptx, generate_script, build_demo_plan, build_deliverable_zip,
    )
"""
from hackpack.models import (  # noqa: F401
    Claim,
    ClaimCategory,
    DemoPlan,
    DemoStep,
    EvidenceType,
    HackathonBrief,
    PitchDeck,
    RepoEvidence,
    SlideContent,
    TeamContext,
)

__version__ = "0.1.0"
