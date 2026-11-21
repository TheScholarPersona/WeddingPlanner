"""Keeps catalog/discovered/backend.json in step with the app (endpoints, roles, jobs, commands).

The feature catalog (tools/feature_catalog) reads this file instead of importing the app.
Regenerate after changing routes, permissions, worker jobs or CLI commands:

    UPDATE_SNAPSHOTS=1 uv run pytest tests/test_catalog_export.py
"""

import ast
import inspect
import json
import os
from pathlib import Path
from typing import Any

from app.admin.router import platform_admin
from app.authz.permissions import (
    ADMIN_PROJECT_ROLE,
    PROJECT_ROLE_PERMS,
    ROLE_PERMS,
    Perm,
    ProjectPerm,
)
from app.jobs.worker import WorkerSettings
from app.main import create_app
from app.organizations.models import OrgRole
from app.portal.service import portal_access
from tests.routes import MIN_ROUTES, api_routes, dependency_calls
from tests.test_route_protection import PUBLIC

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "catalog" / "discovered" / "backend.json"
PREFIX = "/api/v1"

ORG_ROLE_NAMES = {
    OrgRole.ORG_ADMIN: "org admin",
    OrgRole.MEMBER: "team member",
    OrgRole.CLIENT: "couple",
}
PROJECT_ROLE_NAMES = {
    ADMIN_PROJECT_ROLE: "org admin",
    "lead": "lead",
    "planner": "planner",
    "viewer": "viewer",
}


def _relative(obj: Any) -> str:
    return Path(inspect.getfile(obj)).resolve().relative_to(ROOT).as_posix()


def _roles(method: str, path: str, route: Any) -> tuple[list[str], str | None]:
    calls = list(dependency_calls(route.dependant))
    for call in calls:
        perm = getattr(call, "__authz_permission__", None)
        if isinstance(perm, ProjectPerm):
            names = [n for r, n in PROJECT_ROLE_NAMES.items() if perm in PROJECT_ROLE_PERMS[r]]
            return names, str(perm)
        if isinstance(perm, Perm):
            return [n for r, n in ORG_ROLE_NAMES.items() if perm in ROLE_PERMS[r]], str(perm)
    if portal_access in calls:
        return ["couple"], None
    if platform_admin in calls:
        return ["platform admin"], None
    if (method, path) in PUBLIC:
        return ["public"], None
    return ["signed in"], None


def _endpoints() -> list[dict[str, Any]]:
    result = []
    for method, path, route in api_routes(create_app()):
        if not path.startswith(PREFIX):
            continue
        roles, permission = _roles(method, path, route)
        doc = inspect.getdoc(route.endpoint) or ""
        result.append(
            {
                "method": method,
                "path": path.removeprefix(PREFIX),
                "summary": route.summary or doc.split("\n\n")[0].replace("\n", " "),
                "handler": f"{_relative(route.endpoint)}:{route.endpoint.__name__}",
                "roles": roles,
                "permission": permission,
            }
        )
    return sorted(result, key=lambda e: (e["path"], e["method"]))


def _jobs() -> list[dict[str, Any]]:
    jobs = [
        {
            "name": getattr(f, "name", getattr(f, "__name__", "")),
            "kind": "task",
            "schedule": None,
            "handler": _relative(getattr(f, "coroutine", f)),
        }
        for f in WorkerSettings.functions
    ]
    for cron in WorkerSettings.cron_jobs:
        hour = "*" if cron.hour is None else f"{cron.hour:02d}"
        jobs.append(
            {
                "name": cron.name.removeprefix("cron:"),
                "kind": "cron",
                "schedule": f"{hour}:{cron.minute:02d}",
                "handler": _relative(cron.coroutine),
            }
        )
    return sorted(jobs, key=lambda j: j["name"])


def _commands() -> list[dict[str, Any]]:
    source = ROOT / "backend" / "app" / "cli.py"
    commands = []
    for node in ast.walk(ast.parse(source.read_text())):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_parser"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            help_text = next((k.value.value for k in node.keywords if k.arg == "help"), "")  # type: ignore[attr-defined]
            commands.append(
                {"name": node.args[0].value, "summary": help_text, "file": "backend/app/cli.py"}
            )
    return sorted(commands, key=lambda c: c["name"])


def discovered() -> dict[str, Any]:
    return {
        "generatedBy": "backend/tests/test_catalog_export.py",
        "apiPrefix": PREFIX,
        "endpoints": _endpoints(),
        "jobs": _jobs(),
        "commands": _commands(),
    }


def test_catalog_export_is_current() -> None:
    data = discovered()
    assert len(data["endpoints"]) >= MIN_ROUTES
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(text, encoding="utf-8")
    assert SNAPSHOT.exists(), "Run: UPDATE_SNAPSHOTS=1 uv run pytest tests/test_catalog_export.py"
    assert SNAPSHOT.read_text(encoding="utf-8") == text, (
        "catalog/discovered/backend.json is out of date. "
        "Run: UPDATE_SNAPSHOTS=1 uv run pytest tests/test_catalog_export.py"
    )
