"""Tests for the self-healing module (healing/)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mcp_tap.models import (
    CandidateFix,
    ConnectionTestResult,
    DiagnosisResult,
    ErrorCategory,
    HealingAttempt,
    HealingResult,
    ServerConfig,
)

# ─── Helpers ──────────────────────────────────────────────────


def _failed_connection(
    error: str,
    server_name: str = "test-server",
) -> ConnectionTestResult:
    """Build a failed ConnectionTestResult with a given error message."""
    return ConnectionTestResult(
        success=False,
        server_name=server_name,
        error=error,
    )


def _ok_connection(
    server_name: str = "test-server",
    tools: list[str] | None = None,
) -> ConnectionTestResult:
    return ConnectionTestResult(
        success=True,
        server_name=server_name,
        tools_discovered=tools or ["tool_a", "tool_b"],
    )


def _server_config(
    command: str = "npx",
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> ServerConfig:
    return ServerConfig(
        command=command,
        args=args or ["-y", "@modelcontextprotocol/server-postgres"],
        env=env or {},
    )


def _diagnosis(
    category: ErrorCategory = ErrorCategory.COMMAND_NOT_FOUND,
    original_error: str = "Command not found: npx",
    explanation: str = "The command 'npx' was not found on your system.",
    suggested_fix: str = "Install Node.js to get npx.",
    confidence: float = 0.9,
) -> DiagnosisResult:
    return DiagnosisResult(
        category=category,
        original_error=original_error,
        explanation=explanation,
        suggested_fix=suggested_fix,
        confidence=confidence,
    )


def _healing_attempt(
    diagnosis: DiagnosisResult | None = None,
    fix: CandidateFix | None = None,
    success: bool = False,
) -> HealingAttempt:
    return HealingAttempt(
        diagnosis=diagnosis or _diagnosis(),
        fix_applied=fix or CandidateFix(
            description="test", requires_user_action=False,
        ),
        success=success,
    )


# ── Shared parametrize data for classifier structural tests ───

_REPR_ERRORS = (
    "Command not found: npx",
    "Connection refused",
    "Server did not respond within 15s",
    "401 Unauthorized",
    "SLACK_BOT_TOKEN is not set",
    "Permission denied",
    "some random unknown error",
)
_REPR_IDS = (
    "cmd_not_found",
    "conn_refused",
    "timeout",
    "auth",
    "env_var",
    "permission",
    "unknown",
)


# ═══════════════════════════════════════════════════════════════
# 1. Classifier Tests
# ═══════════════════════════════════════════════════════════════


class TestClassifier:
    """Tests for healing/classifier.py -- classify_error()."""

    # ── Parametrized category detection ───────────────────────

    @pytest.mark.parametrize(
        ("error_msg", "expected_category"),
        [
            # COMMAND_NOT_FOUND
            (
                "Command not found: npx. Is the package installed?",
                ErrorCategory.COMMAND_NOT_FOUND,
            ),
            (
                "FileNotFoundError: npx",
                ErrorCategory.COMMAND_NOT_FOUND,
            ),
            # CONNECTION_REFUSED
            (
                "Connection refused",
                ErrorCategory.CONNECTION_REFUSED,
            ),
            (
                "ECONNREFUSED",
                ErrorCategory.CONNECTION_REFUSED,
            ),
            # TIMEOUT
            (
                "Server did not respond within 15s",
                ErrorCategory.TIMEOUT,
            ),
            (
                "TimeoutError",
                ErrorCategory.TIMEOUT,
            ),
            # AUTH_FAILED
            (
                "401 Unauthorized",
                ErrorCategory.AUTH_FAILED,
            ),
            (
                "403 Forbidden",
                ErrorCategory.AUTH_FAILED,
            ),
            (
                "authentication failed",
                ErrorCategory.AUTH_FAILED,
            ),
            # MISSING_ENV_VAR -- must contain uppercase env-var-shaped token
            (
                "SLACK_BOT_TOKEN is not set",
                ErrorCategory.MISSING_ENV_VAR,
            ),
            (
                "required environment variable DATABASE_URL missing",
                ErrorCategory.MISSING_ENV_VAR,
            ),
            # PERMISSION_DENIED
            (
                "Permission denied",
                ErrorCategory.PERMISSION_DENIED,
            ),
            (
                "EACCES",
                ErrorCategory.PERMISSION_DENIED,
            ),
            # UNKNOWN
            (
                "some random unknown error",
                ErrorCategory.UNKNOWN,
            ),
        ],
        ids=[
            "cmd_not_found-explicit",
            "cmd_not_found-FileNotFoundError",
            "conn_refused-explicit",
            "conn_refused-ECONNREFUSED",
            "timeout-did_not_respond",
            "timeout-TimeoutError",
            "auth-401",
            "auth-403",
            "auth-authentication_failed",
            "env_var-not_set",
            "env_var-required_missing",
            "permission-denied",
            "permission-EACCES",
            "unknown-random",
        ],
    )
    def test_classify_error_categories(
        self,
        error_msg: str,
        expected_category: ErrorCategory,
    ):
        """Should map error messages to the correct ErrorCategory."""
        from mcp_tap.healing.classifier import classify_error

        error = _failed_connection(error_msg)
        diagnosis = classify_error(error)

        assert diagnosis.category == expected_category
        assert diagnosis.original_error == error_msg

    # ── Structural invariants ─────────────────────────────────

    @pytest.mark.parametrize(
        "error_msg", _REPR_ERRORS, ids=_REPR_IDS,
    )
    def test_explanation_is_non_empty(self, error_msg: str):
        """Should always provide a non-empty explanation."""
        from mcp_tap.healing.classifier import classify_error

        diagnosis = classify_error(_failed_connection(error_msg))
        assert isinstance(diagnosis.explanation, str)
        assert len(diagnosis.explanation) > 0

    @pytest.mark.parametrize("error_msg", _REPR_ERRORS, ids=_REPR_IDS)
    def test_suggested_fix_is_non_empty(self, error_msg: str):
        """Should always provide a non-empty suggested_fix."""
        from mcp_tap.healing.classifier import classify_error

        diagnosis = classify_error(_failed_connection(error_msg))
        assert isinstance(diagnosis.suggested_fix, str)
        assert len(diagnosis.suggested_fix) > 0

    @pytest.mark.parametrize("error_msg", _REPR_ERRORS, ids=_REPR_IDS)
    def test_confidence_in_valid_range(self, error_msg: str):
        """Should return confidence between 0.0 and 1.0 inclusive."""
        from mcp_tap.healing.classifier import classify_error

        diagnosis = classify_error(_failed_connection(error_msg))
        assert 0.0 <= diagnosis.confidence <= 1.0

    # ── Edge cases ────────────────────────────────────────────

    def test_empty_error_message_returns_unknown(self):
        """Should classify empty error as UNKNOWN."""
        from mcp_tap.healing.classifier import classify_error

        diagnosis = classify_error(_failed_connection(""))
        assert diagnosis.category == ErrorCategory.UNKNOWN

    def test_case_insensitive_matching(self):
        """Should match error patterns regardless of case."""
        from mcp_tap.healing.classifier import classify_error

        diagnosis = classify_error(
            _failed_connection("command not found: uvx"),
        )
        assert diagnosis.category == ErrorCategory.COMMAND_NOT_FOUND

    def test_error_with_mixed_patterns_picks_first_match(self):
        """When error contains multiple patterns, should pick a category.

        The classifier checks patterns in priority order, so a message with
        both timeout and connection patterns should match one of them.
        """
        from mcp_tap.healing.classifier import classify_error

        error = "TimeoutError: Connection refused after 15s"
        diagnosis = classify_error(_failed_connection(error))
        assert diagnosis.category in (
            ErrorCategory.TIMEOUT,
            ErrorCategory.CONNECTION_REFUSED,
        )

    def test_original_error_preserved(self):
        """Should store the original error text in the diagnosis."""
        from mcp_tap.healing.classifier import classify_error

        msg = "FileNotFoundError: /usr/bin/docker"
        diagnosis = classify_error(_failed_connection(msg))
        assert diagnosis.original_error == msg

    def test_diagnosis_result_is_frozen(self):
        """DiagnosisResult should be a frozen dataclass."""
        diag = _diagnosis()
        with pytest.raises(AttributeError):
            diag.category = ErrorCategory.UNKNOWN  # type: ignore[misc]

    def test_enoent_classified_as_command_not_found(self):
        """ENOENT error code should map to COMMAND_NOT_FOUND."""
        from mcp_tap.healing.classifier import classify_error

        diagnosis = classify_error(
            _failed_connection("ENOENT: /usr/bin/docker"),
        )
        assert diagnosis.category == ErrorCategory.COMMAND_NOT_FOUND

    def test_missing_keyword_without_env_context_is_not_env_var(self):
        """A 'missing' message without an env var name token should NOT
        be classified as MISSING_ENV_VAR.
        """
        from mcp_tap.healing.classifier import classify_error

        diagnosis = classify_error(
            _failed_connection("missing dependency: libfoo.so"),
        )
        assert diagnosis.category != ErrorCategory.MISSING_ENV_VAR


# ═══════════════════════════════════════════════════════════════
# 2. Fixer Tests
# ═══════════════════════════════════════════════════════════════


class TestFixer:
    """Tests for healing/fixer.py -- generate_fix()."""

    # ── COMMAND_NOT_FOUND ─────────────────────────────────────

    @patch(
        "mcp_tap.healing.fixer.shutil.which",
        return_value="/usr/local/bin/npx",
    )
    def test_command_not_found_resolves_path(self, _mock_which):
        """Should resolve full path for command when found on system."""
        from mcp_tap.healing.fixer import generate_fix

        diag = _diagnosis(
            category=ErrorCategory.COMMAND_NOT_FOUND,
            original_error="Command not found: npx",
        )
        config = _server_config(command="npx")
        fix = generate_fix(diag, config)

        assert isinstance(fix, CandidateFix)
        assert fix.requires_user_action is False
        assert fix.new_config is not None
        assert fix.new_config.command == "/usr/local/bin/npx"

    @patch("mcp_tap.healing.fixer.shutil.which", return_value=None)
    def test_command_not_found_no_resolution(self, _mock_which):
        """Should require user action when command cannot be found."""
        from mcp_tap.healing.fixer import generate_fix

        diag = _diagnosis(
            category=ErrorCategory.COMMAND_NOT_FOUND,
            original_error="Command not found: nonexistent-tool",
        )
        config = _server_config(command="nonexistent-tool")
        fix = generate_fix(diag, config)

        assert isinstance(fix, CandidateFix)
        assert fix.requires_user_action is True

    @patch(
        "mcp_tap.healing.fixer.shutil.which",
        return_value="/usr/local/bin/npx",
    )
    def test_command_not_found_preserves_args(self, _mock_which):
        """Should preserve original args when resolving command path."""
        from mcp_tap.healing.fixer import generate_fix

        original_args = ["-y", "@foo/bar-server"]
        diag = _diagnosis(category=ErrorCategory.COMMAND_NOT_FOUND)
        config = _server_config(command="npx", args=original_args)
        fix = generate_fix(diag, config)

        assert fix.new_config is not None
        assert fix.new_config.args == original_args

    # ── TIMEOUT ───────────────────────────────────────────────

    def test_timeout_suggests_retry(self):
        """Should suggest retry with no user action required."""
        from mcp_tap.healing.fixer import generate_fix

        diag = _diagnosis(
            category=ErrorCategory.TIMEOUT,
            original_error="Server did not respond within 15s",
        )
        fix = generate_fix(diag, _server_config())

        assert isinstance(fix, CandidateFix)
        assert fix.requires_user_action is False
        assert fix.description != ""
        assert fix.new_config is not None

    # ── AUTH_FAILED ───────────────────────────────────────────

    def test_auth_failed_requires_user_action(self):
        """Should require user action for auth failures."""
        from mcp_tap.healing.fixer import generate_fix

        diag = _diagnosis(
            category=ErrorCategory.AUTH_FAILED,
            original_error="401 Unauthorized",
        )
        fix = generate_fix(diag, _server_config())

        assert fix.requires_user_action is True
        assert fix.env_var_hint is not None and fix.env_var_hint != ""

    # ── MISSING_ENV_VAR ───────────────────────────────────────

    def test_missing_env_var_requires_user_action(self):
        """Should require user action and provide env_var_hint."""
        from mcp_tap.healing.fixer import generate_fix

        diag = _diagnosis(
            category=ErrorCategory.MISSING_ENV_VAR,
            original_error="SLACK_BOT_TOKEN is not set",
            suggested_fix="Set SLACK_BOT_TOKEN in the server env config.",
        )
        fix = generate_fix(diag, _server_config())

        assert fix.requires_user_action is True
        assert fix.env_var_hint is not None and fix.env_var_hint != ""

    # ── CONNECTION_REFUSED ────────────────────────────────────

    def test_connection_refused_requires_user_action(self):
        """Should require user action for connection refused."""
        from mcp_tap.healing.fixer import generate_fix

        diag = _diagnosis(
            category=ErrorCategory.CONNECTION_REFUSED,
            original_error="Connection refused",
        )
        fix = generate_fix(diag, _server_config())
        assert fix.requires_user_action is True

    # ── PERMISSION_DENIED ─────────────────────────────────────

    def test_permission_denied_requires_user_action(self):
        """Should require user action for permission errors."""
        from mcp_tap.healing.fixer import generate_fix

        diag = _diagnosis(
            category=ErrorCategory.PERMISSION_DENIED,
            original_error="Permission denied",
        )
        fix = generate_fix(diag, _server_config())
        assert fix.requires_user_action is True

    # ── UNKNOWN ───────────────────────────────────────────────

    def test_unknown_requires_user_action(self):
        """Should require user action for unrecognized errors."""
        from mcp_tap.healing.fixer import generate_fix

        diag = _diagnosis(
            category=ErrorCategory.UNKNOWN,
            original_error="some random unknown error",
        )
        fix = generate_fix(diag, _server_config())
        assert fix.requires_user_action is True

    # ── TRANSPORT_MISMATCH ────────────────────────────────────

    def test_transport_mismatch_adds_stdio_flag(self):
        """Should add --stdio flag when not present."""
        from mcp_tap.healing.fixer import generate_fix

        diag = _diagnosis(
            category=ErrorCategory.TRANSPORT_MISMATCH,
            original_error="Transport mismatch",
        )
        config = _server_config(args=["-y", "some-server"])
        fix = generate_fix(diag, config)

        assert fix.requires_user_action is False
        assert fix.new_config is not None
        assert "--stdio" in fix.new_config.args

    def test_transport_mismatch_already_has_stdio(self):
        """Should require user action when --stdio already present."""
        from mcp_tap.healing.fixer import generate_fix

        diag = _diagnosis(
            category=ErrorCategory.TRANSPORT_MISMATCH,
            original_error="Transport mismatch",
        )
        config = _server_config(args=["-y", "srv", "--stdio"])
        fix = generate_fix(diag, config)
        assert fix.requires_user_action is True

    # ── Structural invariants ─────────────────────────────────

    @pytest.mark.parametrize(
        "category",
        list(ErrorCategory),
        ids=[c.name for c in ErrorCategory],
    )
    def test_description_always_non_empty(self, category: ErrorCategory):
        """Should always produce a non-empty description."""
        from mcp_tap.healing.fixer import generate_fix

        diag = _diagnosis(
            category=category,
            original_error=f"Error for {category}",
        )
        with patch(
            "mcp_tap.healing.fixer.shutil.which",
            return_value="/usr/bin/npx",
        ):
            fix = generate_fix(diag, _server_config())

        assert isinstance(fix.description, str)
        assert len(fix.description) > 0

    def test_candidate_fix_is_frozen(self):
        """CandidateFix should be a frozen dataclass."""
        fix = CandidateFix(
            description="Test fix", requires_user_action=False,
        )
        with pytest.raises(AttributeError):
            fix.description = "changed"  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════
# 3. Retry Loop Tests
# ═══════════════════════════════════════════════════════════════


class TestRetryLoop:
    """Tests for healing/retry.py -- heal_and_retry()."""

    # ── Happy path: fix succeeds on first attempt ─────────────

    @patch("mcp_tap.healing.retry.test_server_connection")
    @patch("mcp_tap.healing.retry.generate_fix")
    @patch("mcp_tap.healing.retry.classify_error")
    async def test_fix_succeeds_first_attempt(
        self, mock_classify, mock_generate_fix, mock_test_conn,
    ):
        """Should return fixed=True with 1 attempt when fix works."""
        initial_error = _failed_connection("Command not found: npx")
        config = _server_config()

        mock_classify.return_value = _diagnosis(
            category=ErrorCategory.COMMAND_NOT_FOUND,
        )
        mock_generate_fix.return_value = CandidateFix(
            description="Resolved npx to full path",
            requires_user_action=False,
            new_config=ServerConfig(
                command="/usr/local/bin/npx", args=config.args,
            ),
        )
        mock_test_conn.return_value = _ok_connection()

        from mcp_tap.healing.retry import heal_and_retry

        result = await heal_and_retry(
            "test-server", config, initial_error, max_attempts=3,
        )

        assert isinstance(result, HealingResult)
        assert result.fixed is True
        assert len(result.attempts) == 1
        mock_test_conn.assert_awaited_once()

    # ── Fix succeeds on second attempt ────────────────────────

    @patch("mcp_tap.healing.retry.test_server_connection")
    @patch("mcp_tap.healing.retry.generate_fix")
    @patch("mcp_tap.healing.retry.classify_error")
    async def test_fix_succeeds_second_attempt(
        self, mock_classify, mock_generate_fix, mock_test_conn,
    ):
        """Should return fixed=True with 2 attempts."""
        initial_error = _failed_connection(
            "Server did not respond within 15s",
        )
        config = _server_config()

        mock_classify.return_value = _diagnosis(
            category=ErrorCategory.TIMEOUT,
        )
        mock_generate_fix.return_value = CandidateFix(
            description="Retry with increased timeout",
            requires_user_action=False,
            new_config=config,
        )
        mock_test_conn.side_effect = [
            _failed_connection("Server did not respond within 30s"),
            _ok_connection(),
        ]

        from mcp_tap.healing.retry import heal_and_retry

        result = await heal_and_retry(
            "test-server", config, initial_error, max_attempts=3,
        )

        assert result.fixed is True
        assert len(result.attempts) == 2

    # ── All attempts fail ─────────────────────────────────────

    @patch("mcp_tap.healing.retry.test_server_connection")
    @patch("mcp_tap.healing.retry.generate_fix")
    @patch("mcp_tap.healing.retry.classify_error")
    async def test_all_attempts_fail(
        self, mock_classify, mock_generate_fix, mock_test_conn,
    ):
        """Should return fixed=False when all max_attempts exhausted."""
        initial_error = _failed_connection(
            "Server did not respond within 15s",
        )
        config = _server_config()

        mock_classify.return_value = _diagnosis(
            category=ErrorCategory.TIMEOUT,
        )
        mock_generate_fix.return_value = CandidateFix(
            description="Retry with increased timeout",
            requires_user_action=False,
            new_config=config,
        )
        mock_test_conn.return_value = _failed_connection(
            "Server did not respond within 60s",
        )

        from mcp_tap.healing.retry import heal_and_retry

        result = await heal_and_retry(
            "test-server", config, initial_error, max_attempts=3,
        )

        assert result.fixed is False
        assert len(result.attempts) == 3
        assert mock_test_conn.await_count == 3
        assert result.user_action_needed != ""

    # ── User action required stops immediately ────────────────

    @patch("mcp_tap.healing.retry.test_server_connection")
    @patch("mcp_tap.healing.retry.generate_fix")
    @patch("mcp_tap.healing.retry.classify_error")
    async def test_user_action_stops_immediately(
        self, mock_classify, mock_generate_fix, mock_test_conn,
    ):
        """Should stop when fix requires user intervention."""
        initial_error = _failed_connection("401 Unauthorized")
        config = _server_config()

        mock_classify.return_value = _diagnosis(
            category=ErrorCategory.AUTH_FAILED,
        )
        mock_generate_fix.return_value = CandidateFix(
            description="Set API token in env vars",
            requires_user_action=True,
            env_var_hint="Set AUTH_TOKEN environment variable",
        )

        from mcp_tap.healing.retry import heal_and_retry

        result = await heal_and_retry(
            "test-server", config, initial_error, max_attempts=3,
        )

        assert result.fixed is False
        assert result.user_action_needed != ""
        mock_test_conn.assert_not_awaited()

    @patch("mcp_tap.healing.retry.test_server_connection")
    @patch("mcp_tap.healing.retry.generate_fix")
    @patch("mcp_tap.healing.retry.classify_error")
    async def test_user_action_missing_env_var(
        self, mock_classify, mock_generate_fix, mock_test_conn,
    ):
        """Should stop for MISSING_ENV_VAR since user must set it."""
        initial_error = _failed_connection("SLACK_BOT_TOKEN is not set")
        config = _server_config()

        mock_classify.return_value = _diagnosis(
            category=ErrorCategory.MISSING_ENV_VAR,
        )
        mock_generate_fix.return_value = CandidateFix(
            description="Set SLACK_BOT_TOKEN",
            requires_user_action=True,
            env_var_hint="SLACK_BOT_TOKEN",
        )

        from mcp_tap.healing.retry import heal_and_retry

        result = await heal_and_retry(
            "test-server", config, initial_error, max_attempts=3,
        )

        assert result.fixed is False
        assert result.user_action_needed != ""
        mock_test_conn.assert_not_awaited()

    # ── Max attempts respected ────────────────────────────────

    @patch("mcp_tap.healing.retry.test_server_connection")
    @patch("mcp_tap.healing.retry.generate_fix")
    @patch("mcp_tap.healing.retry.classify_error")
    async def test_max_attempts_respected(
        self, mock_classify, mock_generate_fix, mock_test_conn,
    ):
        """Should never exceed max_attempts calls."""
        initial_error = _failed_connection(
            "Server did not respond within 15s",
        )
        config = _server_config()

        mock_classify.return_value = _diagnosis(
            category=ErrorCategory.TIMEOUT,
        )
        mock_generate_fix.return_value = CandidateFix(
            description="Retry with increased timeout",
            requires_user_action=False,
            new_config=config,
        )
        mock_test_conn.return_value = _failed_connection(
            "Server did not respond within 30s",
        )

        from mcp_tap.healing.retry import heal_and_retry

        result = await heal_and_retry(
            "test-server", config, initial_error, max_attempts=2,
        )

        assert mock_test_conn.await_count == 2
        assert result.fixed is False
        assert len(result.attempts) == 2

    @patch("mcp_tap.healing.retry.test_server_connection")
    @patch("mcp_tap.healing.retry.generate_fix")
    @patch("mcp_tap.healing.retry.classify_error")
    async def test_single_attempt_max(
        self, mock_classify, mock_generate_fix, mock_test_conn,
    ):
        """Should work correctly with max_attempts=1."""
        initial_error = _failed_connection(
            "Server did not respond within 15s",
        )
        config = _server_config()

        mock_classify.return_value = _diagnosis(
            category=ErrorCategory.TIMEOUT,
        )
        mock_generate_fix.return_value = CandidateFix(
            description="Retry with increased timeout",
            requires_user_action=False,
            new_config=config,
        )
        mock_test_conn.return_value = _ok_connection()

        from mcp_tap.healing.retry import heal_and_retry

        result = await heal_and_retry(
            "test-server", config, initial_error, max_attempts=1,
        )

        assert result.fixed is True
        assert len(result.attempts) == 1
        mock_test_conn.assert_awaited_once()

    # ── Result structure ──────────────────────────────────────

    @patch("mcp_tap.healing.retry.test_server_connection")
    @patch("mcp_tap.healing.retry.generate_fix")
    @patch("mcp_tap.healing.retry.classify_error")
    async def test_result_contains_attempts_list(
        self, mock_classify, mock_generate_fix, mock_test_conn,
    ):
        """Should populate attempts with HealingAttempt objects."""
        initial_error = _failed_connection("Command not found: npx")
        config = _server_config()

        mock_classify.return_value = _diagnosis(
            category=ErrorCategory.COMMAND_NOT_FOUND,
        )
        mock_generate_fix.return_value = CandidateFix(
            description="Resolved path",
            requires_user_action=False,
            new_config=_server_config(command="/usr/local/bin/npx"),
        )
        mock_test_conn.return_value = _ok_connection()

        from mcp_tap.healing.retry import heal_and_retry

        result = await heal_and_retry(
            "test-server", config, initial_error, max_attempts=3,
        )

        assert isinstance(result.attempts, list)
        assert len(result.attempts) >= 1
        for attempt in result.attempts:
            assert isinstance(attempt, HealingAttempt)
            assert isinstance(attempt.diagnosis, DiagnosisResult)
            assert isinstance(attempt.fix_applied, CandidateFix)
            assert isinstance(attempt.success, bool)

    @patch("mcp_tap.healing.retry.test_server_connection")
    @patch("mcp_tap.healing.retry.generate_fix")
    @patch("mcp_tap.healing.retry.classify_error")
    async def test_result_fixed_config_on_success(
        self, mock_classify, mock_generate_fix, mock_test_conn,
    ):
        """Should include the working config in fixed_config."""
        initial_error = _failed_connection("Command not found: npx")
        config = _server_config(command="npx")
        repaired = _server_config(command="/usr/local/bin/npx")

        mock_classify.return_value = _diagnosis(
            category=ErrorCategory.COMMAND_NOT_FOUND,
        )
        mock_generate_fix.return_value = CandidateFix(
            description="Resolved path",
            requires_user_action=False,
            new_config=repaired,
        )
        mock_test_conn.return_value = _ok_connection()

        from mcp_tap.healing.retry import heal_and_retry

        result = await heal_and_retry(
            "test-server", config, initial_error, max_attempts=3,
        )

        assert result.fixed is True
        assert result.fixed_config is not None
        assert result.fixed_config.command == "/usr/local/bin/npx"

    @patch("mcp_tap.healing.retry.test_server_connection")
    @patch("mcp_tap.healing.retry.generate_fix")
    @patch("mcp_tap.healing.retry.classify_error")
    async def test_result_fixed_config_on_user_action(
        self, mock_classify, mock_generate_fix, mock_test_conn,
    ):
        """Should preserve original config in fixed_config on failure."""
        initial_error = _failed_connection("Connection refused")
        config = _server_config()

        mock_classify.return_value = _diagnosis(
            category=ErrorCategory.CONNECTION_REFUSED,
        )
        mock_generate_fix.return_value = CandidateFix(
            description="Check service",
            requires_user_action=True,
        )

        from mcp_tap.healing.retry import heal_and_retry

        result = await heal_and_retry(
            "test-server", config, initial_error, max_attempts=3,
        )

        assert result.fixed is False
        # fixed_config is still set (to the current config) even on failure
        assert result.fixed_config is not None

    @patch("mcp_tap.healing.retry.test_server_connection")
    @patch("mcp_tap.healing.retry.generate_fix")
    @patch("mcp_tap.healing.retry.classify_error")
    async def test_timeout_escalation(
        self, mock_classify, mock_generate_fix, mock_test_conn,
    ):
        """Should escalate timeout values on successive timeout failures."""
        initial_error = _failed_connection(
            "Server did not respond within 15s",
        )
        config = _server_config()

        mock_classify.return_value = _diagnosis(
            category=ErrorCategory.TIMEOUT,
        )
        mock_generate_fix.return_value = CandidateFix(
            description="Retry with increased timeout",
            requires_user_action=False,
            new_config=config,
        )
        mock_test_conn.return_value = _failed_connection(
            "Server did not respond within 60s",
        )

        from mcp_tap.healing.retry import heal_and_retry

        await heal_and_retry(
            "test-server", config, initial_error, max_attempts=3,
        )

        call_kwargs = [c.kwargs for c in mock_test_conn.call_args_list]
        timeouts = [kw["timeout_seconds"] for kw in call_kwargs]
        assert timeouts == [15, 30, 60]

    # ── Frozen models ─────────────────────────────────────────

    def test_healing_result_is_frozen(self):
        """HealingResult should be a frozen dataclass."""
        result = HealingResult(fixed=False, attempts=[])
        with pytest.raises(AttributeError):
            result.fixed = True  # type: ignore[misc]

    def test_healing_attempt_is_frozen(self):
        """HealingAttempt should be a frozen dataclass."""
        attempt = _healing_attempt()
        with pytest.raises(AttributeError):
            attempt.success = True  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════
# 4. Model Validation Tests
# ═══════════════════════════════════════════════════════════════


class TestHealingModels:
    """Tests for healing-related domain models in models.py."""

    def test_error_category_is_str_enum(self):
        """ErrorCategory should be a StrEnum with all expected members."""
        assert isinstance(ErrorCategory.COMMAND_NOT_FOUND, str)
        expected = {
            "COMMAND_NOT_FOUND", "CONNECTION_REFUSED", "TIMEOUT",
            "AUTH_FAILED", "MISSING_ENV_VAR", "PERMISSION_DENIED",
            "UNKNOWN",
        }
        actual = {m.name for m in ErrorCategory}
        assert expected.issubset(actual)

    def test_error_category_values_are_snake_case(self):
        """ErrorCategory values should be lowercase snake_case strings."""
        for member in ErrorCategory:
            assert member.value == member.name.lower()

    def test_diagnosis_result_construction(self):
        """Should construct a valid DiagnosisResult with all fields."""
        diag = DiagnosisResult(
            category=ErrorCategory.TIMEOUT,
            original_error="timed out",
            explanation="Server took too long.",
            suggested_fix="Increase timeout.",
            confidence=0.85,
        )
        assert diag.category == ErrorCategory.TIMEOUT
        assert diag.confidence == 0.85
        assert diag.original_error == "timed out"

    def test_diagnosis_result_default_confidence(self):
        """DiagnosisResult confidence should default to 1.0."""
        diag = DiagnosisResult(
            category=ErrorCategory.UNKNOWN,
            original_error="x",
            explanation="y",
            suggested_fix="z",
        )
        assert diag.confidence == 1.0

    def test_candidate_fix_with_no_new_config(self):
        """CandidateFix should allow new_config to be None."""
        fix = CandidateFix(
            description="Manual intervention needed",
            requires_user_action=True,
        )
        assert fix.new_config is None

    def test_candidate_fix_with_config(self):
        """CandidateFix should accept a new_config."""
        config = _server_config(command="/usr/local/bin/npx")
        fix = CandidateFix(
            description="Resolved path",
            requires_user_action=False,
            new_config=config,
        )
        assert fix.new_config is not None
        assert fix.new_config.command == "/usr/local/bin/npx"

    def test_candidate_fix_env_var_hint_default(self):
        """CandidateFix env_var_hint should default to None."""
        fix = CandidateFix(description="test", requires_user_action=False)
        assert fix.env_var_hint is None

    def test_candidate_fix_install_command_default(self):
        """CandidateFix install_command should default to None."""
        fix = CandidateFix(description="test", requires_user_action=False)
        assert fix.install_command is None

    def test_healing_result_default_fields(self):
        """HealingResult should have sensible defaults."""
        result = HealingResult(fixed=False, attempts=[])
        assert result.fixed is False
        assert result.attempts == []
        assert result.fixed_config is None
        assert result.user_action_needed == ""

    def test_healing_attempt_stores_all_fields(self):
        """HealingAttempt should store diagnosis, fix_applied, success."""
        diag = _diagnosis()
        fix = CandidateFix(description="test fix", requires_user_action=False)
        attempt = HealingAttempt(
            diagnosis=diag, fix_applied=fix, success=True,
        )
        assert attempt.diagnosis.category == ErrorCategory.COMMAND_NOT_FOUND
        assert attempt.fix_applied.description == "test fix"
        assert attempt.success is True
