from pathlib import Path

from app.core.config import Settings
from app.db.models import Case
from app.integrations.llm import ProviderLLMClient
from app.main import _OfflineLLM, _ServiceState


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "database_url": f"sqlite:///{tmp_path / 'runtime.db'}",
        "storage_dir": tmp_path / "storage",
    }
    values.update(overrides)
    return Settings(**values)


def _runtime_llm(state: _ServiceState):
    session = state.sessions()
    try:
        case = Case(language="en", channel="web")
        session.add(case)
        session.commit()
        return state._runtime(session, str(case.id)).llm
    finally:
        session.close()


def test_runtime_uses_offline_llm_without_provider_endpoint(tmp_path: Path) -> None:
    state = _ServiceState(_settings(tmp_path))
    try:
        llm = _runtime_llm(state)
        assert isinstance(llm, _OfflineLLM)
    finally:
        state.engine.dispose()


def test_runtime_uses_configured_lm_studio_model_without_api_key(tmp_path: Path) -> None:
    state = _ServiceState(
        _settings(
            tmp_path,
            llm_provider="lm_studio",
            llm_api_key="",
            llm_model="dheeraj013/adhikaar-llama3.1-8b-fact-extractor-GGUF",
            llm_base_url="http://127.0.0.1:1234/v1",
        )
    )
    try:
        llm = _runtime_llm(state)
        assert isinstance(llm, ProviderLLMClient)
        assert llm.provider == "lm_studio"
        assert llm.api_key == ""
        assert llm.model == "dheeraj013/adhikaar-llama3.1-8b-fact-extractor-GGUF"
        assert llm.base_url == "http://127.0.0.1:1234/v1"
        assert llm.demo_mode == "live"
    finally:
        state.engine.dispose()
