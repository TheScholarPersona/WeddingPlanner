"""Checks the catalog against the code and the test reports. It only reports; it never adds
features (unassigned parts, dead references and missing evidence are findings)."""

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from feature_catalog.calls import PythonCalls, normalize, pattern, ts_calls
from feature_catalog.catalog import PART_KINDS, Catalog, Discovered, match_length
from feature_catalog.junit import Run, Status, result, run_for
from feature_catalog.model import Area, Feature
from feature_catalog.testcode import TestBody, inspect_test

Level = Literal["error", "warning", "info"]
GENERIC_SEGMENTS = {"orgs", "projects", "portal", "api", "v1", "app"}
# Error codes: snake_case with an underscore, UPPER_SNAKE or an HTTP status (`too_many_images`).
CODE_IN_RULE = re.compile(r"`([a-z]+(?:_[a-z0-9]+)+|[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|[1-5]\d\d)`")
UNKNOWN_CODES = {
    "endpoints": "UNKNOWN_ENDPOINT",
    "jobs": "UNKNOWN_JOB",
    "commands": "UNKNOWN_COMMAND",
    "uiRoutes": "UNKNOWN_ROUTE",
}


@dataclass
class Finding:
    code: str
    level: Level
    message: str
    feature: str | None = None
    file: str | None = None


@dataclass
class EvidenceResult:
    index: int
    status: Status
    found: bool
    line: int
    assertions: int
    status_only: bool
    related: bool


@dataclass
class FeatureResult:
    proof: Literal["proven", "partial", "unproven", "static"]
    evidence: list[EvidenceResult]
    uncovered: list[str]


@dataclass
class Analysis:
    findings: list[Finding] = field(default_factory=list)
    features: dict[str, FeatureResult] = field(default_factory=dict)
    called_by: dict[str, list[str]] = field(default_factory=dict)  # endpoint -> test files
    assigned: dict[str, dict[str, str]] = field(default_factory=dict)  # kind -> key -> feature
    owner: dict[str, dict[str, str]] = field(default_factory=dict)  # kind -> key -> area
    reports_checked: bool = False

    def add(self, code: str, level: Level, message: str, **where: Any) -> None:
        self.findings.append(Finding(code, level, message, **where))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "warning"]


def rule_codes(feature: Feature) -> set[str]:
    return {code for rule in feature.rules for code in CODE_IN_RULE.findall(rule)}


def _segments(path: str) -> list[str]:
    return [
        s
        for s in re.split(r"[/.]", path)
        if s and not s.startswith(("{", ":")) and s not in GENERIC_SEGMENTS
    ]


def related(feature: Feature, body: TestBody) -> bool:
    """Does the test body touch a part of the feature (N4)? Heuristic for a warning."""
    text = body.text

    def has(word: str) -> bool:
        return re.search(rf"(?<![A-Za-z0-9_]){re.escape(word)}(?![A-Za-z0-9_])", text) is not None

    def touches(path: str) -> bool:
        segments = _segments(path)
        if segments:
            return all(has(s) for s in segments)
        # Only generic segments (`/portal/projects/{id}`): look for the static path itself.
        static = re.split(r"/[{:]", path, maxsplit=1)[0]
        return (
            bool(static) and re.search(re.escape(static) + r"(?![A-Za-z0-9_-])", text) is not None
        )

    for endpoint in feature.technical.endpoints:
        if touches(endpoint.split(" ", 1)[1]):
            return True
    for route in feature.technical.uiRoutes:
        if touches(route):
            return True
    for component in feature.technical.components:
        if PurePosixPath(component).stem in text:
            return True
    return any(job in text for job in feature.technical.jobs + feature.technical.commands)


def _check_structure(catalog: Catalog, discovered: Discovered, analysis: Analysis) -> None:
    assert catalog.config is not None
    areas = {a.id: a for a in catalog.config.areas}
    ids = Counter(f.id for _, f, _ in catalog.all_features())
    for feature_id, count in ids.items():
        if count > 1:
            analysis.add("SCHEMA", "error", f"feature id used {count} times", feature=feature_id)
    for area_id, feature, _ in catalog.all_features():
        where = {"feature": feature.id, "file": catalog.files.get(feature.id)}
        area = areas.get(area_id)
        if area is None:
            analysis.add("SCHEMA", "error", f"unknown area '{area_id}'", **where)
            continue
        if feature.group not in {g.id for g in area.groups}:
            analysis.add("SCHEMA", "error", f"group '{feature.group}' not in {area.id}", **where)
        if not feature.id.startswith(area.id + "."):
            analysis.add("SCHEMA", "error", f"id must start with '{area.id}.'", **where)
        for kind in PART_KINDS:
            for key in getattr(feature.technical, kind):
                if key not in discovered.parts[kind]:
                    analysis.add(UNKNOWN_CODES[kind], "error", f"{key} does not exist", **where)
        for component in feature.technical.components:
            if not (catalog.root / component).exists():
                analysis.add("UNKNOWN_COMPONENT", "error", f"{component} is missing", **where)
        for dependency in feature.dependsOn:
            if dependency not in ids:
                analysis.add("UNKNOWN_DEPENDENCY", "error", f"{dependency} is unknown", **where)


