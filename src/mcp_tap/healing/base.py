"""Ports: Error classification, fix generation, and healing orchestration."""

from __future__ import annotations

from typing import Protocol

from mcp_tap.models import (
    CandidateFix,
    ConnectionTestResult,
    DiagnosisResult,
    HealingResult,
    ServerConfig,
)


class ErrorClassifierPort(Protocol):
    """Port for classifying raw connection errors into structured diagnoses."""

    def classify_error(self, error: ConnectionTestResult) -> DiagnosisResult:
        """Map a failed ConnectionTestResult to a structured DiagnosisResult."""
        ...


class FixGeneratorPort(Protocol):
    """Port for generating candidate fixes from diagnoses."""

    def generate_fix(
        self,
        diagnosis: DiagnosisResult,
        current_config: ServerConfig,
    ) -> CandidateFix:
        """Produce a CandidateFix for the given diagnosis."""
        ...


class HealingOrchestratorPort(Protocol):
    """Port for the diagnose-fix-retry healing loop."""

    async def heal_and_retry(
        self,
        server_name: str,
        server_config: ServerConfig,
        error: ConnectionTestResult,
        *,
        max_attempts: int = 2,
        timeout_seconds: int = 15,
    ) -> HealingResult:
        """Diagnose an error, apply a fix, and retry validation."""
        ...
