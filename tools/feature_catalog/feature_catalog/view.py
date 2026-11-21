"""Builds catalog.json and one self-contained HTML view (no server, no external scripts)."""

import json
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from feature_catalog.analysis import Analysis
from feature_catalog.catalog import Catalog, Discovered


def _feature(
    catalog: Catalog, discovered: Discovered, analysis: Analysis, area: str, feature: Any
) -> dict[str, Any]:
    data: dict[str, Any] = feature.model_dump(mode="json")
    data["area"] = area
    result = analysis.features.get(feature.id)
    data["proof"] = result.proof if result else "unproven"
    data["uncovered"] = result.uncovered if result else []
    for item, evidence in zip(data["evidence"], result.evidence if result else [], strict=False):
        item.update(
            status=evidence.status,
            line=evidence.line,
            assertions=evidence.assertions,
            statusOnly=evidence.status_only,
            related=evidence.related,
        )
    endpoints = []
    roles: set[str] = set()
    for key in feature.technical.endpoints:
        info = discovered.parts["endpoints"].get(key, {})
        roles.update(info.get("roles", []))
        endpoints.append(
            {
                "key": key,
                "summary": info.get("summary", ""),
                "roles": info.get("roles", []),
                "permission": info.get("permission"),
                "handler": info.get("handler"),
                "calledBy": analysis.called_by.get(key, []),
            }
        )
    data["technical"]["endpoints"] = endpoints
    data["technical"]["jobs"] = [
        {"name": j, **discovered.parts["jobs"].get(j, {})} for j in feature.technical.jobs
    ]
    data["technical"]["uiRoutes"] = [
        {"path": r, **discovered.parts["uiRoutes"].get(r, {})} for r in feature.technical.uiRoutes
    ]
    data["roles"] = sorted(roles)
    data["channels"] = sorted({u.channel for u in feature.usage})
    data["file"] = catalog.files.get(feature.id)
    return data


def build_data(catalog: Catalog, discovered: Discovered, analysis: Analysis) -> dict[str, Any]:
    assert catalog.config is not None
    features = [
        _feature(catalog, discovered, analysis, area, feature)
        for area, feature, _ in catalog.all_features()
    ]
    areas = []
    for area in catalog.config.areas:
        own = [f for f in features if f["area"] == area.id]
        parts = sum(1 for kind in analysis.owner.values() for a in kind.values() if a == area.id)
        assigned = sum(
            1
            for kind, owners in analysis.owner.items()
            for key, a in owners.items()
            if a == area.id and key in analysis.assigned.get(kind, {})
        )
        areas.append(
            {
                **area.model_dump(mode="json"),
                "features": sum(1 for f in own if not f.get("state")),
                "review": sum(1 for f in own if f.get("state")),
                "parts": parts,
                "assigned": assigned,
            }
        )
    listed = [f for f in features if not f.get("state")]
    return {
        "title": catalog.config.title,
        "generatedAt": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "reportsChecked": analysis.reports_checked,
        "channels": catalog.config.channels,
        "testRuns": [r.model_dump(mode="json") for r in catalog.config.testRuns],
        "stats": {
            "areas": len(areas),
            "catalogued": sum(1 for a in areas if a["status"] == "catalogued"),
            "features": len(listed),
            "proven": sum(1 for f in listed if f["proof"] == "proven"),
            "review": len(features) - len(listed),
            "parts": sum(len(p) for p in discovered.parts.values()),
            "assigned": sum(len(p) for p in analysis.assigned.values()),
            "errors": len(analysis.errors),
            "warnings": len(analysis.warnings),
        },
        "areas": areas,
        "features": features,
        "findings": [
            {
                "code": f.code,
                "level": f.level,
                "message": f.message,
                "feature": f.feature,
                "file": f.file,
            }
            for f in analysis.findings
            if f.level != "info"
        ],
    }


def write(out: Path, data: dict[str, Any]) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    (out / "catalog.json").write_text(text + "\n", encoding="utf-8")
    template = files("feature_catalog").joinpath("view.html").read_text(encoding="utf-8")
    embedded = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = template.replace("__TITLE__", data["title"]).replace("__DATA__", embedded)
    target = out / "index.html"
    target.write_text(page, encoding="utf-8")
    return target
