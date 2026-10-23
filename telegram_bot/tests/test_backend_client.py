import asyncio

import httpx

from app.backend_client import BackendClient


def run(coro):
    return asyncio.run(coro)


def test_get_schemes_reads_backend_catalog_and_sends_service_token():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "scheme_id": "pm_kisan_mock",
                    "name": "PM-Kisan (MOCK, simplified)",
                    "benefit": "MOCK benefit",
                    "required_documents": ["land_record"],
                }
            ],
        )

    client = BackendClient(
        "http://backend.test/",
        "service-secret",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    schemes = run(client.get_schemes())

    assert schemes[0]["scheme_id"] == "pm_kisan_mock"
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/schemes"
    assert requests[0].headers["X-Service-Token"] == "service-secret"
    run(client.aclose())


def test_latest_case_reads_terminal_case_for_status_recovery():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "case": {
                    "case_id": "case-1",
                    "status": "COMPLETED",
                    "decision_summary": {"outcome": "ELIGIBLE"},
                }
            },
        )

    client = BackendClient(
        "http://backend.test/",
        "service-secret",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    case = run(client.latest_case("chat-1"))

    assert case and case["status"] == "COMPLETED"
    assert requests[0].url.path == "/cases/latest"
    assert requests[0].url.params["channel"] == "telegram"
    assert requests[0].url.params["channel_ref"] == "chat-1"
    run(client.aclose())
