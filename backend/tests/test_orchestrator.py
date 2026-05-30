from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from apr_backend.core.settings import get_settings
from apr_backend.db.enums import RiskLevel, RuleType, Severity, TaskStatus
from apr_backend.db.models import ReviewRule, ReviewReport, ReviewTask
from apr_backend.services.diff_parser import parse_diff
from apr_backend.services.llm_adapter import LLMError, MockLLMProvider
from apr_backend.services.orchestrator import _build_prompt, run_review_orchestrator

MULTI_FILE_DIFF = """\
diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,6 +10,8 @@
 def login(user, password):
     if not user:
         return None
+    if not user.is_active:
+        return None
     token = generate_token(user)
     return token
diff --git a/tests/test_auth.py b/tests/test_auth.py
new file mode 100644
--- /dev/null
+++ b/tests/test_auth.py
@@ -0,0 +1,5 @@
+def test_login_active_user():
+    user = User(is_active=True)
+    result = login(user, "secret")
+    assert result is not None
"""


def _alembic_config(database_url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.fixture
def db_session_factory(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'orchestrator.db'}"
    monkeypatch.setenv("APR_DATABASE_URL", database_url)
    get_settings.cache_clear()
    command.upgrade(_alembic_config(database_url), "head")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
    get_settings.cache_clear()


def _create_task(session_factory, **overrides) -> ReviewTask:
    with session_factory() as session:
        task = ReviewTask(
            pr_title="Add token refresh",
            pr_description="Refresh expired tokens before retrying.",
            project_name="user-center",
            demo_owner="test-owner",
            diff_content=MULTI_FILE_DIFF,
            status=TaskStatus.pending,
        )
        for k, v in overrides.items():
            setattr(task, k, v)
        session.add(task)
        session.commit()
        task_id = task.id

    with session_factory() as session:
        return session.get(ReviewTask, task_id)


class TestSuccessfulReview:
    def test_transitions_pending_to_completed(self, db_session_factory, monkeypatch) -> None:
        monkeypatch.setattr(
            "apr_backend.services.orchestrator.create_llm_provider",
            lambda: MockLLMProvider(),
        )
        task = _create_task(db_session_factory)

        run_review_orchestrator(task.id, db_factory=db_session_factory)

        with db_session_factory() as session:
            reloaded = session.get(ReviewTask, task.id)
            assert reloaded.status == TaskStatus.completed
            assert reloaded.risk_level is not None

    def test_creates_report_with_summary_and_risk(self, db_session_factory, monkeypatch) -> None:
        monkeypatch.setattr(
            "apr_backend.services.orchestrator.create_llm_provider",
            lambda: MockLLMProvider(),
        )
        task = _create_task(db_session_factory)

        run_review_orchestrator(task.id, db_factory=db_session_factory)

        with db_session_factory() as session:
            report = session.scalar(select(ReviewReport).where(ReviewReport.task_id == task.id))
            assert report is not None
            assert len(report.summary) > 0
            assert report.risk_level in (RiskLevel.low, RiskLevel.medium, RiskLevel.high)
            assert isinstance(report.risk_reasons, list)

    def test_persists_issues(self, db_session_factory, monkeypatch) -> None:
        monkeypatch.setattr(
            "apr_backend.services.orchestrator.create_llm_provider",
            lambda: MockLLMProvider(),
        )
        task = _create_task(db_session_factory)

        run_review_orchestrator(task.id, db_factory=db_session_factory)

        with db_session_factory() as session:
            reloaded = session.get(ReviewTask, task.id)
            assert reloaded.status == TaskStatus.completed
            assert reloaded.issue_count > 0


class TestLLMFailure:
    def test_marks_task_as_failed_on_llm_error(self, db_session_factory, monkeypatch) -> None:
        class FailingProvider:
            def generate_review(self, _prompt):
                raise LLMError("simulated failure")

        monkeypatch.setattr(
            "apr_backend.services.orchestrator.create_llm_provider",
            lambda: FailingProvider(),
        )
        task = _create_task(db_session_factory)

        run_review_orchestrator(task.id, db_factory=db_session_factory)

        with db_session_factory() as session:
            reloaded = session.get(ReviewTask, task.id)
            assert reloaded.status == TaskStatus.failed
            assert reloaded.error_message is not None

    def test_failure_preserves_error_message(self, db_session_factory, monkeypatch) -> None:
        class FailingProvider:
            def generate_review(self, _prompt):
                raise LLMError("simulated failure")

        monkeypatch.setattr(
            "apr_backend.services.orchestrator.create_llm_provider",
            lambda: FailingProvider(),
        )
        task = _create_task(db_session_factory)

        run_review_orchestrator(task.id, db_factory=db_session_factory)

        with db_session_factory() as session:
            reloaded = session.get(ReviewTask, task.id)
            assert "LLM" in reloaded.error_message


class TestRerun:
    def test_rerun_clears_previous_failure(self, db_session_factory, monkeypatch) -> None:
        class FailingThenOk:
            def __init__(self):
                self.calls = 0

            def generate_review(self, _prompt):
                self.calls += 1
                if self.calls == 1:
                    raise LLMError("first fail")
                return MockLLMProvider().generate_review(_prompt)

        provider = FailingThenOk()
        monkeypatch.setattr(
            "apr_backend.services.orchestrator.create_llm_provider",
            lambda: provider,
        )
        task = _create_task(db_session_factory)

        run_review_orchestrator(task.id, db_factory=db_session_factory)
        with db_session_factory() as session:
            assert session.get(ReviewTask, task.id).status == TaskStatus.failed

        task = _create_task(db_session_factory)
        run_review_orchestrator(task.id, db_factory=db_session_factory)

        with db_session_factory() as session:
            reloaded = session.get(ReviewTask, task.id)
            assert reloaded.status == TaskStatus.completed


class TestInvalidAIOutput:
    def test_normalizes_invalid_enum_values(self, db_session_factory, monkeypatch) -> None:
        class BadOutputProvider:
            def generate_review(self, _prompt):
                return {
                    "summary": {"purpose": "test"},
                    "risk": {"level": "critical", "reasons": 42},
                    "issues": [
                        {
                            "title": "Issue",
                            "type": "imaginary_type",
                            "severity": "fatal",
                            "description": "desc",
                            "suggestion": "fix it",
                            "confidence": "sure",
                            "matched_rule_ids": ["nonexistent"],
                        }
                    ],
                }

        monkeypatch.setattr(
            "apr_backend.services.orchestrator.create_llm_provider",
            lambda: BadOutputProvider(),
        )
        task = _create_task(db_session_factory)

        run_review_orchestrator(task.id, db_factory=db_session_factory)

        with db_session_factory() as session:
            reloaded = session.get(ReviewTask, task.id)
            assert reloaded.status == TaskStatus.completed
            report = session.scalar(select(ReviewReport).where(ReviewReport.task_id == task.id))
            assert report.risk_level in (RiskLevel.low, RiskLevel.medium, RiskLevel.high)

    def test_missing_fields_complete_safely(self, db_session_factory, monkeypatch) -> None:
        class MinimalProvider:
            def generate_review(self, _prompt):
                return {}

        monkeypatch.setattr(
            "apr_backend.services.orchestrator.create_llm_provider",
            lambda: MinimalProvider(),
        )
        task = _create_task(db_session_factory)

        run_review_orchestrator(task.id, db_factory=db_session_factory)

        with db_session_factory() as session:
            reloaded = session.get(ReviewTask, task.id)
            assert reloaded.status == TaskStatus.completed


class TestRuleLoading:
    def test_loads_only_enabled_rules(self, db_session_factory, monkeypatch) -> None:
        with db_session_factory() as session:
            session.add_all([
                ReviewRule(name="Enabled", description="E", rule_type=RuleType.style, severity=Severity.low, enabled=True, demo_owner="test-owner"),
                ReviewRule(name="Disabled", description="D", rule_type=RuleType.style, severity=Severity.low, enabled=False, demo_owner="test-owner"),
            ])
            session.commit()

        monkeypatch.setattr(
            "apr_backend.services.orchestrator.create_llm_provider",
            lambda: MockLLMProvider(),
        )
        task = _create_task(db_session_factory)

        run_review_orchestrator(task.id, db_factory=db_session_factory)

        with db_session_factory() as session:
            reloaded = session.get(ReviewTask, task.id)
            assert reloaded.status == TaskStatus.completed


class TestSystemPrompt:
    def test_uses_custom_system_prompt_when_configured(self, db_session_factory, monkeypatch) -> None:
        monkeypatch.setattr(
            "apr_backend.services.orchestrator.load_llm_config",
            lambda: {
                "active_provider": "openai",
                "mock_enabled": False,
                "timeout": 60,
                "system_prompt": "Custom system prompt for test.",
                "openai": {"base_uri": "", "api_key": "sk-key", "model": ""},
                "anthropic": {"base_uri": "", "api_key": None, "model": ""},
            },
        )
        task = _create_task(db_session_factory)
        parsed = parse_diff(task.diff_content)
        prompt = _build_prompt(task, parsed, [], [])
        assert "Custom system prompt for test." in prompt
        assert "You are an AI PR Review assistant" not in prompt

    def test_falls_back_to_default_when_system_prompt_empty(self, db_session_factory, monkeypatch) -> None:
        monkeypatch.setattr(
            "apr_backend.services.orchestrator.load_llm_config",
            lambda: {
                "active_provider": "openai",
                "mock_enabled": False,
                "timeout": 60,
                "system_prompt": "",
                "openai": {"base_uri": "", "api_key": "sk-key", "model": ""},
                "anthropic": {"base_uri": "", "api_key": None, "model": ""},
            },
        )
        task = _create_task(db_session_factory)
        parsed = parse_diff(task.diff_content)
        prompt = _build_prompt(task, parsed, [], [])
        assert "You are an AI PR Review assistant" in prompt
