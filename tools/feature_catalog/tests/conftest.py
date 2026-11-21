"""A tiny invented repository to check the tool against (no real customer data)."""

import json
import textwrap
from pathlib import Path
from typing import Any

import pytest

CATALOG = """
schemaVersion: 1
title: Test catalog
channels: { web: Browser, api: REST API }
testRuns:
  - id: backend
    title: Backend
    kind: integration
    format: pytest
    root: backend
    suite: backend
areas:
  - id: guests
    title: Guests
    summary: Guest list.
    status: catalogued
    owns:
      endpoints: ["/guests"]
    groups:
      - { id: guests.list, title: Guest list }
  - id: exports
    title: Exports
    summary: Exports.
    status: open
    owns:
      endpoints: ["/guests-export"]
    groups:
      - { id: exports.files, title: Files }
"""

FEATURES = """
area: guests
features:
  - id: guests.rsvp
    title: Reply to an invitation
    group: guests.list
    summary: Guests accept with a plus-one.
    usage:
      - { channel: api, text: "`POST /guests/{guest_id}/rsvp`" }
    rules:
      - "Closed after the deadline (`rsvp_closed`)."
    technical:
      components: [backend/app/rsvp.py]
      endpoints: ["POST /guests/{guest_id}/rsvp", "GET /guests"]
    acceptance:
      - { id: plus-one, kind: effect, text: "A reply with a plus-one counts two guests." }
      - id: deadline
        kind: rule
        text: "Replies after the deadline are refused."
        code: rsvp_closed
    evidence:
      - kind: integration
        file: backend/tests/test_rsvp.py
        test: test_saves_rsvp_with_plus_one
        covers: [plus-one]
      - kind: integration
        file: backend/tests/test_rsvp.py
        test: test_rejects_changes_after_deadline
        covers: [deadline]
"""

TESTS = """
def url(guest):
    return f"/api/v1/guests/{guest}/rsvp"


def test_saves_rsvp_with_plus_one(client):
    response = client.post(url("g1"), json={"plus_one": True})
    assert response.status_code == 201
    assert client.get("/api/v1/guests").json()["count"] == 2


def test_rejects_changes_after_deadline(client):
    response = client.post("/api/v1/guests/g1/rsvp", json={})
    assert response.json()["code"] == "rsvp_closed"


def test_only_status(client):
    response = client.post("/api/v1/guests/g1/rsvp", json={})
    assert response.status_code == 201


def test_no_assertion(client):
    client.post("/api/v1/guests/g1/rsvp", json={})


def test_unrelated(client):
    assert sum([1, 1]) == 2


PATHS = ["/api/v1/guests-export"]  # a bare path list is no call
"""

DISCOVERED = {
    "apiPrefix": "/api/v1",
    "endpoints": [
        {
            "method": "GET",
            "path": "/guests",
            "summary": "List guests",
            "roles": ["planner"],
            "permission": None,
            "handler": "backend/app/rsvp.py:list_guests",
        },
        {
            "method": "POST",
            "path": "/guests/{guest_id}/rsvp",
            "summary": "Reply",
            "roles": ["public"],
            "permission": None,
            "handler": "backend/app/rsvp.py:reply",
        },
        {
            "method": "GET",
            "path": "/guests-export",
            "summary": "Export",
            "roles": ["planner"],
            "permission": None,
            "handler": "backend/app/rsvp.py:export",
        },
    ],
    "jobs": [],
    "commands": [],
}


def junit(cases: dict[str, str], suite: str = "backend") -> str:
    """cases: test name -> passed|failed|skipped"""
    body = {
        "passed": "",
        "failed": "<failure message='boom'/>",
        "skipped": "<skipped message='no docker'/>",
    }
    rows = "".join(
        f'<testcase classname="tests.test_rsvp" name="{name}">{body[outcome]}</testcase>'
        for name, outcome in cases.items()
    )
    return f'<testsuites><testsuite name="{suite}">{rows}</testsuite></testsuites>'


class Repo:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write(self, path: str, text: str) -> Path:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
        return target

    def features(self, text: str) -> None:
        self.write("catalog/features/guests.yaml", text)

    def discovered(self, data: dict[str, Any]) -> None:
        self.write("catalog/discovered/backend.json", json.dumps(data))

    def reports(self, cases: dict[str, str], name: str = "anything.xml", **kw: str) -> Path:
        self.write(f"reports/{name}", junit(cases, **kw))
        return self.root / "reports"


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    r = Repo(tmp_path)
    r.write("catalog/catalog.yaml", CATALOG)
    r.features(FEATURES)
    r.discovered(DISCOVERED)
    r.write("catalog/discovered/frontend-routes.json", json.dumps({"routes": []}))
    r.write("backend/app/rsvp.py", "def reply(): ...\n")
    r.write("backend/tests/__init__.py", "")
    r.write("backend/tests/test_rsvp.py", TESTS)
    return r
