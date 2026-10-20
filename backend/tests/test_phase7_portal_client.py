from __future__ import annotations

import httpx
from app.integrations.portal_client import PortalClient


def test_submit_and_verify_use_portal_contract_without_network() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"portal_ref": "MOCK-PORTAL-0001"}, request=request)
        return httpx.Response(
            200,
            json={"portal_ref": "MOCK-PORTAL-0001", "status": "accepted"},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    with PortalClient(
        "http://portal.test",
        client=httpx.Client(transport=transport),
    ) as portal:
        submitted = portal.submit("pm_kisan_mock", {"aadhaar_last4": "9012"})
        verified = portal.verify("MOCK-PORTAL-0001")

    assert submitted == {"ok": True, "portal_ref": "MOCK-PORTAL-0001"}
    assert verified == {
        "ok": True,
        "portal_ref": "MOCK-PORTAL-0001",
        "status": "accepted",
    }
    assert requests[0].url == "http://portal.test/applications"
    assert requests[0].content == (
        b'{"scheme_id":"pm_kisan_mock","payload_fields":{"aadhaar_last4":"9012"}}'
    )


def test_client_maps_validation_permanent_and_server_errors() -> None:
    responses = [
        httpx.Response(
            422,
            json={"errors": [{"field": "bank_ifsc", "code": "missing_field"}]},
        ),
        httpx.Response(409, json={"code": "duplicate_application", "message": "duplicate"}),
        httpx.Response(503, json={"message": "busy"}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        response = responses.pop(0)
        response.request = request
        return response

    with PortalClient(client=httpx.Client(transport=httpx.MockTransport(handler))) as portal:
        validation = portal.submit("pm_kisan_mock", {})
        permanent = portal.submit("pm_kisan_mock", {})
        transient = portal.submit("pm_kisan_mock", {})

    assert validation["error"] == {
        "kind": "validation",
        "code": "missing_field",
        "message": "MOCK portal rejected the application",
        "field": "bank_ifsc",
    }
    assert permanent["error"]["kind"] == "permanent"
    assert permanent["error"]["code"] == "duplicate_application"
    assert transient["error"]["kind"] == "transient"
    assert transient["error"]["code"] == "http_503"


def test_client_maps_http_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with PortalClient(client=httpx.Client(transport=httpx.MockTransport(handler))) as portal:
        result = portal.submit("pm_kisan_mock", {})

    assert result == {
        "ok": False,
        "error": {"kind": "timeout", "code": "timeout", "message": "MOCK portal request timed out"},
    }
