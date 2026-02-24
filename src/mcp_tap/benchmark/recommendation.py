"""Recommendation quality benchmark for scan_project outputs."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from importlib.resources import files
from pathlib import Path
from statistics import mean

from mcp_tap.models import MCPClient
from mcp_tap.scanner.detector import scan_project

_DEFAULT_DATASET = "recommendation_dataset_v1.json"


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One benchmark fixture with expected top recommendations."""

    name: str
    project_path: str
    client: MCPClient
    expected_servers: tuple[str, ...]
    top_k: int


@dataclass(frozen=True, slots=True)
class CaseResult:
    """Computed benchmark metrics for a single case."""

    name: str
    project_path: str
    client: str
    top_k: int
    expected_servers: tuple[str, ...]
    actual_top_k: tuple[str, ...]
    hit_count: int
    precision_at_k: float
    accepted_top_1: bool | None


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Aggregate benchmark report across all cases."""

    dataset: str
    case_count: int
    precision_at_k: float
    acceptance_rate: float
    coverage_at_k: float
    min_precision: float
    min_acceptance: float
    passed: bool
    failures: tuple[str, ...]
    cases: tuple[CaseResult, ...]


def default_dataset_path() -> Path:
    """Return the packaged recommendation benchmark dataset path."""
    return Path(str(files("mcp_tap.benchmark").joinpath(_DEFAULT_DATASET)))


def load_cases(dataset_path: Path | None = None) -> tuple[str, list[BenchmarkCase]]:
    """Load benchmark cases from JSON dataset."""
    path = dataset_path or default_dataset_path()
    raw = json.loads(path.read_text(encoding="utf-8"))

    dataset_name = str(raw.get("name") or path.name)
    default_top_k = int(raw.get("top_k", 3))
    cases_raw = raw.get("cases", [])
    if not isinstance(cases_raw, list) or not cases_raw:
        raise ValueError("Benchmark dataset must define a non-empty 'cases' list.")

    cases: list[BenchmarkCase] = []
    for item in cases_raw:
        if not isinstance(item, dict):
            raise ValueError("Each benchmark case must be an object.")

        top_k = int(item.get("top_k", default_top_k))
        if top_k <= 0:
            raise ValueError(f"Invalid top_k for case '{item.get('name', 'unknown')}'.")

        expected = item.get("expected_servers", [])
        if not isinstance(expected, list):
            raise ValueError("expected_servers must be a list.")

        cases.append(
            BenchmarkCase(
                name=str(item["name"]),
                project_path=str(item["project_path"]),
                client=MCPClient(str(item.get("client", MCPClient.CLAUDE_CODE.value))),
                expected_servers=tuple(str(s) for s in expected),
                top_k=top_k,
            )
        )

    return dataset_name, cases


def evaluate_case(actual_servers: list[str], case: BenchmarkCase) -> CaseResult:
    """Compute precision/acceptance for one benchmark case."""
    actual_top_k = tuple(actual_servers[: case.top_k])
    expected_set = set(case.expected_servers)

    if not expected_set:
        precision = 1.0 if not actual_top_k else 0.0
        accepted: bool | None = None
        hit_count = 0
    else:
        hit_count = sum(1 for s in actual_top_k if s in expected_set)
        precision = hit_count / max(1, len(actual_top_k))
        accepted = bool(actual_top_k and actual_top_k[0] in expected_set)

    return CaseResult(
        name=case.name,
        project_path=case.project_path,
        client=case.client.value,
        top_k=case.top_k,
        expected_servers=case.expected_servers,
        actual_top_k=actual_top_k,
        hit_count=hit_count,
        precision_at_k=round(precision, 4),
        accepted_top_1=accepted,
    )


def build_report(
    *,
    dataset: str,
    case_results: list[CaseResult],
    min_precision: float,
    min_acceptance: float,
) -> BenchmarkReport:
    """Aggregate benchmark results and evaluate thresholds."""
    if not case_results:
        raise ValueError("Cannot build report with no case results.")

    precision = mean(c.precision_at_k for c in case_results)

    acceptance_inputs = [c.accepted_top_1 for c in case_results if c.accepted_top_1 is not None]
    acceptance = mean(1.0 if v else 0.0 for v in acceptance_inputs) if acceptance_inputs else 1.0

    coverage_inputs = [c for c in case_results if c.expected_servers]
    coverage = (
        mean(1.0 if c.hit_count > 0 else 0.0 for c in coverage_inputs) if coverage_inputs else 1.0
    )

    failures: list[str] = []
    if precision < min_precision:
        failures.append(f"precision_at_k={precision:.3f} is below threshold {min_precision:.3f}")
    if acceptance < min_acceptance:
        failures.append(f"acceptance_rate={acceptance:.3f} is below threshold {min_acceptance:.3f}")

    return BenchmarkReport(
        dataset=dataset,
        case_count=len(case_results),
        precision_at_k=round(precision, 4),
        acceptance_rate=round(acceptance, 4),
        coverage_at_k=round(coverage, 4),
        min_precision=min_precision,
        min_acceptance=min_acceptance,
        passed=not failures,
        failures=tuple(failures),
        cases=tuple(case_results),
    )


async def run_benchmark(
    *,
    dataset_path: Path | None = None,
    project_root: Path | None = None,
    min_precision: float = 0.90,
    min_acceptance: float = 0.85,
) -> BenchmarkReport:
    """Run recommendation benchmark by scanning each dataset fixture project."""
    dataset_name, cases = load_cases(dataset_path)
    root = (project_root or Path.cwd()).resolve()

    case_results: list[CaseResult] = []
    for case in cases:
        case_path = Path(case.project_path)
        resolved_path = case_path if case_path.is_absolute() else root / case_path
        profile = await scan_project(str(resolved_path), client=case.client)
        actual = [rec.server_name for rec in profile.recommendations]
        case_results.append(evaluate_case(actual, case))

    return build_report(
        dataset=dataset_name,
        case_results=case_results,
        min_precision=min_precision,
        min_acceptance=min_acceptance,
    )


def _format_report_text(report: BenchmarkReport) -> str:
    lines = [
        f"Recommendation Benchmark: {report.dataset}",
        f"Cases: {report.case_count}",
        f"precision@k: {report.precision_at_k:.3f} (min {report.min_precision:.3f})",
        f"acceptance_rate: {report.acceptance_rate:.3f} (min {report.min_acceptance:.3f})",
        f"coverage@k: {report.coverage_at_k:.3f}",
    ]
    if report.passed:
        lines.append("status: PASS")
    else:
        lines.append("status: FAIL")
        lines.extend(f"- {failure}" for failure in report.failures)

    lines.append("case details:")
    for case in report.cases:
        accepted = (
            "n/a" if case.accepted_top_1 is None else ("yes" if case.accepted_top_1 else "no")
        )
        lines.append(
            f"- {case.name}: precision={case.precision_at_k:.3f}, "
            f"accepted_top_1={accepted}, top_k={list(case.actual_top_k)}"
        )

    return "\n".join(lines)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Run recommendation benchmark quality gate (precision@k + acceptance_rate).")
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Optional dataset JSON path. Defaults to packaged recommendation_dataset_v1.json.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root used to resolve relative fixture paths.",
    )
    parser.add_argument(
        "--min-precision",
        type=float,
        default=0.90,
        help="Minimum required precision@k threshold.",
    )
    parser.add_argument(
        "--min-acceptance",
        type=float,
        default=0.85,
        help="Minimum required acceptance_rate threshold.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print report as JSON instead of human-readable text.",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Always exit 0 even if thresholds fail (report-only mode).",
    )
    return parser.parse_args(argv)


def run_cli(argv: list[str] | None = None) -> int:
    """CLI runner for recommendation benchmark quality gate."""
    args = _parse_args(argv)
    report = asyncio.run(
        run_benchmark(
            dataset_path=args.dataset,
            project_root=args.project_root,
            min_precision=args.min_precision,
            min_acceptance=args.min_acceptance,
        )
    )

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(_format_report_text(report))

    if args.no_fail:
        return 0
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(run_cli())
