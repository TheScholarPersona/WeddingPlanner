"""Loads catalog/ and the discovered parts of the app (catalog/discovered/*.json)."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from feature_catalog.model import CatalogConfig, Feature, FeatureFile, ReviewFeature, ReviewFile

PART_KINDS = ("endpoints", "jobs", "commands", "uiRoutes")


@dataclass
class Problem:
    file: str
    message: str


@dataclass
class Catalog:
    root: Path
    config: CatalogConfig | None = None
    features: list[tuple[str, Feature]] = field(default_factory=list)  # (area id, feature)
    review: list[ReviewFeature] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)  # feature id -> yaml file

    def all_features(self) -> list[tuple[str, Feature, str | None]]:
        """(area, feature, review state or None)."""
        return [(a, f, None) for a, f in self.features] + [
            (r.area, r, r.state) for r in self.review
        ]


def _yaml(path: Path) -> Any:
    return YAML(typ="safe", pure=True).load(path.read_text(encoding="utf-8"))


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _errors(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors()[:5]
    )


def load(root: Path) -> Catalog:
    catalog = Catalog(root=root)
    base = root / "catalog"
    try:
        catalog.config = CatalogConfig.model_validate(_yaml(base / "catalog.yaml"))
    except (ValidationError, YAMLError, OSError) as error:
        message = _errors(error) if isinstance(error, ValidationError) else str(error)
        catalog.problems.append(Problem("catalog/catalog.yaml", message))
        return catalog
    for path in sorted((base / "features").glob("*.yaml")):
        try:
            data = FeatureFile.model_validate(_yaml(path))
        except (ValidationError, YAMLError) as error:
            message = _errors(error) if isinstance(error, ValidationError) else str(error)
            catalog.problems.append(Problem(_rel(root, path), message))
            continue
        for feature in data.features:
            catalog.features.append((data.area, feature))
            catalog.files[feature.id] = _rel(root, path)
    review = base / "review.yaml"
    if review.exists():
        try:
            catalog.review = ReviewFile.model_validate(_yaml(review) or {}).features
            for feature in catalog.review:
                catalog.files[feature.id] = "catalog/review.yaml"
        except (ValidationError, YAMLError) as error:
            message = _errors(error) if isinstance(error, ValidationError) else str(error)
            catalog.problems.append(Problem("catalog/review.yaml", message))
    return catalog


@dataclass
class Discovered:
    """Parts of the app by kind, keyed like the catalog refers to them."""

    parts: dict[str, dict[str, dict[str, Any]]]
    problems: list[Problem]
    api_prefix: str = ""


def discover(root: Path) -> Discovered:
    parts: dict[str, dict[str, dict[str, Any]]] = {kind: {} for kind in PART_KINDS}
    problems: list[Problem] = []
    folder = root / "catalog" / "discovered"
    prefix = ""
    backend = folder / "backend.json"
    if backend.exists():
        data = json.loads(backend.read_text(encoding="utf-8"))
        prefix = data.get("apiPrefix", "")
        for endpoint in data["endpoints"]:
            parts["endpoints"][f"{endpoint['method']} {endpoint['path']}"] = endpoint
        for job in data["jobs"]:
            parts["jobs"][job["name"]] = job
        for command in data["commands"]:
            parts["commands"][command["name"]] = command
    else:
        problems.append(Problem(_rel(root, backend), "missing; run the backend export test"))
    frontend = folder / "frontend-routes.json"
    if frontend.exists():
        for route in json.loads(frontend.read_text(encoding="utf-8"))["routes"]:
            parts["uiRoutes"][route["path"]] = route
    else:
        problems.append(Problem(_rel(root, frontend), "missing; run the frontend export test"))
    return Discovered(parts=parts, problems=problems, api_prefix=prefix)


def path_of(kind: str, key: str) -> str:
    return key.split(" ", 1)[1] if kind == "endpoints" else key


def match_length(kind: str, key: str, prefixes: list[str]) -> int:
    """How specifically `prefixes` claim `key` (0: not at all). The most specific area wins.

    `/v1/orders` owns itself and `/v1/orders/...`, not `/v1/orders-export`; an entry with a
    method (`GET /v1/orders`) owns exactly that endpoint.
    """
    if kind in ("jobs", "commands"):
        return 10_000 if key in prefixes else 0
    path = path_of(kind, key)
    best = 0
    for prefix in prefixes:
        if prefix == key:
            return 10_000
        if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
            best = max(best, len(prefix))
    return best
