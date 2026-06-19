# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
import logging
import os
import uuid

import google.auth
from fastapi import FastAPI, HTTPException, Request
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.cli.utils.service_factory import create_session_service_from_options
from google.adk.runners import Runner
from google.genai import types

from expense_agent.agent import root_agent
from expense_agent.app_utils.telemetry import setup_telemetry
from expense_agent.app_utils.typing import Feedback

# Configure standard Python logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

setup_telemetry()

allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
session_service_uri = None

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=False,  # Unconditional disabled per checklist
)
app.title = "ambient-expense-agent"
app.description = "API for interacting with the Agent ambient-expense-agent"

# Initialize local session service
session_service = create_session_service_from_options(
    base_dir=AGENT_DIR,
    session_service_uri=session_service_uri,
    use_local_storage=True,
)

runner = Runner(
    agent=root_agent,
    session_service=session_service,
    app_name="expense_agent",
)


@app.post("/pubsub")
async def handle_pubsub(request: Request):
    """Custom route to handle Pub/Sub event triggers and run the workflow."""
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse JSON body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Normalize subscription path to a short name for readability
    subscription_path = body.get("subscription", "")
    if subscription_path and "/" in subscription_path:
        user_id = subscription_path.split("/")[-1]
    else:
        user_id = "pubsub-trigger"

    # Extract message ID or generate uuid
    message = body.get("message", {})
    message_id = message.get("messageId")
    session_id = f"ps-{message_id}" if message_id else f"ps-{uuid.uuid4()}"

    logger.info(
        f"Received Pub/Sub event. Normalizing subscriber '{subscription_path}' "
        f"to '{user_id}'. Session: {session_id}"
    )

    # Create session in the session service
    try:
        session = await session_service.create_session(
            app_name="expense_agent",
            user_id=user_id,
            session_id=session_id,
        )
    except Exception as e:
        logger.error(f"Failed to create session in session service: {e}")
        session = await session_service.get_session(
            app_name="expense_agent",
            user_id=user_id,
            session_id=session_id,
        )

    # Convert request body to types.Content
    message_payload = json.dumps(body)
    new_message = types.Content(
        role="user", parts=[types.Part.from_text(text=message_payload)]
    )

    # Run the workflow using the runner
    events = []
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=new_message,
        ):
            events.append(event)
    except Exception as e:
        logger.error(f"Error during workflow execution: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {e}")

    # Check if workflow is paused for human review
    paused = False
    for event in events:
        if event.long_running_tool_ids:
            paused = True
            break

    status = "PAUSED_FOR_REVIEW" if paused else "COMPLETED"
    logger.info(f"Workflow execution {session_id} finished with status: {status}")

    return {
        "status": status,
        "session_id": session.id,
        "user_id": user_id,
    }


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    logger.info(f"Feedback logged: {feedback.model_dump()}")
    return {"status": "success"}


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
