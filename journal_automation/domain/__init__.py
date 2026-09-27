from journal_automation.domain.absence import (
    AbsenceConfirmation,
    ResolvedAbsence,
    resolve_absence_confirmation,
    resolve_comment,
)
from journal_automation.domain.photo import (
    PhotoCandidate,
    PhotoValidationState,
    compute_file_hash,
    validate_photo_candidate,
)
from journal_automation.domain.session import TrainingSession, build_session_id
from journal_automation.domain.states import AutomationState, TrainingDomainState

__all__ = [
    "AbsenceConfirmation",
    "ResolvedAbsence",
    "resolve_absence_confirmation",
    "resolve_comment",
    "PhotoCandidate",
    "PhotoValidationState",
    "compute_file_hash",
    "validate_photo_candidate",
    "TrainingSession",
    "build_session_id",
    "AutomationState",
    "TrainingDomainState",
]
