"""Thin client for direct Azure AI Foundry model calls.

Replaces the earlier Foundry-Agent approach: registering resolve_customer /
resolve_product / check_order_risks / create_technical_escalation as real
callable tools turned out to require a Foundry Portal step (agent-level
tool registration -- confirmed live: Foundry rejects a `tools=` argument
passed per-request once `agent_name=` is set, with "Not allowed when agent
is specified"), and the installed azure-ai-projects SDK version exposes no
agent-management API to script that step either. For a small, fixed set of
lookups like GAF's, that's not worth the extra moving part anyway --
telecom-assistant's own pattern (one fast LLM call to classify/extract,
then plain Python calling a REST API deterministically) is simpler,
cheaper, and fully unit-testable without any Foundry-side configuration.

This module is the only place that builds the OpenAI-compatible client.
Authentication: API-key only, via FOUNDRY_API_KEY. `az login` / Entra ID
auth (DefaultAzureCredential) is not usable in this environment, so it is
not used at all here -- see _NoOpCredential below.
"""

import json
import logging
from typing import Any

from app.config import FOUNDRY_API_KEY, FOUNDRY_PROJECT_ENDPOINT, GAF_MODEL

logger = logging.getLogger("gaf_demo.foundry_client")


class FoundryNotConfiguredError(RuntimeError):
    """Raised when FOUNDRY_PROJECT_ENDPOINT / FOUNDRY_API_KEY are not set."""


class FoundryCallError(RuntimeError):
    """Raised when the Azure AI Foundry model call itself fails (auth, network, etc.)."""


class _NoOpCredential:
    """Placeholder passed as AIProjectClient(credential=...).

    Satisfies the constructor's structural TokenCredential requirement
    without ever performing Entra ID / DefaultAzureCredential auth (which is
    unavailable in this environment). Every call in this module passes an
    explicit `api_key=` to get_openai_client(), so get_token() is never
    actually invoked; it raises loudly if that assumption is ever wrong,
    rather than silently falling back to an ambient identity.
    """

    def get_token(self, *scopes: str, **kwargs: Any) -> Any:
        raise RuntimeError(
            "_NoOpCredential.get_token() was called — this module is meant to authenticate with "
            "FOUNDRY_API_KEY only."
        )

    def close(self) -> None:
        pass


def is_configured() -> bool:
    return bool(FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_API_KEY)


def _client():
    if not FOUNDRY_PROJECT_ENDPOINT or not FOUNDRY_API_KEY:
        raise FoundryNotConfiguredError(
            "FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_API_KEY must both be set to talk to Azure AI Foundry."
        )

    try:
        from azure.ai.projects import AIProjectClient
    except ImportError as exc:  # pragma: no cover - dependency install issue
        raise FoundryCallError("azure-ai-projects is not installed. Run: pip install -r requirements.txt") from exc

    project_client = AIProjectClient(endpoint=FOUNDRY_PROJECT_ENDPOINT, credential=_NoOpCredential())
    return project_client.get_openai_client(api_key=FOUNDRY_API_KEY, default_headers={"api-key": FOUNDRY_API_KEY})


def _reasoning_options() -> dict[str, str]:
    # gpt-5.4-nano uses the newer reasoning scale; gpt-5-mini accepts the
    # older "minimal" value used by this app for fast extraction.
    effort = "none" if "5.4" in GAF_MODEL else "minimal"
    return {"effort": effort}


def call_model(prompt: str) -> str:
    """One fast, stateless model call. Returns the raw text output.

    reasoning effort minimal + low verbosity: confirmed live this takes
    gpt-5-mini from ~8s to ~1.7s on this project with no loss of accuracy on
    a structured-extraction task -- the same speed trick telecom-assistant's
    own router uses (reasoning_effort="minimal" there; the Responses API
    spells it as a nested `reasoning={"effort": ...}` object instead).
    """
    if not FOUNDRY_PROJECT_ENDPOINT or not FOUNDRY_API_KEY:
        raise FoundryNotConfiguredError(
            "FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_API_KEY must both be set to talk to Azure AI Foundry."
        )

    try:
        client = _client()
        response = client.responses.create(
            model=GAF_MODEL,
            input=prompt,
            reasoning=_reasoning_options(),
            text={"verbosity": "low"},
        )
        return response.output_text or ""
    except (FoundryNotConfiguredError, FoundryCallError):
        raise
    except Exception as exc:  # noqa: BLE001 - surface any Azure/auth failure clearly
        raise FoundryCallError(f"Azure AI Foundry call to model '{GAF_MODEL}' failed: {exc}") from exc


def call_model_vision(prompt: str, image_data_url: str) -> str:
    """One model call with an image attached (Responses API input_image).
    Same deployment, same speed settings as call_model()."""
    if not FOUNDRY_PROJECT_ENDPOINT or not FOUNDRY_API_KEY:
        raise FoundryNotConfiguredError(
            "FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_API_KEY must both be set to talk to Azure AI Foundry."
        )

    try:
        client = _client()
        response = client.responses.create(
            model=GAF_MODEL,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": image_data_url},
                    ],
                }
            ],
            reasoning=_reasoning_options(),
            text={"verbosity": "low"},
        )
        return response.output_text or ""
    except (FoundryNotConfiguredError, FoundryCallError):
        raise
    except Exception as exc:  # noqa: BLE001
        raise FoundryCallError(f"Azure AI Foundry vision call to model '{GAF_MODEL}' failed: {exc}") from exc


def call_model_vision_json(prompt: str, image_data_url: str) -> dict[str, Any]:
    raw = call_model_vision(prompt, image_data_url)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise FoundryCallError(f"Model '{GAF_MODEL}' did not return valid JSON: {raw[:200]!r}") from exc


def call_model_json(prompt: str) -> dict[str, Any]:
    """Same as call_model(), parsed as JSON. Raises FoundryCallError (not a
    silent {}) if the model's output isn't valid JSON -- a caller asking for
    structured output needs to know that failed, not get an empty dict that
    looks like "nothing found".
    """
    raw = call_model(prompt)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise FoundryCallError(f"Model '{GAF_MODEL}' did not return valid JSON: {raw[:200]!r}") from exc
