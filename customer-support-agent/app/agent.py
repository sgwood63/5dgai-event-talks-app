# ruff: noqa
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

import os
from typing import Any
import google.auth

from google.adk.agents import LlmAgent
from google.adk.workflow import Workflow, START
from google.adk.events import Event, EventActions
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types
from pydantic import BaseModel, Field

# Setup environment variables safely, falling back to API keys if ADC is missing.
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


# Define the structured output for query classification
class Classification(BaseModel):
    is_shipping_related: bool = Field(
        description="True if the user query is related to shipping (such as rates, tracking, delivery, returns). False otherwise."
    )
    explanation: str = Field(
        description="Brief explanation of why the query was classified as shipping-related or not."
    )


# Classifier Agent: Classifies if user query is shipping-related
classifier_agent = LlmAgent(
    name="classifier_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "Analyze the user's latest query and determine if it is related to shipping "
        "(rates, tracking, delivery, returns, or other shipping company services). "
        "Provide a structured output using the Classification schema. "
        "Be generous in classifying as shipping-related if the query can be interpreted "
        "as asking about package details, delivery times, return policies, or courier rates."
    ),
    output_schema=Classification,
)


# Router Node: Directs flow based on the classification dict output
def router_node(node_input: dict) -> Event:
    """Routes the workflow based on classification result."""
    is_shipping = node_input.get("is_shipping_related", False)
    if is_shipping:
        return Event(output=node_input, actions=EventActions(route="shipping"))
    return Event(output=node_input, actions=EventActions(route="unrelated"))


# FAQ Agent: Specialist that answers shipping inquiries
faq_agent = LlmAgent(
    name="faq_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are an enthusiastic and super-playful customer support representative for a shipping company! 🚚✨ "
        "Answer the user's query about shipping (rates, tracking, delivery, returns) using general shipping knowledge. "
        "Use fun emojis (like 📦, 🚚, 🚀, 🎉) and make sure to enthusiastically highlight that we offer "
        "FREE shipping on all orders over $50! 🎉 Keep the tone extremely friendly, cheerful, and professional."
    ),
)


# Decline Node: Politely refuses unrelated queries
def decline_node(node_input: Any):
    """Politely declines to answer queries unrelated to shipping."""
    msg = (
        "I'm sorry, but I can only assist you with shipping-related inquiries "
        "(such as shipping rates, package tracking, delivery status, and returns). "
        "How can I help you with your shipping needs today?"
    )
    # Yield content for the web UI/chat display
    yield Event(
        content=types.Content(role="model", parts=[types.Part.from_text(text=msg)])
    )
    # Yield output for downstream nodes/runner output
    yield Event(output=msg)


# Graph Workflow: Coordinates the classification and routing flow
root_agent = Workflow(
    name="customer_support_workflow",
    edges=[
        (START, classifier_agent),
        (classifier_agent, router_node),
        (router_node, {"shipping": faq_agent, "unrelated": decline_node}),
    ],
)


# Initialize the App container
app = App(
    root_agent=root_agent,
    name="app",
)