def _check_parts(catalog: Catalog, discovered: Discovered, analysis: Analysis) -> None:
    assert catalog.config is not None
    excluded = {
        kind: {e.item for e in getattr(catalog.config.exclusions, kind)} for kind in PART_KINDS
    }
    for kind in PART_KINDS:
        analysis.assigned[kind] = {}
        analysis.owner[kind] = {}
        for _, feature, _ in catalog.all_features():
            for key in getattr(feature.technical, kind):
                analysis.assigned[kind].setdefault(key, feature.id)
        for item in excluded[kind]:
            if item not in discovered.parts[kind]:
                analysis.add(UNKNOWN_CODES[kind], "error", f"excluded {item} does not exist")
    for kind in PART_KINDS:
        for key in discovered.parts[kind]:
            if key in excluded[kind]:
                continue
            scored = [
                (match_length(kind, key, getattr(a.owns, kind)), a) for a in catalog.config.areas
            ]
            best = max((score for score, _ in scored), default=0)
            if best == 0:
                analysis.add("UNOWNED", "error", f"{key} ({kind}): no area claims it")
                continue
            owners = [a for score, a in scored if score == best]
            if len(owners) > 1:
                names = ", ".join(a.id for a in owners)
                analysis.add("SCHEMA", "error", f"{key} ({kind}) is claimed by {names}")
            area: Area = owners[0]
            analysis.owner[kind][key] = area.id
            if key not in analysis.assigned[kind]:
                level: Level = "error" if area.status == "catalogued" else "info"
                analysis.add(
                    "UNASSIGNED", level, f"{key} ({kind}) in area {area.id} has no feature"
                )


def _test_files(catalog: Catalog) -> list[Path]:
    assert catalog.config is not None
    files: list[Path] = []
    for run in catalog.config.testRuns:
        base = catalog.root / run.root
        if run.format == "pytest":
            files += sorted(base.glob("tests/**/test_*.py"))
        elif run.format == "playwright":
            files += sorted(base.glob("**/*.spec.ts"))
        else:
            files += sorted(
                p for p in base.glob("src/**/*.test.ts*") if "node_modules" not in p.parts
            )
    return files


def _check_calls(catalog: Catalog, discovered: Discovered, analysis: Analysis) -> None:
    assert catalog.config is not None
    calls: list[tuple[str, str, str]] = []
    for run in catalog.config.testRuns:
        base = catalog.root / run.root
        if run.format == "pytest":
            resolver = PythonCalls(base)
            for path in sorted(base.glob("tests/**/test_*.py")):
                rel = path.relative_to(catalog.root).as_posix()
                calls += [(m, p, rel) for m, p in resolver.calls(path)]
    for test_file in _test_files(catalog):
        if test_file.suffix == ".ts":
            rel = test_file.relative_to(catalog.root).as_posix()
            calls += [(m, p, rel) for m, p in ts_calls(test_file)]
    prefix = discovered.api_prefix
    for key in discovered.parts["endpoints"]:
        method, endpoint_path = key.split(" ", 1)
        regex = pattern(endpoint_path)
        files = sorted(
            {
                file
                for m, p, file in calls
                if m == method and regex.match(normalize(p).removeprefix(prefix))
            }
        )
        analysis.called_by[key] = files
        area = analysis.owner["endpoints"].get(key)
        if not files and area:
            status = next(a.status for a in catalog.config.areas if a.id == area)
            level: Level = "warning" if status == "catalogued" else "info"
            analysis.add("ENDPOINT_UNTESTED", level, f"no test calls {key} recognizably")


