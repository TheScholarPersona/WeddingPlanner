"""The catalog tool: it checks, reports and builds; it never invents features."""

from pathlib import Path

from feature_catalog.analysis import Analysis
from feature_catalog.calls import PythonCalls, ts_calls
from feature_catalog.cli import main, run
from tests.conftest import DISCOVERED, FEATURES, TESTS, Repo

ROOT = Path(__file__).resolve().parents[3]

ALL_PASSED = {
    "test_saves_rsvp_with_plus_one": "passed",
    "test_rejects_changes_after_deadline": "passed",
}


def codes(analysis: Analysis) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for finding in analysis.findings:
        result.setdefault(finding.code, []).append(finding.message)
    return result


def check(repo: Repo, reports: Path | None = None) -> Analysis:
    analysis, _ = run(repo.root, reports)
    return analysis


# --- The real catalog ----------------------------------------------------------------------


def test_real_catalog_has_no_errors() -> None:
    analysis, data = run(ROOT, None)
    assert [f"{f.code}: {f.message}" for f in analysis.errors] == []
    assert data["stats"]["features"] >= 10  # type: ignore[index]


def test_assigns_every_discovered_part_to_an_area() -> None:
    analysis, _ = run(ROOT, None)
    assert "UNOWNED" not in codes(analysis)
    owned = sum(len(keys) for keys in analysis.owner.values())
    assert owned >= 200


# --- Structure -----------------------------------------------------------------------------


def test_correct_catalog_is_proven_with_passing_reports(repo: Repo) -> None:
    analysis, data = run(repo.root, repo.reports(ALL_PASSED))
    assert [f.code for f in analysis.errors] == []
    assert analysis.features["guests.rsvp"].proof == "proven"
    assert data["stats"]["proven"] == 1  # type: ignore[index]


def test_requires_evidence(repo: Repo) -> None:
    repo.features(FEATURES.split("    evidence:")[0])
    found = codes(check(repo))
    assert "EVIDENCE_MISSING" in found
    assert "ACCEPTANCE_UNCOVERED" in found


def test_never_adds_features(repo: Repo) -> None:
    before = {p: p.read_text() for p in (repo.root / "catalog").rglob("*.yaml")}
    data = dict(DISCOVERED)
    data["endpoints"] = [
        *DISCOVERED["endpoints"],
        {
            "method": "DELETE",
            "path": "/guests/{guest_id}",
            "summary": "",
            "roles": [],
            "permission": None,
            "handler": "",
        },
    ]
    repo.discovered(data)

    analysis = check(repo)
    main(["build", "--root", str(repo.root), "--out", str(repo.root / "dist")])

    assert any("DELETE /guests/{guest_id}" in m for m in codes(analysis)["UNASSIGNED"])
    assert len(analysis.features) == 1
    assert {p: p.read_text() for p in (repo.root / "catalog").rglob("*.yaml")} == before


def test_unassigned_parts_of_open_areas_are_notes(repo: Repo) -> None:
    analysis = check(repo)
    notes = [f for f in analysis.findings if f.code == "UNASSIGNED"]
    assert [(f.level, "GET /guests-export" in f.message) for f in notes] == [("info", True)]


def test_area_prefix_does_not_claim_similar_paths(repo: Repo) -> None:
    analysis = check(repo)
    assert analysis.owner["endpoints"]["GET /guests-export"] == "exports"
    assert analysis.owner["endpoints"]["GET /guests"] == "guests"


def test_reports_references_to_removed_parts(repo: Repo) -> None:
    text = (
        FEATURES.replace('"GET /guests"]', '"GET /guests", "PUT /guests/{guest_id}"]')
        .replace("backend/app/rsvp.py]", "backend/app/rsvp.py, backend/app/gone.py]")
        .replace("test: test_saves_rsvp_with_plus_one", "test: test_renamed_meanwhile")
        .replace("    acceptance:", "    dependsOn: [guests.gone]\n    acceptance:")
    )
    repo.features(text)

    found = codes(check(repo))

    assert found["UNKNOWN_ENDPOINT"] == ["PUT /guests/{guest_id} does not exist"]
    assert found["UNKNOWN_COMPONENT"] == ["backend/app/gone.py is missing"]
    assert any("test_renamed_meanwhile" in m for m in found["UNKNOWN_TEST"])
    assert found["UNKNOWN_DEPENDENCY"] == ["guests.gone is unknown"]


