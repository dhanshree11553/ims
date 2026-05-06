import pytest
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.rca_validation import RcaIncompleteError, assert_rca_complete_for_close, validate_rca_complete
from app.workflow.state_machine import WorkItemStateMachine
from app.models.enums import WorkItemStatus


def test_validate_rca_complete_ok():
    t0 = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 5, 1, 11, 0, tzinfo=timezone.utc)
    validate_rca_complete(t0, t1, "Network", "Rolled back", "Add alerts")


def test_validate_rca_missing_fields():
    t0 = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 5, 1, 11, 0, tzinfo=timezone.utc)
    with pytest.raises(RcaIncompleteError):
        validate_rca_complete(t0, t1, "", "fix", "prev")
    with pytest.raises(RcaIncompleteError):
        validate_rca_complete(t0, t1, "cat", "", "prev")


def test_validate_rca_end_before_start():
    t0 = datetime(2026, 5, 1, 11, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
    with pytest.raises(RcaIncompleteError):
        validate_rca_complete(t0, t1, "x", "y", "z")


def test_assert_rca_complete_for_close_none():
    with pytest.raises(RcaIncompleteError):
        assert_rca_complete_for_close(None)


def test_assert_rca_complete_for_close_incomplete_object():
    rca = SimpleNamespace(
        incident_start=None,
        incident_end=datetime.now(timezone.utc),
        root_cause_category="x",
        fix_applied="y",
        prevention_steps="z",
    )
    with pytest.raises(RcaIncompleteError):
        assert_rca_complete_for_close(rca)


def test_state_machine_closed_requires_rca():
    sm = WorkItemStateMachine()
    t0 = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 5, 1, 11, 0, tzinfo=timezone.utc)
    rca = SimpleNamespace(
        incident_start=t0,
        incident_end=t1,
        root_cause_category="Network",
        fix_applied="done",
        prevention_steps="monitor",
    )
    assert sm.transition(WorkItemStatus.RESOLVED, WorkItemStatus.CLOSED, rca) == WorkItemStatus.CLOSED
    with pytest.raises(RcaIncompleteError):
        sm.transition(WorkItemStatus.RESOLVED, WorkItemStatus.CLOSED, None)
