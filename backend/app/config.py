import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

# Load the repo-root .env. Real process env vars always take precedence.
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BASE_DIR.parent / ".env")

DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

# Azure AI Foundry — direct model calls only, same pattern telecom-assistant
# uses: a router/extraction LLM call classifies or extracts structured
# fields, then plain Python deterministically calls a REST API and (for
# order) templates the answer or (for warranty) synthesizes one grounded
# only in what that API actually returned. No Foundry "Agent" resource, no
# tool-calling loop, no File Search -- registering real function tools on a
# Foundry agent turned out to need a Portal step this environment can't
# automate, and for a small fixed set of lookups like these, direct calls
# are simpler, cheaper, faster, and fully unit-testable. Auth is API-key
# only (az login is blocked in this environment).
FOUNDRY_PROJECT_ENDPOINT = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "")
FOUNDRY_API_KEY = os.getenv("FOUNDRY_API_KEY", "")
# Available deployments in this Foundry project:
# gpt-5-mini, gpt-5.4-nano, and gpt-realtime-1.5. Keep gpt-5-mini as the
# default for text/vision quality; realtime voice is configured separately.
GAF_MODEL = os.getenv("GAF_MODEL", "gpt-5-mini")

# The Telecom-POC + GAF-POC Azure Function App (see ../telecom-poc-api/) --
# GAF_API_BASE_URL is scoped to /api/gaf/* by every caller; /api/* (telecom)
# is a separate, unrelated route group on the same Function App.
GAF_API_BASE_URL = os.getenv("GAF_API_BASE_URL", "")

# Where gaf_api_client's get_* functions read GAF data from: "local" reads
# the synthetic dataset under data/ on disk (see app/services/
# local_data_repository.py) -- no Azure Function App call, no network at
# all; "live" hits GAF_API_BASE_URL as before. Local is the default so the
# demo runs fully offline out of the box; switch to "live" to point back at
# the real Function App once one is deployed.
GAF_DATA_SOURCE = os.getenv("GAF_DATA_SOURCE", "local").strip().lower()
DATA_DIR = PROJECT_ROOT / "data"

FOUNDRY_CONFIGURED = bool(FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_API_KEY and (GAF_API_BASE_URL or GAF_DATA_SOURCE == "local"))

# Realtime voice can use this Foundry project's gpt-realtime-1.5 deployment
# if the Azure OpenAI endpoint/key/deployment values below are set. Leaving
# them blank disables voice while chat/order/warranty continue to work.
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_REALTIME_DEPLOYMENT = os.getenv("AZURE_OPENAI_REALTIME_DEPLOYMENT", "")
AZURE_OPENAI_TRANSCRIBE_DEPLOYMENT = os.getenv("AZURE_OPENAI_TRANSCRIBE_DEPLOYMENT", "")
REALTIME_NOISE_REDUCTION_MODE = os.getenv("REALTIME_NOISE_REDUCTION_MODE", "far_field")
REALTIME_VAD_THRESHOLD = float(os.getenv("REALTIME_VAD_THRESHOLD", "0.7"))
VOICE_CONFIGURED = bool(AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY and AZURE_OPENAI_REALTIME_DEPLOYMENT)

# Self-hosted coturn TURN relay (see ../../deploy/setup_vm.sh) -- same VM,
# same coturn instance telecom-assistant already runs; empty secret just
# disables it and voice falls back to STUN-only, no error either way.
TURN_SHARED_SECRET = os.getenv("TURN_SHARED_SECRET", "")
TURN_DOMAIN = os.getenv("TURN_DOMAIN", "")

CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
