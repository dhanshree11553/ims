"""
State pattern: incident lifecycle transitions with explicit guards.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.models.enums import WorkItemStatus
from app.services.rca_validation import assert_rca_complete_for_close


TransitionGuard = Callable[[WorkItemStatus, WorkItemStatus, object | None], None]


def _guard_closed_requires_rca(_from: WorkItemStatus, to: WorkItemStatus, rca: object | None) -> None:
    if to == WorkItemStatus.CLOSED:
        assert_rca_complete_for_close(rca)


@dataclass
class WorkItemStateMachine:
    """Valid transitions: OPEN->INVESTIGATING->RESOLVED->CLOSED (with branch to INVESTIGATING from RESOLVED not allowed — linear closure)."""

    _allowed: dict[WorkItemStatus, frozenset[WorkItemStatus]] | None = None
    _guards: list[TransitionGuard] | None = None

    def __post_init__(self):
        if self._allowed is None:
            self._allowed = {
                WorkItemStatus.OPEN: frozenset({WorkItemStatus.INVESTIGATING}),
                WorkItemStatus.INVESTIGATING: frozenset({WorkItemStatus.RESOLVED, WorkItemStatus.OPEN}),
                WorkItemStatus.RESOLVED: frozenset({WorkItemStatus.CLOSED, WorkItemStatus.INVESTIGATING}),
                WorkItemStatus.CLOSED: frozenset(),
            }
        if self._guards is None:
            self._guards = [_guard_closed_requires_rca]

    def transition(self, current: WorkItemStatus, target: WorkItemStatus, rca: object | None = None) -> WorkItemStatus:
        if target not in self._allowed[current]:
            raise ValueError(f"Invalid transition {current.value} -> {target.value}")
        for guard in self._guards:
            guard(current, target, rca)
        return target
