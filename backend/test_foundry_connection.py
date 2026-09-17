"""Standalone Azure AI Foundry connectivity check — API-key auth only.

Run directly (NOT via pytest — this makes a real network call):

    cd backend
    .venv\\Scripts\\activate
    python test_foundry_connection.py

`az login` / Entra ID auth is unavailable in this environment (blocked by
policy), so this uses API-key authentication exclusively: FOUNDRY_API_KEY is
passed straight to `get_openai_client(api_key=...)`.

Direct model call, not an agent: registering resolve_customer/resolve_product/
etc. as real Foundry Agent tools turned out to need a Portal step this
environment can't automate (confirmed live: Foundry rejects a `tools=`
argument passed per-request once `agent_name=` is set), and for a small
fixed set of lookups, direct calls (this app's actual architecture now) are
simpler, cheaper, and fully unit-testable without any agent configuration.
See app/foundry_client.py.

Only the endpoint and model name are ever printed. The API key itself is
never logged, never echoed, and never included in any exception message
printed here (Python exceptions from httpx/openai do not embed request
header values, only the response body).

Named test_foundry_connection.py so it lives next to the pytest suite, but it
defines no test_* functions, so `pytest` collects the module (0 items)
without ever executing this network call.
"""

import os
import sys

from dotenv import load_dotenv

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
load_dotenv(os.path.join(_BACKEND_DIR, ".env"))


class _NoOpCredential:
    """Structural placeholder only — see app/foundry_client.py for why this
    is safe: api_key is always passed explicitly, so get_token() never runs."""

    def get_token(self, *scopes, **kwargs):
        raise RuntimeError("_NoOpCredential.get_token() should never be called in API-key auth mode.")

    def close(self):
        pass


def main() -> int:
    from azure.ai.projects import AIProjectClient

    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
    api_key = os.environ.get("FOUNDRY_API_KEY", "")
    model = os.environ.get("GAF_MODEL", "gpt-5-mini")
    reasoning_effort = "none" if "5.4" in model else "minimal"

    print(f"FOUNDRY_PROJECT_ENDPOINT = {endpoint or '(not set)'}")
    print(f"GAF_MODEL                = {model}")
    print(f"FOUNDRY_API_KEY          = {'(set)' if api_key else '(not set)'}")

    if not endpoint or not api_key:
        print("\nMissing FOUNDRY_PROJECT_ENDPOINT and/or FOUNDRY_API_KEY. Set them in .env.")
        return 1

    print("\nCreating AIProjectClient (API-key auth, no Entra ID / DefaultAzureCredential)...")
    project_client = AIProjectClient(
        endpoint=endpoint,
        credential=_NoOpCredential(),
    )
    print("AIProjectClient created.")

    print(f"\nGetting a plain OpenAI-compatible client (no agent_name) with API-key auth...")
    # This gateway validates key auth via the `api-key` header, not the
    # `Authorization: Bearer` header the openai SDK sends by default for
    # api_key= — force the header it actually checks.
    openai_client = project_client.get_openai_client(
        api_key=api_key,
        default_headers={"api-key": api_key},
    )
    print("OpenAI client obtained.")

    print(f"\nCalling model '{model}' directly (reasoning effort {reasoning_effort}, low verbosity)...")
    response = openai_client.responses.create(
        model=model,
        input="Reply with the single word: Hello",
        reasoning={"effort": reasoning_effort},
        text={"verbosity": "low"},
    )

    print("\n--- Response ---")
    print(getattr(response, "output_text", None) or response)
    print("--- End response ---")

    print(f"\nSUCCESS: connected to Foundry with API-key auth and got a response from model '{model}'.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - this is a diagnostic script, print and exit non-zero
        print(f"\nFAILED: {type(exc).__name__}: {exc}")
        sys.exit(1)