def _check_evidence(catalog: Catalog, analysis: Analysis, reports: dict[str, Run] | None) -> None:
    assert catalog.config is not None
    runs = catalog.config.testRuns
    for _, feature, state in catalog.all_features():
        where = {"feature": feature.id, "file": catalog.files.get(feature.id)}
        listed = state is None  # review entries are reported, not enforced
        level: Level = "error" if listed else "info"
        criteria = {c.id: c for c in feature.acceptance}
        if listed and not feature.evidence:
            analysis.add("EVIDENCE_MISSING", "error", "no evidence", **where)
        if listed and not any(c.kind == "effect" for c in feature.acceptance):
            analysis.add("ACCEPTANCE_MISSING", "error", "no criterion of kind effect", **where)
        rule_criteria = {c.code for c in feature.acceptance if c.kind == "rule" and c.code}
        for code in sorted(rule_codes(feature) - rule_criteria):
            analysis.add(
                "RULE_WITHOUT_ACCEPTANCE", level, f"rule code `{code}` has no criterion", **where
            )
        results: list[EvidenceResult] = []
        covered: set[str] = set()
        bodies: dict[str, list[TestBody]] = {c: [] for c in criteria}
        for index, evidence in enumerate(feature.evidence):
            label = f"{evidence.file} :: {evidence.test}"
            unknown = [c for c in evidence.covers if c not in criteria]
            if not evidence.covers or unknown:
                analysis.add(
                    "EVIDENCE_UNLINKED",
                    level,
                    f"{label}: covers {unknown or 'nothing'}",
                    **where,
                )
            run = run_for(evidence, runs)
            if run is not None and run.kind != evidence.kind:
                analysis.add(
                    "EVIDENCE_KIND", level, f"{label}: run {run.id} is {run.kind}", **where
                )
            body = inspect_test(catalog.root / evidence.file, evidence.test)
            status = result(evidence, runs, reports)
            is_related = body.found and related(feature, body)
            results.append(
                EvidenceResult(
                    index,
                    status,
                    body.found,
                    body.line,
                    body.assertions,
                    body.status_only,
                    is_related,
                )
            )
            if not body.found:
                analysis.add("UNKNOWN_TEST", level, f"{label}: test not found", **where)
                continue
            if body.assertions == 0:
                analysis.add("EVIDENCE_NO_ASSERTION", level, f"{label}: no assertion", **where)
                continue
            # For a rule, a refused request with its status code is the assertion (N4);
            # an effect needs more than a status.
            effects = [c for c in evidence.covers if c in criteria and criteria[c].kind == "effect"]
            if body.status_only and effects:
                analysis.add(
                    "EVIDENCE_STATUS_ONLY", "warning", f"{label}: only status checks", **where
                )
            if not is_related:
                analysis.add(
                    "EVIDENCE_UNRELATED",
                    "warning",
                    f"{label}: touches no part of the feature",
                    **where,
                )
            codes = {
                "failed": "EVIDENCE_FAILED",
                "skipped": "EVIDENCE_SKIPPED",
                "not-run": "EVIDENCE_NOT_RUN",
                "no-report": "EVIDENCE_NOT_RUN",
            }
            if status in codes:
                detail = "no report of its test run" if status == "no-report" else status
                analysis.add(codes[status], level, f"{label}: {detail}", **where)
            if status in ("passed", "not-checked"):
                for covered_id in evidence.covers:
                    if covered_id in criteria:
                        covered.add(covered_id)
                        bodies[covered_id].append(body)
        uncovered = [c for c in criteria if c not in covered]
        for uncovered_id in uncovered:
            analysis.add(
                "ACCEPTANCE_UNCOVERED",
                level,
                f"criterion '{uncovered_id}' has no passed evidence",
                **where,
            )
        for criterion in criteria.values():
            if criterion.kind == "rule" and criterion.code and bodies[criterion.id]:
                if not any(criterion.code in b.text for b in bodies[criterion.id]):
                    analysis.add(
                        "RULE_CODE_NOT_ASSERTED",
                        level,
                        f"criterion '{criterion.id}': `{criterion.code}` not in its tests",
                        **where,
                    )
        if reports is None:
            proof: Literal["proven", "partial", "unproven", "static"] = "static"
        elif criteria and not uncovered:
            proof = "proven"
        elif covered:
            proof = "partial"
        else:
            proof = "unproven"
        analysis.features[feature.id] = FeatureResult(proof, results, uncovered)


def analyze(catalog: Catalog, discovered: Discovered, reports: dict[str, Run] | None) -> Analysis:
    analysis = Analysis(reports_checked=reports is not None)
    for problem in catalog.problems + discovered.problems:
        analysis.add("SCHEMA", "error", problem.message, file=problem.file)
    if catalog.config is None:
        return analysis
    _check_structure(catalog, discovered, analysis)
    _check_parts(catalog, discovered, analysis)
    _check_calls(catalog, discovered, analysis)
    _check_evidence(catalog, analysis, reports)
    if reports is not None:
        for run in catalog.config.testRuns:
            if run.id not in reports:
                analysis.add("REPORT_MISSING", "error", f"no JUnit report of test run {run.id}")
    return analysis
