"""Render dashboard components offline with a local in-process API; no browser/network."""
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from app.config import Settings
from app.main import create_app


@pytest.mark.parametrize("page", ["Overview", "Documents", "RAG Playground", "Attack Lab",
                                  "Defense Comparison", "Runs & Reports"])
def test_dashboard_pages(tmp_path, page):
    with TestClient(create_app(Settings(data_dir=tmp_path, _env_file=None))) as client:
        lab = client.app.state.lab
        collection = lab.create_collection("Demo")
        lab.ingest(b"Returns are accepted within 7 days.", "policy.txt", collection["id"])
        def local_request(method, url, **kwargs):
            kwargs.pop("timeout", None)
            return client.request(method, url.replace("http://127.0.0.1:8000", ""), **kwargs)
        with patch("httpx.request", side_effect=local_request):
            app = AppTest.from_file(Path(__file__).resolve().parents[1] / "dashboard/streamlit_app.py", default_timeout=15).run()
            app.radio[0].set_value(page).run()
            assert not app.exception
            assert app.title[-1].value == "◈ RAGVanta" or any(t.value == page for t in app.title)


def test_dashboard_experiment_and_exports(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path, _env_file=None))) as client:
        def local_request(method, url, **kwargs):
            kwargs.pop("timeout", None)
            return client.request(method, url.replace("http://127.0.0.1:8000", ""), **kwargs)
        with patch("httpx.request", side_effect=local_request):
            app = AppTest.from_file(Path(__file__).resolve().parents[1] / "dashboard/streamlit_app.py", default_timeout=15).run()
            app.radio[0].set_value("Attack Lab").run()
            app.slider[0].set_value(2)
            app.button[0].click().run()
            assert not app.exception
            assert app.session_state["report"]["status"] == "completed"
            app.radio[0].set_value("Runs & Reports").run()
            assert not app.exception
            assert len(app.get("download_button")) == 2
