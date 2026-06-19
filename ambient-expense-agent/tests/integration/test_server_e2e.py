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
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
import requests
from requests.exceptions import RequestException

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = os.getenv("TEST_SERVER_URL", "http://127.0.0.1:8000")
STREAM_URL = BASE_URL + "/run_sse"
FEEDBACK_URL = BASE_URL + "/feedback"

HEADERS = {"Content-Type": "application/json"}


def log_output(pipe: Any, log_func: Any) -> None:
    """Log the output from the given pipe."""
    for line in iter(pipe.readline, ""):
        log_func(line.strip())


def start_server() -> subprocess.Popen[str]:
    """Start the FastAPI server using subprocess and log its output."""
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "expense_agent.fast_api_app:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]
    env = os.environ.copy()
    env["INTEGRATION_TEST"] = "TRUE"
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    # Start threads to log stdout and stderr in real-time
    threading.Thread(
        target=log_output, args=(process.stdout, logger.info), daemon=True
    ).start()
    threading.Thread(
        target=log_output, args=(process.stderr, logger.error), daemon=True
    ).start()

    return process


def wait_for_server(timeout: int = 90, interval: int = 1) -> bool:
    """Wait for the server to be ready."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get("http://127.0.0.1:8000/docs", timeout=10)
            if response.status_code == 200:
                logger.info("Server is ready")
                return True
        except RequestException:
            pass
        time.sleep(interval)
    logger.error(f"Server did not become ready within {timeout} seconds")
    return False


@pytest.fixture(scope="session")
def server_fixture(request: Any) -> Iterator[Any]:
    """Pytest fixture to start and stop the server for testing."""
    if os.getenv("TEST_SERVER_URL"):
        logger.info(f"Using external server at {BASE_URL}")
        yield None
        return

    logger.info("Starting server process")
    server_process = start_server()
    if not wait_for_server():
        pytest.fail("Server failed to start")
    logger.info("Server process started")

    def stop_server() -> None:
        logger.info("Stopping server process")
        server_process.terminate()
        server_process.wait()
        logger.info("Server process stopped")

    request.addfinalizer(stop_server)
    yield server_process


def test_chat_stream(server_fixture: subprocess.Popen[str]) -> None:
    """Test the chat stream functionality."""
    logger.info("Starting chat stream test")
    # Create session first
    user_id = "test_user_123"
    session_data = {"state": {"preferred_language": "English", "visit_count": 1}}

    session_url = f"{BASE_URL}/apps/expense_agent/users/{user_id}/sessions"
    session_response = requests.post(
        session_url,
        headers=HEADERS,
        json=session_data,
        timeout=60,
    )
    assert session_response.status_code == 200
    logger.info(f"Session creation response: {session_response.json()}")
    session_id = session_response.json()["id"]

    # Then send chat message
    data = {
        "app_name": "expense_agent",
        "user_id": user_id,
        "session_id": session_id,
        "new_message": {
            "role": "user",
            "parts": [{"text": '{"amount": 45.0, "submitter": "alice@example.com", "category": "Meals", "description": "Client lunch", "date": "2026-06-18"}'}],
        },
        "streaming": True,
    }
    response = requests.post(
        STREAM_URL, headers=HEADERS, json=data, stream=True, timeout=60
    )
    assert response.status_code == 200

    # Parse SSE events from response
    events = []
    for line in response.iter_lines():
        if line:
            # SSE format is "data: {json}"
            line_str = line.decode("utf-8")
            if line_str.startswith("data: "):
                event_json = line_str[6:]  # Remove "data: " prefix
                event = json.loads(event_json)
                events.append(event)

    assert events, "No events received from stream"
    # Check for valid content in the response
    has_text_content = False
    for event in events:
        content = event.get("content")
        if (
            content is not None
            and content.get("parts")
            and any(part.get("text") for part in content["parts"])
        ):
            has_text_content = True
            break

    assert has_text_content, "Expected at least one event with text content"


def test_chat_stream_error_handling(server_fixture: subprocess.Popen[str]) -> None:
    """Test the chat stream error handling."""
    logger.info("Starting chat stream error handling test")
    data = {
        "input": {"messages": [{"type": "invalid_type", "content": "Cause an error"}]}
    }
    response = requests.post(
        STREAM_URL, headers=HEADERS, json=data, stream=True, timeout=10
    )

    assert response.status_code == 422, (
        f"Expected status code 422, got {response.status_code}"
    )
    logger.info("Error handling test completed successfully")


def test_collect_feedback(server_fixture: subprocess.Popen[str]) -> None:
    """
    Test the feedback collection endpoint (/feedback) to ensure it properly
    logs the received feedback.
    """
    # Create sample feedback data
    feedback_data = {
        "score": 4,
        "user_id": "test-user-456",
        "session_id": "test-session-456",
        "text": "Great response!",
    }

    response = requests.post(
        FEEDBACK_URL, json=feedback_data, headers=HEADERS, timeout=10
    )
    assert response.status_code == 200


def test_pubsub_endpoint(server_fixture: subprocess.Popen[str]) -> None:
    """Test the custom Pub/Sub event ingestion endpoint."""
    import base64

    expense_data = {
        "amount": 45.0,
        "submitter": "alice@example.com",
        "category": "Meals",
        "description": "Client lunch",
        "date": "2026-06-18",
    }
    encoded_data = base64.b64encode(json.dumps(expense_data).encode("utf-8")).decode("utf-8")

    payload = {
        "message": {
            "data": encoded_data,
            "messageId": "987654321",
            "publishTime": "2026-06-18T12:00:00Z",
        },
        "subscription": "projects/my-project/subscriptions/test-sub",
    }

    pubsub_url = f"{BASE_URL}/pubsub"
    response = requests.post(pubsub_url, json=payload, headers=HEADERS, timeout=10)

    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "COMPLETED"
    assert res_json["user_id"] == "test-sub"
    assert res_json["session_id"] == "ps-987654321"


def test_hitl_json_e2e(server_fixture: subprocess.Popen[str]) -> None:
    """Test multi-turn JSON chat interaction with human-in-the-loop approval."""
    # 1. Create a session
    user_id = "test_user_json_hitl"
    session_url = f"{BASE_URL}/apps/expense_agent/users/{user_id}/sessions"
    session_response = requests.post(session_url, headers=HEADERS, json={}, timeout=10)
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    # 2. Send high-value expense payload to trigger review and pause
    payload = '{"amount": 150.0, "submitter": "bob@example.com", "category": "Travel", "description": "Flight to SF", "date": "2026-06-18"}'
    data = {
        "app_name": "expense_agent",
        "user_id": user_id,
        "session_id": session_id,
        "new_message": {
            "role": "user",
            "parts": [{"text": payload}],
        },
        "streaming": True,
    }
    response = requests.post(STREAM_URL, headers=HEADERS, json=data, stream=True, timeout=15)
    assert response.status_code == 200

    # Verify the workflow paused (yields long_running_tool_ids containing approval_decision)
    paused = False
    events = []
    for line in response.iter_lines():
        if line:
            event = json.loads(line.decode("utf-8")[6:])
            events.append(event)
            if event.get("longRunningToolIds") and "approval_decision" in event.get("longRunningToolIds", []):
                paused = True

    assert paused, f"Expected workflow to pause. Events received: {events}"

    # 3. Resume the workflow with approval response
    resume_data = {
        "app_name": "expense_agent",
        "user_id": user_id,
        "session_id": session_id,
        "new_message": {
            "role": "user",
            "parts": [
                {
                    "function_response": {
                        "id": "approval_decision",
                        "name": "approval_decision",
                        "response": {"result": "approve"},
                    }
                }
            ],
        },
        "streaming": True,
    }
    response2 = requests.post(STREAM_URL, headers=HEADERS, json=resume_data, stream=True, timeout=15)
    assert response2.status_code == 200

    # Verify that the workflow completed and was APPROVED
    completed = False
    approved = False
    for line in response2.iter_lines():
        if line:
            event = json.loads(line.decode("utf-8")[6:])
            content = event.get("content")
            if content and content.get("parts"):
                for part in content["parts"]:
                    text = part.get("text", "")
                    if "APPROVED" in text:
                        approved = True
                        completed = True

    assert completed and approved, "Expected workflow to complete with APPROVED status"


def test_hitl_pubsub_e2e(server_fixture: subprocess.Popen[str]) -> None:
    """Test multi-turn Pub/Sub event flow with human-in-the-loop rejection."""
    import base64

    # 1. Send high-value expense event to /pubsub
    expense_data = {
        "amount": 250.0,
        "submitter": "attacker@example.com",
        "category": "Meals",
        "description": "Premium Dinner",
        "date": "2026-06-18",
    }
    encoded_data = base64.b64encode(json.dumps(expense_data).encode("utf-8")).decode("utf-8")

    payload = {
        "message": {
            "data": encoded_data,
            "messageId": "pubsub-hitl-msg-123",
            "publishTime": "2026-06-18T12:00:00Z",
        },
        "subscription": "projects/my-project/subscriptions/admin-review-sub",
    }

    pubsub_url = f"{BASE_URL}/pubsub"
    response = requests.post(pubsub_url, json=payload, headers=HEADERS, timeout=10)

    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "PAUSED_FOR_REVIEW"
    session_id = res_json["session_id"]
    user_id = res_json["user_id"]
    assert user_id == "admin-review-sub"

    # 2. Resume the workflow with rejection response
    resume_data = {
        "app_name": "expense_agent",
        "user_id": user_id,
        "session_id": session_id,
        "new_message": {
            "role": "user",
            "parts": [
                {
                    "function_response": {
                        "id": "approval_decision",
                        "name": "approval_decision",
                        "response": {"result": "reject"},
                    }
                }
            ],
        },
        "streaming": True,
    }
    response2 = requests.post(STREAM_URL, headers=HEADERS, json=resume_data, stream=True, timeout=15)
    assert response2.status_code == 200

    # Verify that the workflow completed and was REJECTED
    completed = False
    rejected = False
    for line in response2.iter_lines():
        if line:
            event = json.loads(line.decode("utf-8")[6:])
            content = event.get("content")
            if content and content.get("parts"):
                for part in content["parts"]:
                    text = part.get("text", "")
                    if "REJECTED" in text:
                        rejected = True
                        completed = True

    assert completed and rejected, "Expected workflow to complete with REJECTED status"


