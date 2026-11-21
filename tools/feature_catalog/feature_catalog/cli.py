"""python -m feature_catalog check|build [--root DIR] [--reports DIR] [--out DIR]"""

import argparse
import sys
from pathlib import Path

from feature_catalog import view
from feature_catalog.analysis import Analysis, analyze
from feature_catalog.catalog import discover, load
from feature_catalog.junit import read_reports


def find_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / "catalog" / "catalog.yaml").exists():
            return path
    raise SystemExit("No catalog/catalog.yaml found above the current directory.")


def run(root: Path, reports: Path | None) -> tuple[Analysis, dict[str, object]]:
    catalog = load(root)
    discovered = discover(root)
    parsed = None
    if reports is not None and catalog.config is not None:
        parsed = read_reports(reports, catalog.config.testRuns)
    analysis = analyze(catalog, discovered, parsed)
    data = view.build_data(catalog, discovered, analysis) if catalog.config else {}
    return analysis, data


def _print(analysis: Analysis, data: dict[str, object], verbose: bool) -> None:
    shown = [f for f in analysis.findings if verbose or f.level != "info"]
    for finding in shown:
        where = f" [{finding.feature}]" if finding.feature else ""
        where += f" ({finding.file})" if finding.file and not finding.feature else ""
        print(f"{finding.level.upper():7} {finding.code}{where}: {finding.message}")
    stats = data.get("stats", {})
    if isinstance(stats, dict) and stats:
        print(
            f"\n{stats['features']} features ({stats['proven']} proven), {stats['review']} in "
            f"review, {stats['catalogued']}/{stats['areas']} areas catalogued, "
            f"{stats['assigned']}/{stats['parts']} parts assigned."
        )
    infos = sum(1 for f in analysis.findings if f.level == "info")
    print(
        f"{len(analysis.errors)} errors, {len(analysis.warnings)} warnings, {infos} notes"
        + ("" if verbose or not infos else " (--verbose shows notes)")
    )
    if not analysis.reports_checked:
        print("Static check only: no --reports given, so test results were not checked.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m feature_catalog")
    parser.add_argument("command", choices=["check", "build"])
    parser.add_argument("--root", type=Path, default=None, help="repository root")
    parser.add_argument("--reports", type=Path, default=None, help="folder with JUnit XML files")
    parser.add_argument("--out", type=Path, default=Path("catalog/dist"))
    parser.add_argument("--verbose", action="store_true", help="also print notes")
    args = parser.parse_args(argv)

    root = (args.root or find_root(Path.cwd())).resolve()
    reports = args.reports.resolve() if args.reports else None
    analysis, data = run(root, reports)
    _print(analysis, data, args.verbose)
    if args.command == "build" and data:
        out = args.out if args.out.is_absolute() else root / args.out
        print(f"Wrote {view.write(out, data)}")
    return 1 if analysis.errors and args.command == "check" else 0


if __name__ == "__main__":
    sys.exit(main())
