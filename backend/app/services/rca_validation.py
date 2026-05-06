"""RCA completeness rules used by state machine and API."""
from dataclasses import dataclass
from datetime import datetime


class RcaIncompleteError(ValueError):
    pass


@dataclass
class RcaFields:
    incident_start: datetime | None
    incident_end: datetime | None
    root_cause_category: str | None
    fix_applied: str | None
    prevention_steps: str | None


def _non_empty(s: str | None) -> bool:
    return bool(s and str(s).strip())


def validate_rca_complete(
    incident_start: datetime | None,
    incident_end: datetime | None,
    root_cause_category: str | None,
    fix_applied: str | None,
    prevention_steps: str | None,
) -> None:
    if incident_start is None or incident_end is None:
        raise RcaIncompleteError("incident_start and incident_end are required")
    if incident_end < incident_start:
        raise RcaIncompleteError("incident_end must be after incident_start")
    if not _non_empty(root_cause_category):
        raise RcaIncompleteError("root_cause_category is required")
    if not _non_empty(fix_applied):
        raise RcaIncompleteError("fix_applied is required")
    if not _non_empty(prevention_steps):
        raise RcaIncompleteError("prevention_steps is required")


def assert_rca_complete_for_close(rca: object | None) -> None:
    if rca is None:
        raise RcaIncompleteError("RCA must exist before CLOSED")
    incident_start = getattr(rca, "incident_start", None)
    incident_end = getattr(rca, "incident_end", None)
    root_cause_category = getattr(rca, "root_cause_category", None)
    fix_applied = getattr(rca, "fix_applied", None)
    prevention_steps = getattr(rca, "prevention_steps", None)
    validate_rca_complete(
        incident_start,
        incident_end,
        root_cause_category,
        fix_applied,
        prevention_steps,
    )


def compute_mttr_seconds(first_signal_at: datetime, rca_end: datetime) -> float:
    return max(0.0, (rca_end - first_signal_at).total_seconds())
