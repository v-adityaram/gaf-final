"""gaf_api_client transport tests. The "live" transport is exercised against
a faked httpx.AsyncClient (no pytest-asyncio needed -- asyncio.run around
each call) to prove params are forwarded and HTTP failures degrade to a
structured ToolResult; the "local" transport is proven to never touch
httpx at all."""

import asyncio

import httpx
import pytest

from app.services import gaf_api_client


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.com")
            response = httpx.Response(self.status_code, request=request, json=self._json_data)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self):
        return self._json_data


class FakeAsyncClient:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.last_url = None
        self.last_params = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        self.last_url = url
        self.last_params = params
        if self._exc:
            raise self._exc
        return self._response


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(gaf_api_client, "DATA_SOURCE", "live")
    monkeypatch.setattr(gaf_api_client, "GAF_API_BASE_URL", "https://fn.example")


def test_live_forwards_query_params_and_drops_empty_ones(live, monkeypatch):
    fake = FakeAsyncClient(response=FakeResponse(200, {"data": {"contractors": []}}))
    monkeypatch.setattr(gaf_api_client.httpx, "AsyncClient", lambda **kwargs: fake)

    result = asyncio.run(gaf_api_client.get_contractors(zip_code="30061", city=None, radius_miles=10, limit=5, min_tier="master_elite"))

    assert result.success is True
    assert result.data == {"data": {"contractors": []}}
    assert fake.last_url == "https://fn.example/api/gaf/contractors"
    assert fake.last_params == {"zip": "30061", "radius": "10", "limit": "5", "minTier": "master_elite"}

    asyncio.run(gaf_api_client.get_products())
    assert fake.last_params == {}


def test_live_404_maps_to_gaf_api_not_found_with_the_body(live, monkeypatch):
    fake = FakeAsyncClient(response=FakeResponse(404, {"supportMessage": "Unknown sku 'NOPE'."}))
    monkeypatch.setattr(gaf_api_client.httpx, "AsyncClient", lambda **kwargs: fake)

    result = asyncio.run(gaf_api_client.get_products(sku="NOPE"))

    assert result.success is False
    assert result.error == "gaf_api_not_found"
    assert result.status_code == 404
    assert result.data == {"supportMessage": "Unknown sku 'NOPE'."}


def test_live_400_maps_to_bad_request(live, monkeypatch):
    fake = FakeAsyncClient(response=FakeResponse(400, {"supportMessage": "sku required"}))
    monkeypatch.setattr(gaf_api_client.httpx, "AsyncClient", lambda **kwargs: fake)
    result = asyncio.run(gaf_api_client.get_inventory())
    assert (result.success, result.error, result.status_code) == (False, "gaf_api_bad_request", 400)


@pytest.mark.parametrize("exc,error", [(httpx.TimeoutException("t"), "gaf_api_timeout"), (httpx.ConnectError("refused"), "gaf_api_unreachable")])
def test_live_network_failures_are_clean_results_not_exceptions(live, monkeypatch, exc, error):
    monkeypatch.setattr(gaf_api_client.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient(exc=exc))
    result = asyncio.run(gaf_api_client.get_escalation_rules())
    assert result.success is False and result.error == error


def test_local_transport_never_touches_httpx(monkeypatch):
    monkeypatch.setattr(gaf_api_client, "DATA_SOURCE", "local")

    def fail(**kwargs):
        raise AssertionError("local mode must not open an HTTP client")

    monkeypatch.setattr(gaf_api_client.httpx, "AsyncClient", fail)
    result = asyncio.run(gaf_api_client.get_customers(account_id="ACC-1001"))
    assert result.success is True
    assert result.data["data"]["customers"][0]["tradeName"] == "Sunshine Roofing Supply"