def test_schema_rejects_unknown_keys(repo: Repo) -> None:
    repo.features(FEATURES.replace("    title: Reply", "    owner: someone\n    title: Reply"))
    assert any("owner" in m for m in codes(check(repo))["SCHEMA"])


# --- Evidence ------------------------------------------------------------------------------


def test_flags_failed_skipped_and_missing_evidence(repo: Repo) -> None:
    reports = repo.reports(
        {
            "test_saves_rsvp_with_plus_one": "failed",
            "test_rejects_changes_after_deadline": "skipped",
        }
    )
    found = codes(check(repo, reports))
    assert "EVIDENCE_FAILED" in found and "EVIDENCE_SKIPPED" in found

    reports = repo.reports({"test_saves_rsvp_with_plus_one": "passed"})
    analysis = check(repo, reports)
    assert "EVIDENCE_NOT_RUN" in codes(analysis)
    assert analysis.features["guests.rsvp"].proof == "partial"


def test_parametrized_tests_need_every_instance_to_pass(repo: Repo) -> None:
    reports = repo.reports(
        {
            "test_saves_rsvp_with_plus_one[a]": "passed",
            "test_saves_rsvp_with_plus_one[b]": "skipped",
            "test_rejects_changes_after_deadline": "passed",
        }
    )
    assert "EVIDENCE_SKIPPED" in codes(check(repo, reports))


def test_recognizes_reports_by_content_not_name(repo: Repo) -> None:
    other = repo.reports(ALL_PASSED, name="unit.xml", suite="something-else")
    assert "REPORT_MISSING" in codes(check(repo, other))

    renamed = repo.reports(ALL_PASSED, name="unit.xml", suite="backend")
    assert "REPORT_MISSING" not in codes(check(repo, renamed))


def test_requires_passed_evidence_for_every_criterion(repo: Repo) -> None:
    repo.features(FEATURES.replace("covers: [deadline]", "covers: [plus-one]"))
    analysis = check(repo, repo.reports(ALL_PASSED))
    assert codes(analysis)["ACCEPTANCE_UNCOVERED"] == [
        "criterion 'deadline' has no passed evidence"
    ]
    assert analysis.features["guests.rsvp"].proof == "partial"


def test_evidence_needs_covers(repo: Repo) -> None:
    repo.features(FEATURES.replace("covers: [deadline]", "covers: []"))
    assert "EVIDENCE_UNLINKED" in codes(check(repo))


def test_flags_evidence_without_assertion_status_only_or_unrelated(repo: Repo) -> None:
    for test, code in (
        ("test_no_assertion", "EVIDENCE_NO_ASSERTION"),
        ("test_only_status", "EVIDENCE_STATUS_ONLY"),
        ("test_unrelated", "EVIDENCE_UNRELATED"),
    ):
        repo.features(FEATURES.replace("test: test_saves_rsvp_with_plus_one", f"test: {test}"))
        assert code in codes(check(repo)), test


def test_requires_rule_code_as_assertion(repo: Repo) -> None:
    repo.features(
        FEATURES.replace("test: test_rejects_changes_after_deadline", "test: test_only_status")
    )
    assert "RULE_CODE_NOT_ASSERTED" in codes(check(repo))

    repo.features(FEATURES.replace("        code: rsvp_closed\n", ""))
    assert codes(check(repo))["RULE_WITHOUT_ACCEPTANCE"] == [
        "rule code `rsvp_closed` has no criterion"
    ]


