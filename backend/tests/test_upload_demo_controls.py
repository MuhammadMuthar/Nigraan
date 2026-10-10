"""Upload responsiveness, resource bounds and destructive demo-control permissions."""
from __future__ import annotations

import io
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest
from starlette.datastructures import UploadFile

from app.api.finance import upload_invoice
from app.config import Settings
from app.services.docreader import gemini, pipeline
from tests.conftest import login


def test_slow_extraction_does_not_block_other_requests(client, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    headers = login(client, "sana")

    def slow_reader(*args):
        entered.set()
        assert release.wait(timeout=8), "test did not release the document reader"
        return {"invoice_id": 123, "engine": "test-reader"}

    monkeypatch.setattr(pipeline, "read_and_store", slow_reader)
    with ThreadPoolExecutor(max_workers=2) as requests:
        upload = requests.submit(client.post, "/api/v1/invoices/upload", headers=headers,
                                 files={"file": ("test.pdf", b"test document", "application/pdf")})
        try:
            assert entered.wait(timeout=3), "document reader was never reached"
            health = requests.submit(client.get, "/health").result(timeout=2)
            assert health.status_code == 200
            assert not upload.done(), "health must respond while extraction is still running"
        finally:
            release.set()
        assert upload.result(timeout=3).status_code == 200


def test_upload_reads_only_limit_plus_one_byte(monkeypatch):
    limit = 8 * 1024 * 1024

    class TrackedFile(io.BytesIO):
        def read(self, size=-1):
            self.requested_size = size
            return super().read(size)

    document = TrackedFile(b"x" * (limit + 1024))
    monkeypatch.setattr(pipeline, "read_and_store", lambda *args: pytest.fail("oversized input must not be extracted"))
    from app.errors import ApiError

    with pytest.raises(ApiError) as raised:
        upload_invoice(UploadFile(file=document, filename="large.pdf"), db=None, user=None)
    assert document.requested_size == limit + 1
    assert document.tell() == limit + 1
    assert raised.value.status == 413


@pytest.mark.parametrize("who", ["sana", "kashif", "bilal"])
def test_demo_reset_is_owner_only(client, monkeypatch, who):
    from app.services import demo

    monkeypatch.setattr(demo, "reset", lambda: pytest.fail("a non-owner must never reset the database"))
    response = client.post("/api/v1/demo/reset", headers=login(client, who))
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_owner_can_reset_demo(client, monkeypatch):
    from app.services import demo

    called = []
    monkeypatch.setattr(demo, "reset", lambda: called.append(True) or {"reset": True})
    response = client.post("/api/v1/demo/reset", headers=login(client, "rashid"))
    assert response.status_code == 200
    assert response.json() == {"reset": True}
    assert called == [True]


def test_demo_reset_requires_sign_in(client, monkeypatch):
    from app.services import demo

    monkeypatch.setattr(demo, "reset", lambda: pytest.fail("anonymous callers must never reset the database"))
    response = client.post("/api/v1/demo/reset")
    assert response.status_code == 401


def test_gemini_timeout_uses_eight_second_default_and_falls_back(monkeypatch):
    settings = Settings(gemini_api_key="test-only-key")
    monkeypatch.setattr(gemini, "get_settings", lambda: settings)
    observed = []

    def timeout(*args, **kwargs):
        observed.append(kwargs["timeout"])
        raise httpx.ReadTimeout("test timeout")

    monkeypatch.setattr(gemini.httpx, "post", timeout)
    with pytest.raises(gemini.GeminiUnavailable, match="ReadTimeout"):
        gemini.extract(None, b"test document", "application/pdf")
    assert observed == [8.0, 8.0]  # The existing single retry remains available.


def test_gemini_success_keeps_schema_output_and_cache_flag(monkeypatch):
    settings = Settings(gemini_api_key="test-only-key")
    monkeypatch.setattr(gemini, "get_settings", lambda: settings)
    expected = {"invoice_no": "EXTRACT-001", "total": 1180.0}
    monkeypatch.setattr(gemini.httpx, "post", lambda *args, **kwargs: SimpleNamespace(
        status_code=200,
        json=lambda: {"candidates": [{"content": {"parts": [{"text": '{"invoice_no":"EXTRACT-001","total":1180.0}'}]}}]},
    ))
    extracted, cached = gemini.extract(None, b"test document", "application/pdf")
    assert extracted == expected
    assert cached is False
