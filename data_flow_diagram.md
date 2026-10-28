Data Flow Diagram: success_tensile scenario

```mermaid
flowchart TD
    A["LabRequest (trusted envelope)<br/>authenticated_user_id = alice<br/>project_id = polymer-study<br/>resource_id = tensile-01<br/>start = 2026-10-15T10:00, end = 2026-10-15T11:00<br/>text = Reserve tensile-01 for polymer-study ..."]
    B["initialize_messages<br/>system prompt + trusted envelope + request text"]
    C["StructuredLLM returns one decision<br/>validated by DecisionAdapter<br/>(tool_call, clarification, or final)"]
    G["Action gate<br/>validate_proposed_tool_call<br/>1. request binding<br/>2. reservation preconditions (reserve only)<br/>3. no earlier successful mutation"]
    D["Denied: ToolObservation<br/>ok=False, error_code=action_gate_denied"]
    T["environment.dispatch(tool, arguments)<br/>tool is executed"]
    O["ToolObservation<br/>ok, data, error_code, message"]
    TR["Trace: TraceEvent(step, decision, observation, mutating)<br/>+ assistant and tool messages appended"]
    F["Final decision:<br/>validate_final_response<br/>checks citations and claimed actions against the trace"]
    R["AgentRun<br/>status = completed<br/>completed_actions = reserve_resource<br/>termination_reason = model_finished"]
    X["AgentRun<br/>status = failed<br/>termination_reason = invalid_final_response"]

    A --> B --> C
    C -->|"tool_call"| G
    G -->|"errors"| D
    G -->|"no errors"| T
    T --> O
    D --> TR
    O --> TR
    TR -->|"next step, up to max_steps"| C
    C -->|"final"| F
    F -->|"consistent with trace"| R
    F -->|"inconsistent"| X
```

This run has the model to make 4 tool calls, with each one passing the action gate. First, it searches policy using search_lab_documents to find TRN-210#tensile-tester. Then it checks for authorizations of action by alice. Next, it checks the status of tensile-01 for the specified interval. Finally, it calls reserve_resource. All of the preconditions are true, so a reservation is created. The final decision has status completed. It cites TRN-210#tensile-tester, and lists reserve_resource as the completed action. The function validate_final_response finds the citation in a successful search result, and the action in a successful mutating trace event. So the run ends as completed.