def test_criterion_of_kind_effect_is_required(repo: Repo) -> None:
    repo.features(FEATURES.replace("kind: effect", "kind: rule"))
    assert "ACCEPTANCE_MISSING" in codes(check(repo))


# --- Calls ---------------------------------------------------------------------------------


def test_recognizes_calls_with_method_but_not_bare_path_lists(repo: Repo) -> None:
    calls = PythonCalls(repo.root / "backend").calls(repo.root / "backend/tests/test_rsvp.py")
    assert ("POST", "/api/v1/guests/g1/rsvp") in calls  # through the url() helper
    assert ("GET", "/api/v1/guests") in calls
    assert not any("guests-export" in path for _, path in calls)

    spec = repo.write(
        "frontend/e2e/guests.spec.ts",
        "const paths = ['/api/v1/guests-export'];\n"
        "test('x', async ({ request }) => { await request.post(`/api/v1/guests/${id}/rsvp`); });\n",
    )
    assert ts_calls(spec) == [("POST", "/api/v1/guests/{}/rsvp")]

    analysis = check(repo)
    assert analysis.called_by["GET /guests-export"] == []
    assert analysis.called_by["POST /guests/{guest_id}/rsvp"] == ["backend/tests/test_rsvp.py"]


# --- View ----------------------------------------------------------------------------------


def test_builds_a_self_contained_view(repo: Repo) -> None:
    out = repo.root / "dist"
    assert main(["build", "--root", str(repo.root), "--out", str(out)]) == 0

    page = (out / "index.html").read_text()
    assert "<script src" not in page and "<link" not in page  # no external resources
    assert "Reply to an invitation" in page and "guests.rsvp" in page
    assert (out / "catalog.json").exists()
    assert "</script><script>" not in page.split('id="data">')[1].split("</script>")[0]


def test_check_exits_with_an_error_code(repo: Repo) -> None:
    assert main(["check", "--root", str(repo.root)]) == 0
    repo.features(FEATURES.split("    evidence:")[0])
    assert main(["check", "--root", str(repo.root)]) == 1


def test_follows_helpers_imported_from_other_test_modules(repo: Repo) -> None:
    repo.write(
        "backend/tests/helpers.py",
        """
        def reply(client, guest):
            return client.post(f"/api/v1/guests/{guest}/rsvp", json={"plus_one": True})
        """,
    )
    repo.write(
        "backend/tests/test_rsvp.py",
        TESTS.replace(
            "def test_unrelated(client):",
            "from tests.helpers import reply\n\n\ndef test_unrelated(client):\n"
            "    assert reply(client, 'g1').json()['count'] == 2\n\n\ndef test_old(client):",
        ),
    )
    repo.features(FEATURES.replace("test: test_saves_rsvp_with_plus_one", "test: test_unrelated"))
    assert "EVIDENCE_UNRELATED" not in codes(check(repo))


def test_paths_of_only_generic_segments_are_matched_as_a_whole(repo: Repo) -> None:
    data = dict(DISCOVERED)
    data["endpoints"] = [
        *DISCOVERED["endpoints"],
        {
            "method": "GET",
            "path": "/portal/projects",
            "summary": "",
            "roles": ["couple"],
            "permission": None,
            "handler": "",
        },
    ]
    repo.discovered(data)
    repo.write(
        "backend/tests/test_rsvp.py",
        TESTS
        + "\n\ndef test_portal(client):\n"
        + "    assert client.get('/api/v1/portal/projects').json() == []\n"
        + "\n\ndef test_portal_export(client):\n"
        + "    assert client.get('/api/v1/portal/projects-export').json() == []\n",
    )
    text = FEATURES.replace('"GET /guests"]', '"GET /guests", "GET /portal/projects"]').replace(
        '"POST /guests/{guest_id}/rsvp", ', ""
    )
    for test, related in (("test_portal", True), ("test_portal_export", False)):
        repo.features(text.replace("test: test_saves_rsvp_with_plus_one", f"test: {test}"))
        found = codes(check(repo))
        assert ("EVIDENCE_UNRELATED" not in found) is related, test
