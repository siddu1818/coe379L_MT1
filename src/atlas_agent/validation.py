"""Milestone 3: implement three selected validation responsibilities."""

from __future__ import annotations

from .agent_models import ToolCallDecision
from .models import AgentResponse, LabRequest, TraceEvent
from .policy_context import ReservationContext, build_reservation_context

BOUND_FIELDS = ("project_id","resource_id","start","end")

PRECONDITION_ERRORS = {
    "arguments_complete":"arguments_incomplete",
    "policy_retrieved":"policy_not_retrieved",
    "authorizations_checked":"authorizations_not_checked",
    "resource_status_checked":"resource_status_not_checked",
    "project_authorized":"project_not_authorized",
    "qualification_current":"required_qualification_missing",
    "resource_available":"resource_not_available",
    "calibration_current":"calibration_not_current",
    "maintenance_clear":"resource_under_maintenance",
    "after_hours_approval_satisfied":"after_hours_approval_missing",
}


def validate_request_binding(
    decision: ToolCallDecision,
    *,
    request: LabRequest,
) -> list[str]:
    args = decision.arguments
    errors = []
    if "user_id" in args:
        if args["user_id"] != request.authenticated_user_id:
            errors.append("user_id_must_match_authenticated_user")
    for field in BOUND_FIELDS:
        expected = getattr(request, field)
        if field in args and expected is not None:
            if args[field] != expected:
                errors.append(f"{field}_does_not_match_request")
        if decision.tool == "reserve_resource":
            if expected is None:
                errors.append(f"{field}_unresolved_in_request")
    return errors


def validate_reservation_preconditions(context: ReservationContext) -> list[str]:
    errors = []
    for field, error in PRECONDITION_ERRORS.items():
        fact = getattr(context, field)
        if not fact:
            errors.append(error)
    return errors


def validate_proposed_tool_call(
    decision: ToolCallDecision,
    *,
    request: LabRequest,
    trace: list[TraceEvent],
) -> list[str]:
    """Supplied wrapper. Do not modify this function."""
    errors = validate_request_binding(decision, request=request)
    if decision.tool == "reserve_resource":
        context = build_reservation_context(decision, trace)
        errors.extend(validate_reservation_preconditions(context))
    return errors


def retrieved_passage_ids(trace: list[TraceEvent]) -> set[str]:
    """Supplied helper. Do not modify this function."""
    identifiers: set[str] = set()
    for event in trace:
        if event.observation.tool != "search_lab_documents" or not event.observation.ok:
            continue
        identifiers.update(
            passage["passage_id"]
            for passage in event.observation.data.get("passages", [])
        )
    return identifiers


def validate_final_response(
    response: AgentResponse, trace: list[TraceEvent]
) -> list[str]:
    errors = []
    retrieved = retrieved_passage_ids(trace)
    unretrieved = []
    for citation in response.citations:
        if citation not in retrieved:
            unretrieved.append(citation)
    if unretrieved:
        errors.append(f"citations_not_retrieved: {', '.join(unretrieved)}")

    mutations = []
    for event in trace:
        if event.mutating and event.observation.ok:
            mutations.append(event.observation.tool)

    for action in response.completed_actions:
        if action not in mutations:
            errors.append("completed_action_not_in_successful_trace")
            break

    if response.status == "completed":
        if not mutations:
            errors.append("completed_without_successful_mutation")
        if not response.completed_actions:
            errors.append("completed_without_completed_actions")
    else:
        if response.completed_actions:
            errors.append("completed_actions_on_non_completed_response")
        if mutations:
            errors.append("unreported_successful_mutation")
    return errors
