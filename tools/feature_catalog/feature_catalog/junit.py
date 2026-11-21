"""Reads JUnit XML reports (pytest, vitest, Playwright) and finds the result of each evidence.

Which test run a report belongs to is decided by its content (suite names, test file
suffixes), never by its file name.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

from feature_catalog.model import Evidence, TestRun

Outcome = Literal["passed", "failed", "skipped"]
PLAYWRIGHT_SEPARATOR = " \u203a "  # Playwright joins describe and test titles with it
Status = Literal["passed", "failed", "skipped", "not-run", "no-report", "not-checked"]


@dataclass
class Case:
    classname: str
    name: str
    outcome: Outcome


@dataclass
class Run:
    config: TestRun
    files: list[str] = field(default_factory=list)
    cases: list[Case] = field(default_factory=list)


def _outcome(case: ET.Element) -> Outcome:
    if case.find("failure") is not None or case.find("error") is not None:
        return "failed"
    if case.find("skipped") is not None:
        return "skipped"
    return "passed"


def _recognize(root: ET.Element, runs: list[TestRun]) -> TestRun | None:
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    names = {root.get("name", "")} | {s.get("name", "") for s in suites[:1]}
    for run in runs:
        if run.suite and run.suite in names:
            return run
    classnames = {c.get("classname", "") for c in root.iter("testcase")}
    if classnames and all(c.endswith(".spec.ts") for c in classnames):
        return next((r for r in runs if r.format == "playwright"), None)
    return None


def read_reports(directory: Path, runs: list[TestRun]) -> dict[str, Run]:
    result: dict[str, Run] = {}
    for path in sorted(directory.rglob("*.xml")):
        try:
            root = ET.parse(path).getroot()  # noqa: S314
        except ET.ParseError:
            continue
        config = _recognize(root, runs)
        if config is None:
            continue
        run = result.setdefault(config.id, Run(config))
        run.files.append(path.as_posix())
        for case in root.iter("testcase"):
            run.cases.append(Case(case.get("classname", ""), case.get("name", ""), _outcome(case)))
    return result


def _strip_param(name: str) -> str:
    return name.split("[", 1)[0] if name.endswith("]") else name


def run_for(evidence: Evidence, runs: list[TestRun]) -> TestRun | None:
    file = PurePosixPath(evidence.file)
    for run in runs:
        if not file.is_relative_to(run.root):
            continue
        if run.format == "pytest" and file.suffix == ".py":
            return run
        if run.format == "playwright" and file.name.endswith(".spec.ts"):
            return run
        if run.format == "vitest" and ".test." in file.name:
            return run
    return None


def matches(evidence: Evidence, run: TestRun, case: Case) -> bool:
    rel = PurePosixPath(evidence.file).relative_to(run.root)
    if run.format == "pytest":
        module = ".".join(rel.with_suffix("").parts)
        cls, _, func = evidence.test.rpartition("::")
        classname = f"{module}.{cls}" if cls else module
        return case.classname == classname and _strip_param(case.name) == func
    if case.classname != rel.as_posix():
        return False
    sep = PLAYWRIGHT_SEPARATOR if run.format == "playwright" else " > "
    return case.name == evidence.test or case.name.endswith(sep + evidence.test)


def result(evidence: Evidence, runs: list[TestRun], reports: dict[str, Run] | None) -> Status:
    if reports is None:
        return "not-checked"
    run = run_for(evidence, runs)
    if run is None or run.id not in reports:
        return "no-report"
    outcomes = [c.outcome for c in reports[run.id].cases if matches(evidence, run, c)]
    if not outcomes:
        return "not-run"
    if "failed" in outcomes:
        return "failed"
    if "skipped" in outcomes:
        return "skipped"
    return "passed"
