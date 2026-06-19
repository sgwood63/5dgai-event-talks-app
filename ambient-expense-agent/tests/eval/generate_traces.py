import json
import os
import sys
from pathlib import Path

# Ensure the ambient-expense-agent folder is in sys.path
sys.path.append(str(Path(__file__).parent.parent.parent))

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from expense_agent.agent import root_agent

def parse_input_expense(payload_str):
    """Parses raw JSON string of expense payload."""
    try:
        return json.loads(payload_str)
    except Exception:
        return {}

def should_reject(expense_dict):
    """Checks if the description indicates a prompt-injection attempt."""
    desc = expense_dict.get("description", "").lower()
    # Detect prompt-injection attempts using keywords matched in the checkpoint
    if "bypass" in desc or "injection" in desc or "auto-approve" in desc:
        return True
    return False

def generate_traces():
    dataset_path = Path(__file__).parent / "datasets" / "basic-dataset.json"
    if not dataset_path.exists():
        print(f"Dataset not found at {dataset_path}")
        sys.exit(1)

    with open(dataset_path, "r") as f:
        dataset = json.load(f)

    session_service = InMemorySessionService()
    eval_cases_traces = []

    for case in dataset.get("eval_cases", []):
        case_id = case["eval_case_id"]
        prompt_text = case["prompt"]["parts"][0]["text"]
        expense_dict = parse_input_expense(prompt_text)

        print(f"Running scenario: {case_id}...")

        # Create session
        session_id = f"session-{case_id}"
        session = session_service.create_session_sync(
            user_id="eval-user", app_name="expense_agent", session_id=session_id
        )

        runner = Runner(
            agent=root_agent, session_service=session_service, app_name="expense_agent"
        )

        # 1. Run the initial prompt
        message = types.Content(role="user", parts=[types.Part.from_text(text=prompt_text)])
        events = list(runner.run(user_id="eval-user", session_id=session.id, new_message=message))

        # Check if workflow is paused (has long_running_tool_ids containing approval_decision)
        paused = False
        for event in events:
            if event.long_running_tool_ids and "approval_decision" in event.long_running_tool_ids:
                paused = True
                break

        # 2. Intercept and automate decision if paused
        if paused:
            decision = "reject" if should_reject(expense_dict) else "approve"
            print(f"  -> Workflow paused at human_approval. Automating decision: '{decision}'")

            resume_message = types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id="approval_decision",
                            name="approval_decision",
                            response={"result": decision},
                        )
                    )
                ],
            )
            # Resume running the runner
            events2 = list(runner.run(user_id="eval-user", session_id=session.id, new_message=resume_message))
            events.extend(events2)

        # 3. Format history turns into the standard EvalCase trace format
        turns = []
        turn_index = -1
        # Fetch the session's full, updated history of events
        full_session = session_service.get_session_sync(
            app_name="expense_agent", user_id="eval-user", session_id=session_id
        )
        
        for event in full_session.events:
            # Whenever user issues content, it starts/resumes a turn
            if event.author == "user":
                turn_index += 1
                turns.append({
                    "turn_index": turn_index,
                    "events": []
                })

            content_dict = None
            if event.content:
                try:
                    content_dict = event.content.model_dump(exclude_none=True)
                except Exception:
                    # fallback manual serialization
                    content_dict = {"role": event.content.role, "parts": []}
                    for part in event.content.parts:
                        part_dict = {}
                        if part.text is not None:
                            part_dict["text"] = part.text
                        if part.function_call is not None:
                            part_dict["function_call"] = part.function_call.model_dump(exclude_none=True)
                        if part.function_response is not None:
                            part_dict["function_response"] = part.function_response.model_dump(exclude_none=True)
                        content_dict["parts"].append(part_dict)

            # Safeguard: ensure we have a turn index
            if turn_index == -1:
                turn_index = 0
                turns.append({
                    "turn_index": turn_index,
                    "events": []
                })

            turns[-1]["events"].append({
                "author": event.author,
                "content": content_dict
            })

        # Find the final text response from the turns to populate the "responses" field
        final_response_text = None
        for turn in reversed(turns):
            for event in reversed(turn["events"]):
                if event["content"]:
                    parts = event["content"].get("parts", [])
                    texts = [p.get("text") for p in parts if p.get("text")]
                    if texts:
                        final_response_text = "".join(texts)
                        break
            if final_response_text:
                break

        responses = []
        if final_response_text:
            responses.append({
                "response": {
                    "role": "model",
                    "parts": [{"text": final_response_text}]
                }
            })

        # Append structured eval case to final output
        eval_cases_traces.append({
            "eval_case_id": case_id,
            "agent_data": {
                "agents": {
                    "expense_approval_workflow": {
                        "agent_id": "expense_approval_workflow",
                        "instruction": "Expense approval workflow"
                    },
                    "expense_agent": {
                        "agent_id": "expense_agent",
                        "instruction": "Expense approval agent"
                    }
                },
                "turns": turns
            },
            "responses": responses
        })

    # Save final results to artifacts/traces/generated_traces.json
    output_dir = Path(__file__).parent.parent.parent / "artifacts" / "traces"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "generated_traces.json"

    with open(output_file, "w") as f:
        json.dump({"eval_cases": eval_cases_traces}, f, indent=2)

    print(f"Successfully generated 5 evaluation traces in: {output_file}")

if __name__ == "__main__":
    generate_traces()
