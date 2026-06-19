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

import base64
import sys
import json
import os
import re
from collections.abc import AsyncGenerator
from typing import Any

import google.auth
from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.apps import App, ResumabilityConfig
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.models import Gemini
from google.adk.workflow import Workflow
from google.genai import types
from pydantic import BaseModel, Field

from . import config

try:
    _, project_id = google.auth.default()
    if project_id:
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
except Exception:
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key
        os.environ["GOOGLE_API_KEY"] = api_key


class ExpenseDetails(BaseModel):
    amount: float = Field(description="The numeric amount of the expense")
    submitter: str = Field(
        description="The email or name of the employee submitting the expense"
    )
    category: str = Field(
        description="The type or category of the expense (e.g. Travel, Meals)"
    )
    description: str = Field(
        description="A brief description or justification of the expense"
    )
    date: str = Field(description="The date of the expense (YYYY-MM-DD)")


class RiskAssessment(BaseModel):
    is_risky: bool = Field(
        description="True if there are high-risk factors, False otherwise"
    )
    risk_factors: str = Field(
        description="Bullet points of identified risk factors, if any"
    )
    explanation: str = Field(description="A brief explanation of the risk assessment")


def parse_and_extract(node_input: Any) -> ExpenseDetails:
    """Parses incoming JSON payloads (Pub/Sub or direct) and extracts expense details."""
    data = None

    if hasattr(node_input, "parts"):
        text_content = ""
        for part in node_input.parts:
            if hasattr(part, "text") and part.text:
                text_content += part.text
        if text_content:
            try:
                data = json.loads(text_content)
            except json.JSONDecodeError:
                data = text_content
    elif isinstance(node_input, str):
        try:
            data = json.loads(node_input)
        except json.JSONDecodeError:
            data = node_input
    elif isinstance(node_input, dict):
        data = node_input
    else:
        try:
            data = json.loads(str(node_input))
        except Exception:
            data = node_input

    # Extract the payload dictionary (under "data" or "message.data" for Pub/Sub)
    payload = None
    if isinstance(data, dict):
        if (
            "message" in data
            and isinstance(data["message"], dict)
            and "data" in data["message"]
        ):
            payload = data["message"]["data"]
        elif "data" in data:
            payload = data["data"]
        else:
            payload = data
    else:
        payload = data

    # Base64 decode if it's a base64 string
    if isinstance(payload, str):
        try:
            decoded_bytes = base64.b64decode(payload.strip(), validate=True)
            decoded_str = decoded_bytes.decode("utf-8")
            payload = json.loads(decoded_str)
        except Exception:
            try:
                payload = json.loads(payload)
            except Exception:
                pass

    if not isinstance(payload, dict):
        raise ValueError(
            f"Could not parse payload to a valid dictionary. Payload: {payload}"
        )

    # Helper for case-insensitive field matching
    def get_field(keys: list[str], default: Any) -> Any:
        for key in keys:
            if key in payload:
                return payload[key]
            if key.lower() in payload:
                return payload[key.lower()]
            if key.capitalize() in payload:
                return payload[key.capitalize()]
        return default

    amount_val = get_field(["amount"], 0.0)
    try:
        amount = float(amount_val)
    except Exception:
        amount = 0.0

    submitter = str(get_field(["submitter", "email", "user"], "Unknown"))
    category = str(get_field(["category", "type"], "General"))
    description = str(
        get_field(["description", "details", "purpose"], "No description")
    )
    date = str(get_field(["date", "time"], "Unknown"))

    return ExpenseDetails(
        amount=amount,
        submitter=submitter,
        category=category,
        description=description,
        date=date,
    )


def route_expense(node_input: ExpenseDetails) -> Event:
    """Routes the expense depending on the dollar threshold."""
    if node_input.amount < config.THRESHOLD:
        return Event(output=node_input, route="auto_approve")
    else:
        return Event(output=node_input, route="risk_review")


def approve_instantly(node_input: ExpenseDetails) -> dict:
    """Automatically approves expenses under the threshold."""
    return {
        "decision": "approve",
        "approved": True,
        "reason": f"Auto-approved (Amount ${node_input.amount} is below threshold ${config.THRESHOLD})",
    }


