from atlas_agent.agent import run_agent
from atlas_agent.llm import ScriptedLLM
from atlas_agent.models import LabRequest

INTERVAL = {"start": "2026-10-15T10:00:00", "end": "2026-10-15T11:00:00"}

REQUEST = LabRequest(
    authenticated_user_id="alice",
    text="Reserve tensile-01 for polymer-study from 2026-10-15 10:00 to 11:00.",
    project_id="polymer-study",
    resource_id="tensile-01",
    **INTERVAL,
)


def tool(name, arguments):
    return {"kind": "tool_call", "tool": name, "arguments": arguments, "reasoning_summary": "Test step."}


def reserve():
    return tool("reserve_resource", {"user_id": "alice", "project_id": "polymer-study", "resource_id": "tensile-01", **INTERVAL})


def final(status, completed_actions):
    return {"kind": "final", "response": {"status": status, "message": "Done.", "completed_actions": completed_actions}}


def test_reserve_without_required_checks_is_denied_before_execution(environment):
    reservations_before = len(environment.simulator.state["reservations"])
    llm = ScriptedLLM([reserve(), final("blocked", [])])

    run = run_agent(REQUEST, llm=llm, environment=environment)

    assert run.trace[0].observation.error_code == "action_gate_denied"
    assert "policy_not_retrieved" in run.trace[0].observation.message
    assert len(environment.simulator.state["reservations"]) == reservations_before


def test_final_response_claiming_denied_reservation_is_rejected(environment):
    llm = ScriptedLLM([reserve(), final("completed", ["reserve_resource"])])

    run = run_agent(REQUEST, llm=llm, environment=environment)

    assert run.response.status == "failed"
    assert run.termination_reason == "invalid_final_response"
    assert "completed_action_not_in_successful_trace" in run.response.message


def test_second_reservation_after_success_is_denied(environment):
    reservations_before = len(environment.simulator.state["reservations"])
    checks = [
        tool("search_lab_documents", {"query": "tensile tester lab_safety authorization calibration"}),
        tool("get_user_authorizations", {"user_id": "alice"}),
        tool("get_resource_status", {"resource_id": "tensile-01", **INTERVAL}),
    ]
    llm = ScriptedLLM(checks + [reserve(), reserve(), final("completed", ["reserve_resource"])])

    run = run_agent(REQUEST, llm=llm, environment=environment)

    assert run.trace[-1].observation.error_code == "action_gate_denied"
    assert "repeated_mutating_call" in run.trace[-1].observation.message
    assert len(environment.simulator.state["reservations"]) == reservations_before + 1
