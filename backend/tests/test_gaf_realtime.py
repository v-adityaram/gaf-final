"""Realtime voice session minting against a fake httpx client -- no live
Azure OpenAI resource needed."""

import asyncio

import httpx
import pytest

from app.services import gaf_realtime


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setattr(gaf_realtime, "AZURE_OPENAI_ENDPOINT", "https://example-realtime.openai.azure.com")
    monkeypatch.setattr(gaf_realtime, "AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(gaf_realtime, "AZURE_OPENAI_REALTIME_DEPLOYMENT", "gpt-realtime-test")


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://example.com")
            raise httpx.HTTPStatusError("error", request=request, response=httpx.Response(self.status_code, request=request))

    def json(self):
        return self._json_data


class FakeAsyncClient:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.captured = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        self.captured = {"url": url, "payload": json, "headers": headers}
        if self._exc:
            raise self._exc
        return self._response


def test_success_mints_a_token_and_defers_transcription_to_post_connect(monkeypatch):
    monkeypatch.setattr(gaf_realtime, "AZURE_OPENAI_TRANSCRIBE_DEPLOYMENT", "gpt-live-transcribe")
    fake = FakeAsyncClient(response=FakeResponse(200, {"value": "ephemeral-token-123"}))
    monkeypatch.setattr(gaf_realtime.httpx, "AsyncClient", lambda **kwargs: fake)

    result = asyncio.run(gaf_realtime.create_realtime_session())

    assert result.success is True and result.client_secret == "ephemeral-token-123"
    assert result.realtime_url.endswith("/realtime/calls")
    assert fake.captured["headers"]["api-key"] == "test-key"
    mint = fake.captured["payload"]["session"]
    assert "transcription" not in mint["audio"]["input"]
    assert mint["audio"]["input"]["turn_detection"]["create_response"] is True
    update = result.post_connect_update["session"]
    assert update["audio"]["input"]["transcription"] == {"model": "gpt-live-transcribe"}
    assert update["audio"]["input"]["turn_detection"]["create_response"] is True
    assert update["instructions"] == gaf_realtime.INSTRUCTIONS and update["tools"] == gaf_realtime.REALTIME_TOOLS


def test_post_connect_update_is_none_when_transcription_unconfigured(monkeypatch):
    monkeypatch.setattr(gaf_realtime, "AZURE_OPENAI_TRANSCRIBE_DEPLOYMENT", "")
    monkeypatch.setattr(gaf_realtime.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient(response=FakeResponse(200, {"value": "tok"})))
    assert asyncio.run(gaf_realtime.create_realtime_session()).post_connect_update is None


def test_failures_are_structured_results(monkeypatch):
    for client, error in [
        (FakeAsyncClient(response=FakeResponse(200, {})), "realtime_session_invalid_response"),
        (FakeAsyncClient(exc=httpx.TimeoutException("timeout")), "realtime_session_timeout"),
        (FakeAsyncClient(response=FakeResponse(401)), "realtime_session_error"),
        (FakeAsyncClient(exc=httpx.ConnectError("refused")), "realtime_session_unreachable"),
    ]:
        monkeypatch.setattr(gaf_realtime.httpx, "AsyncClient", lambda c=client, **kwargs: c)
        result = asyncio.run(gaf_realtime.create_realtime_session())
        assert result.success is False and result.error == error, error


def test_not_configured_never_attempts_a_network_call(monkeypatch):
    def fail(**kwargs):
        raise AssertionError("must not attempt a network call when voice isn't configured")

    monkeypatch.setattr(gaf_realtime.httpx, "AsyncClient", fail)
    for missing in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_REALTIME_DEPLOYMENT"):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(gaf_realtime, missing, "")
            result = asyncio.run(gaf_realtime.create_realtime_session())
        assert result.success is False and result.error == "realtime_not_configured", missing


def test_every_realtime_tool_has_a_handler():
    assert {tool["name"] for tool in gaf_realtime.REALTIME_TOOLS} == {"handle_customer_request", "confirm_pending_order"}
