from __future__ import annotations

from pydantic import ValidationError

from .agent_models import (
    ClarificationDecision,
    DecisionAdapter,
    FinalDecision,
    ToolCallDecision,
)
from .llm import StructuredLLM
from .models import AgentResponse, AgentRun, LabRequest, ToolObservation, TraceEvent
from .prompts import initialize_messages
from .tools import MUTATING_TOOLS, ToolEnvironment
from .validation import validate_final_response, validate_proposed_tool_call


def _failed(message: str, trace: list[TraceEvent], reason: str) -> AgentRun:
    return AgentRun(
        response=AgentResponse(status="failed", message=message),
        trace=trace,
        termination_reason=reason,
    )


def run_agent(
    request: LabRequest,
    *,
    llm: StructuredLLM,
    environment: ToolEnvironment,
    max_steps: int = 10,
) -> AgentRun:
    messages = initialize_messages(request)
    trace: list[TraceEvent] = []

    for step in range(1, max_steps + 1):
        try:
            decision = llm.generate(messages=messages, response_model=DecisionAdapter)
        except (ValidationError, ValueError, TypeError, RuntimeError) as exc:
            return _failed(f"The model did not produce a valid decision: {exc}", trace, "invalid_model_decision")

        if isinstance(decision, ClarificationDecision):
            return AgentRun(response=AgentResponse(status="clarification_required", message=decision.question), trace=trace, termination_reason="clarification_required")

        if isinstance(decision, FinalDecision):
            errors = validate_final_response(decision.response, trace)
            if errors:
                return _failed(f"The final response was inconsistent with the trace: {errors}", trace, "invalid_final_response")
            else:
                return AgentRun(response=decision.response, trace=trace, termination_reason="model_finished")

        if not isinstance(decision, ToolCallDecision):
            return _failed("Unsupported decision type.", trace, "invalid_model_decision")

        errors = validate_proposed_tool_call(decision, request=request, trace=trace)
        if decision.tool in MUTATING_TOOLS:
            for event in trace:
                if event.mutating and event.observation.ok:
                    errors.append("repeated_mutating_call")
                    break
                else:
                    continue

        if errors:
            observation = ToolObservation(ok=False, tool=decision.tool, error_code="action_gate_denied", message=", ".join(errors))
        else:
            observation = environment.dispatch(decision.tool, decision.arguments)

        trace.append(
            TraceEvent(step=step, decision=decision.model_dump(), observation=observation, mutating=decision.tool in MUTATING_TOOLS)
        )

        messages.append({"role": "assistant", "content": decision.model_dump_json()})
        messages.append({"role": "tool", "content": observation.model_dump_json()})

    return _failed("The maximum number of steps was reached.", trace, "maximum_steps_exceeded")
