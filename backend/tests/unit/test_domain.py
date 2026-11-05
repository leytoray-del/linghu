from datetime import date

import pytest

from erf.core.errors import InvalidTransition
from erf.domain.calendar import WorkingCalendar
from erf.domain.enums import Action, Priority, RequestStatus, RequestType, UrgencyReason
from erf.domain.urgency import evaluate_urgency
from erf.domain.validation import SubmissionFields, validate_submission
from erf.domain.workflow import TRANSITIONS, Actor, available_actions, find_transition

DEEPAVALI = date(2026, 11, 9)


class TestWorkingCalendar:
    cal = WorkingCalendar([DEEPAVALI])

    def test_counts_days_strictly_between_submission_and_start(self) -> None:
        # Thu 5 Nov -> Thu 12 Nov: Fri 6, (Mon 9 holiday), Tue 10, Wed 11
        assert self.cal.notice_working_days(date(2026, 11, 5), date(2026, 11, 12)) == 3

    def test_without_holiday(self) -> None:
        cal = WorkingCalendar()
        assert cal.notice_working_days(date(2026, 11, 5), date(2026, 11, 12)) == 4

    def test_start_on_or_before_submission_is_zero(self) -> None:
        assert self.cal.notice_working_days(date(2026, 11, 5), date(2026, 11, 5)) == 0
        assert self.cal.notice_working_days(date(2026, 11, 5), date(2026, 11, 1)) == 0

    def test_weekend_submission(self) -> None:
        # Sat 7 Nov -> Mon 16 Nov: Tue 10 .. Fri 13 (Mon 9 is a holiday)
        assert self.cal.notice_working_days(date(2026, 11, 7), date(2026, 11, 16)) == 4

    def test_add_working_days_skips_weekends_and_holidays(self) -> None:
        assert self.cal.add_working_days(date(2026, 11, 6), 1) == date(2026, 11, 10)
        assert self.cal.add_working_days(date(2026, 11, 5), 5) == date(2026, 11, 13)


class TestUrgency:
    def test_short_notice_forces_urgent(self) -> None:
        r = evaluate_urgency(Priority.NORMAL, 4, 5)
        assert r.is_urgent and r.reason == UrgencyReason.SHORT_NOTICE and r.is_short_notice

    def test_exact_minimum_is_normal(self) -> None:
        assert not evaluate_urgency(Priority.NORMAL, 5, 5).is_urgent

    def test_declared_urgent_with_enough_notice(self) -> None:
        r = evaluate_urgency(Priority.URGENT, 9, 5)
        assert r.is_urgent and r.reason == UrgencyReason.DECLARED and not r.is_short_notice


def _fields(**overrides: object) -> SubmissionFields:
    base: dict[str, object] = dict(
        request_type=RequestType.PROJECT, project_name="P", client_name="C", support_type_id=1, headcount=1,
        man_days=10.0, planned_start=date(2026, 12, 1), planned_end=date(2026, 12, 31), scope_description="S",
        task_schedule="T", is_urgent=False, urgent_justification=None,
    )  # fmt: skip
    base.update(overrides)
    return SubmissionFields(**base)  # type: ignore[arg-type]


class TestValidation:
    today = date(2026, 11, 5)

    def test_valid(self) -> None:
        assert validate_submission(_fields(), self.today) == {}

    def test_man_days_required_for_projects_only(self) -> None:
        assert "man_days" in validate_submission(_fields(man_days=None), self.today)
        assert (
            validate_submission(_fields(request_type=RequestType.PRESALES, man_days=None), self.today) == {}
        )

    def test_justification_required_when_urgent(self) -> None:
        assert "urgent_justification" in validate_submission(_fields(is_urgent=True), self.today)

    def test_dates(self) -> None:
        errors = validate_submission(_fields(planned_end=date(2026, 11, 30)), self.today)
        assert "planned_end" in errors
        assert "planned_start" in validate_submission(_fields(planned_start=date(2026, 11, 4)), self.today)


class TestWorkflow:
    def test_transitions_are_unique(self) -> None:
        keys = [(t.source, t.action) for t in TRANSITIONS]
        assert len(keys) == len(set(keys))

    def test_terminal_states_have_no_exits(self) -> None:
        for terminal in (
            RequestStatus.REJECTED,
            RequestStatus.WITHDRAWN,
            RequestStatus.CANCELLED,
            RequestStatus.CLOSED,
        ):
            assert not [t for t in TRANSITIONS if t.source == terminal]

    def test_invalid_transition_raises(self) -> None:
        with pytest.raises(InvalidTransition):
            find_transition(RequestStatus.APPROVED, Action.APPROVE)

    def test_return_and_reject_need_comment(self) -> None:
        assert find_transition(RequestStatus.PENDING_TL_REVIEW, Action.RETURN).requires_comment
        assert find_transition(RequestStatus.PENDING_DIRECTOR_APPROVAL, Action.REJECT).requires_comment
        assert not find_transition(RequestStatus.PENDING_TL_REVIEW, Action.APPROVE).requires_comment

    def test_available_actions_depend_on_capacity(self) -> None:
        assert available_actions(RequestStatus.PENDING_TL_REVIEW, {Actor.REQUESTER}) == [Action.WITHDRAW]
        assert set(available_actions(RequestStatus.PENDING_TL_REVIEW, {Actor.STEP_ASSIGNEE})) == {
            Action.APPROVE,
            Action.RETURN,
            Action.REJECT,
        }
