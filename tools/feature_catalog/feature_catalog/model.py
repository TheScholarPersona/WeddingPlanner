"""Schema of catalog/ (catalog.yaml, features/*.yaml, review.yaml). Unknown keys are errors."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Channel = Literal["web", "portal", "api", "email", "calendar", "batch", "development"]
AreaStatus = Literal["catalogued", "open"]
ReviewState = Literal["incomplete", "disabled", "not-proven"]
EvidenceKind = Literal["unit", "integration", "e2e"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Owns(Strict):
    endpoints: list[str] = []
    jobs: list[str] = []
    commands: list[str] = []
    uiRoutes: list[str] = []


class Group(Strict):
    id: str
    title: str
    summary: str = ""


class Area(Strict):
    id: str
    title: str
    summary: str
    status: AreaStatus = "open"
    owns: Owns = Owns()
    groups: list[Group] = []


class Exclusion(Strict):
    item: str
    reason: str = Field(min_length=3)


class Exclusions(Strict):
    endpoints: list[Exclusion] = []
    jobs: list[Exclusion] = []
    commands: list[Exclusion] = []
    uiRoutes: list[Exclusion] = []


class TestRun(Strict):
    """A test report and how to recognize it by its content (not by its file name)."""

    id: str
    title: str
    kind: EvidenceKind
    format: Literal["pytest", "vitest", "playwright"]
    root: str  # directory the test files are relative to in the report
    suite: str | None = None  # root or first testsuite name; playwright is recognized by *.spec.ts


class CatalogConfig(Strict):
    schemaVersion: Literal[1]
    title: str
    channels: dict[str, str]
    testRuns: list[TestRun]
    areas: list[Area]
    exclusions: Exclusions = Exclusions()


class Usage(Strict):
    channel: Channel
    text: str


class Technical(Strict):
    components: list[str] = []
    endpoints: list[str] = []
    jobs: list[str] = []
    commands: list[str] = []
    uiRoutes: list[str] = []
    settings: list[str] = []
    notes: list[str] = []


class Criterion(Strict):
    id: str
    kind: Literal["effect", "rule"]
    text: str
    code: str | None = None


class Evidence(Strict):
    kind: EvidenceKind
    file: str  # repository-relative
    test: str  # pytest: function or Class::function; vitest/playwright: full title or last part
    covers: list[str] = []


class Feature(Strict):
    id: str
    title: str
    group: str
    summary: str
    description: str = ""
    usage: list[Usage] = Field(min_length=1)
    rules: list[str] = []
    dependsOn: list[str] = []
    technical: Technical = Technical()
    acceptance: list[Criterion] = []
    evidence: list[Evidence] = []


class ReviewFeature(Feature):
    area: str
    state: ReviewState
    reason: str = Field(min_length=3)


class FeatureFile(Strict):
    area: str
    features: list[Feature]


class ReviewFile(Strict):
    features: list[ReviewFeature] = []