def scrub_pii(text: str) -> tuple[str, list[str]]:
    """Scrubs SSNs and Credit Card numbers from description and returns redacted categories."""
    ssn_pattern = re.compile(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b")
    cc_pattern = re.compile(r"\b(?:\d[ -]?){13,19}\b")

    scrubbed = text
    redacted = []

    if ssn_pattern.search(scrubbed):
        scrubbed = ssn_pattern.sub("[REDACTED SSN]", scrubbed)
        redacted.append("SSN")

    if cc_pattern.search(scrubbed):
        scrubbed = cc_pattern.sub("[REDACTED CREDIT CARD]", scrubbed)
        redacted.append("Credit Card")

    return scrubbed, redacted


def detect_prompt_injection(text: str) -> bool:
    """Detects prompt injection words/phrases attempting to bypass or override instructions."""
    injection_patterns = [
        r"ignore\s+(?:all\s+)?previous\s+instructions",
        r"bypass\s+(?:all\s+)?rules",
        r"force\s+auto-approval",
        r"auto-approve\s+this",
        r"override\s+(?:all\s+)?policies",
        r"you\s+must\s+approve",
        r"system\s+directive",
        r"new\s+instruction",
        r"forget\s+(?:what\s+)?you\s+were\s+told",
    ]

    lowercase_text = text.lower()
    for pattern in injection_patterns:
        if re.search(pattern, lowercase_text):
            return True

    suspicious_phrases = [
        "approve instantly",
        "bypass the rules",
        "bypass rules",
        "force approval",
        "ignore rules",
    ]
    for phrase in suspicious_phrases:
        if phrase in lowercase_text:
            return True

    return False


def security_checkpoint(node_input: ExpenseDetails) -> Event:
    """Scrubs PII and defends against prompt injection, routing flagged inputs straight to human review."""
    scrubbed_desc, redacted_categories = scrub_pii(node_input.description)
    node_input.description = scrubbed_desc

    is_injection = detect_prompt_injection(scrubbed_desc)

    if is_injection:
        security_alert = {
            "is_risky": True,
            "risk_factors": "PROMPT INJECTION ATTEMPT DETECTED",
            "explanation": (
                "Security alert: The description contained potential prompt injection. "
                f"Redacted PII categories: {', '.join(redacted_categories) if redacted_categories else 'None'}. "
                "Raw input description was blocked from the model."
            ),
        }
        return Event(
            output=security_alert,
            route="flagged",
            state={"redacted_pii": redacted_categories, "security_event": True},
        )
    else:
        return Event(
            output=node_input,
            route="clean",
            state={"redacted_pii": redacted_categories, "security_event": False},
        )


# LLM Risk Review Agent
# LLM Risk Review Agent
is_pytest = "pytest" in sys.modules or any("pytest" in arg for arg in sys.argv)
has_api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
has_vertex = False
try:
    _, project_id = google.auth.default()
    if project_id:
        has_vertex = True
except Exception:
    pass

if not is_pytest and not has_api_key and not has_vertex:
    from unittest.mock import MagicMock
    from google.adk.models.llm_response import LlmResponse

    class MockGemini(Gemini):
        async def generate_content_async(
            self, llm_request: Any, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            response_text = json.dumps({
                "is_risky": True,
                "risk_factors": "- Amount is $150.0 which exceeds the $100.0 threshold.",
                "explanation": "This is a mock risk assessment because no GEMINI_API_KEY was provided."
            })
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=response_text)]
                )
            )

        @property
        def api_client(self) -> Any:
            return MagicMock()

    _GeminiClass = MockGemini
else:
    _GeminiClass = Gemini

risk_assessment = LlmAgent(
    name="risk_assessment",
    model=_GeminiClass(
        model=config.MODEL_NAME,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are an expense compliance reviewer. Review the provided expense details "
        "and check for anomalies, risk factors, or policy violations (e.g. suspicious categories, "
        "mismatched descriptions, excessive amounts, or odd dates). "
        "Provide a structured assessment output conforming to the schema."
    ),
    output_schema=RiskAssessment,
)


async def human_approval(node_input: dict) -> AsyncGenerator[Any, None]:
    """Pauses the workflow for human review if the expense requires review."""
    msg = (
        f"⚠️ High-value expense requires human review!\n"
        f"Risk Assessment:\n"
        f"- Is Risky: {node_input.get('is_risky')}\n"
        f"- Risk Factors: {node_input.get('risk_factors')}\n"
        f"- Explanation: {node_input.get('explanation')}\n\n"
        f"Please reply with 'approve' or 'reject':"
    )
    yield RequestInput(interrupt_id="approval_decision", message=msg)


def record_outcome(ctx: Context, node_input: Any) -> Event:
    """Records the final decision outcome and displays it in the UI/stdout."""
    if isinstance(node_input, dict):
        decision = node_input.get("decision", "unknown")
        approved = node_input.get("approved", False)
        reason = node_input.get("reason", "")
    else:
        # String response from human approval resumption
        decision = str(node_input).strip().lower()
        approved = decision == "approve"
        reason = f"Human review outcome: {decision}"

    security_event = ctx.state.get("security_event", False)
    redacted_pii = ctx.state.get("redacted_pii", [])

    status = "APPROVED" if approved else "REJECTED"
    outcome_text = (
        f"🏁 Workflow Finished!\n"
        f"Expense Status: {status}\n"
        f"Decision: {decision}\n"
        f"Details: {reason}"
    )

    if security_event:
        outcome_text += (
            "\n⚠️ SECURITY ALERT: Prompt injection attempt was detected and bypassed!"
        )
    if redacted_pii:
        outcome_text += f"\n🔒 PII Redacted: {', '.join(redacted_pii)}"

    return Event(
        content=types.Content(
            role="model", parts=[types.Part.from_text(text=outcome_text)]
        ),
        output={
            "status": status,
            "reason": reason,
            "security_event": security_event,
            "redacted_pii": redacted_pii,
        },
    )


root_agent = Workflow(
    name="expense_approval_workflow",
    edges=[
        ("START", parse_and_extract),
        (parse_and_extract, route_expense),
        (
            route_expense,
            {"auto_approve": approve_instantly, "risk_review": security_checkpoint},
        ),
        (
            security_checkpoint,
            {"clean": risk_assessment, "flagged": human_approval},
        ),
        (risk_assessment, human_approval),
        (human_approval, record_outcome),
        (approve_instantly, record_outcome),
    ],
)

app = App(
    root_agent=root_agent,
    name="expense_agent",
    resumability_config=ResumabilityConfig(is_resumable=True),
)
