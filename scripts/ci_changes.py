"""Change-aware PR validation: classify a PR's diff and gate on the selected suites (#687).

Stdlib only:

    python scripts/ci_changes.py classify --event pull_request --head-sha SHA [--pr N --repo O/R]
    python scripts/ci_changes.py gate --mode MODE --classify-result RESULT --needs-json JSON
    python scripts/ci_changes.py paths FILE [FILE ...]   # classify paths locally, no git/API

Full validation is the default. ``classify`` grants a reduced mode only when every check
below positively passes; anything else, including an error, is full validation:

* the event is a ``pull_request`` (pushes to main, tags and manual runs are always full);
* the checkout is GitHub's PR merge commit, whose second parent is the PR head: its diff
  against the first parent is the PR's complete effect on the current base, including
  additions, deletions, both sides of renames and a changed base;
* the PR has no ``ci:full`` label, read from the API at run time (so re-runs see it);
* every changed path fits the mode: it is in the mode's allowlist, not in its force-full
  exceptions, and not a deletion the mode forbids (``MODES`` below);
* the repository variable CI_CHANGE_SELECTION enables the mode (rollout switch; without
  it the would-be reduction is reported and the full suites still run).

The narrowest enabled mode that fits is used: a documentation-only PR runs ``docs`` even
when ``frontend`` or ``deploy`` is enabled as well.

``classify`` appends ``mode=<mode>`` to $GITHUB_OUTPUT and a report to $GITHUB_STEP_SUMMARY.
Jobs omitted in a mode skip only on the exact output ``mode == '<mode>'``, so a failed
or missing classification runs them.

``gate`` is the "CI result" check. It requires a successful classification, a known mode,
that the workflow's gate ``needs`` are exactly the suites registered in ``SUITES``, that
every suite the mode requires succeeded, and that every suite it omits either skipped or
succeeded. Failed, cancelled or missing results always fail it.

Keep this registry short: a mode is a stable component boundary, not a per-file test map.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field

FULL = "full"
DOCS = "docs"
FRONTEND = "frontend"
DEPLOY = "deploy"
FORCE_FULL_LABEL = "ci:full"
SELECTION_VARIABLE = "CI_CHANGE_SELECTION"

# Gate-checked jobs: workflow job id -> check name. The full mode requires all of them.
SUITES = {
    "docs-check": "Documentation checks",
    "test-backend": "Backend tests",
    "test-frontend": "Frontend checks",
    "test-integration": "Integration tests",
    "test-browser": "Browser smoke tests",
    "python-locks": "Python dependency locks",
    "api-client-drift": "Generated API client drift",
}

# Paths that nothing builds, installs, imports or reads at test or run time. Package
# READMEs are excluded (pyproject.toml ``readme``), as are generated client docs, YAML,
# JSON, scripts and anything else; a new kind of file needs a reviewed entry here.
DOCS_ONLY = (
    "*.md",  # the repository root only: in _matches, * never crosses "/"
    "docs/**.md",
    "deploy/README.md",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/*.md",
)

# The frontend's source, tests and static assets, which only "Frontend checks", the browser
# suite and the image build consume. Not included, so they run everything: package.json and
# the lock (dependencies), build, lint, type and test configuration, scripts/ (the API
# client generator) and anything else in the frontend's root.
FRONTEND_ONLY = DOCS_ONLY + (
    "semant_demo_frontend/src/**",
    "semant_demo_frontend/test/**",
    "semant_demo_frontend/public/**",
    "semant_demo_frontend/index.html",
    "semant_demo_frontend/README.md",
)
# Frontend files that the omitted suites read; changing them runs everything. Backend
# tests that read a frontend file must add it here (test_ci_changes.py checks the literal
# paths in backend code).
FRONTEND_FORCE_FULL = (
    "semant_demo_frontend/src/generated/**",  # the API client: "Generated API client drift"
    "semant_demo_frontend/src/features/documents/originalSource.ts",  # test_mcp.py
    "semant_demo_frontend/test/e2e/shard_durations.json",  # test_browser_shards.py
)
# Backend tests check that browser specs exist (test_browser_shards.py: those named in
# shard_durations.json; test_e2e_dev_script.py: smoke.spec.ts), so deleting or renaming
# one runs everything.
FRONTEND_NO_DELETE = ("semant_demo_frontend/test/e2e/*.spec.ts",)

# Deployment configuration and its contract tests. Only "Backend tests" (the
# test_deploy_*.py contracts, test_dependency_locks.py and test_search_vectors.py read
# deploy/) and the PR preview, which builds and runs the image, consume deploy/; the
# frontend, integration, browser and lock suites run from source and never read it
# (test_ci_changes.py checks that they do not name it). The workflow (.github/) and the
# shared scripts/ are not included.
DEPLOY_ONLY = DOCS_ONLY + (
    "deploy/**",
    "semant_demo_backend/tests/test_deploy_*.py",
)


@dataclass(frozen=True)
class Mode:
    name: str
    description: str
    allowlist: tuple[str, ...]
    required: frozenset[str]
    omits_preview: bool = False
    force_full: tuple[str, ...] = ()
    no_delete: tuple[str, ...] = ()

    def fits(self, path: str, deleted: frozenset[str] = frozenset()) -> bool:
        return (in_allowlist(path, self.allowlist) and not in_allowlist(path, self.force_full)
                and not (path in deleted and in_allowlist(path, self.no_delete)))


MODES = {
    FULL: Mode(FULL, "Full validation", (), frozenset(SUITES)),
    DOCS: Mode(DOCS, "Documentation only", DOCS_ONLY, frozenset({"docs-check"}), omits_preview=True),
    FRONTEND: Mode(FRONTEND, "Frontend only", FRONTEND_ONLY,
                   frozenset({"docs-check", "test-frontend", "test-browser"}),
                   force_full=FRONTEND_FORCE_FULL, no_delete=FRONTEND_NO_DELETE),
    DEPLOY: Mode(DEPLOY, "Deployment only", DEPLOY_ONLY,
                 frozenset({"docs-check", "test-backend", "api-client-drift"})),
}
# Reduced modes, narrowest first. Each contains the documentation allowlist and otherwise
# they are disjoint, so at most one mode beyond `docs` fits a PR.
REDUCED = (MODES[DOCS], MODES[FRONTEND], MODES[DEPLOY])


def _matches(path: str, pattern: str) -> bool:
    """fnmatch where ``*`` stays within one directory and ``**`` crosses directories."""
    if "**" in pattern:
        return fnmatch.fnmatchcase(path, pattern.replace("**", "*"))
    return path.count("/") == pattern.count("/") and fnmatch.fnmatchcase(path, pattern)


def in_allowlist(path: str, allowlist: tuple[str, ...]) -> bool:
    return any(_matches(path, pattern) for pattern in allowlist)


@dataclass
class Decision:
    mode: str = FULL
    classification: str = FULL
    reason: str = ""
    files: list[str] = field(default_factory=list)
    outside: list[str] = field(default_factory=list)

    def summary(self) -> str:
        mode = MODES[self.mode]
        lines = [
            "### Change classification (#687)",
            "",
            f"**Mode: {mode.description} (`{self.mode}`).** {self.reason}",
            "",
            "| Suite | Selection |",
            "| --- | --- |",
        ]
        for job, name in SUITES.items():
            lines.append(f"| {name} | {'required' if job in mode.required else 'intentionally omitted'} |")
        lines.append(f"| PR preview | {'intentionally omitted' if mode.omits_preview else 'deployed'} |")
        if self.files:
            lines += ["", f"<details><summary>{len(self.files)} changed path(s)</summary>", ""]
            lines += [f"- `{path}`" + (" (fits no reduced mode)" if path in self.outside else "")
                      for path in self.files[:300]]
            if len(self.files) > 300:
                lines.append(f"- ... and {len(self.files) - 300} more")
            lines += ["", "</details>"]
        return "\n".join(lines) + "\n"


def classify_paths(files: list[str], enabled: set[str], deleted: frozenset[str] = frozenset()) -> Decision:
    """The decision for a PR whose complete diff is ``files``, of which ``deleted`` were deleted."""
    if not files:
        return Decision(reason="The diff is empty or could not be listed; running everything.")
    fitting = [mode for mode in REDUCED if all(mode.fits(path, deleted) for path in files)]
    if not fitting:
        outside = [path for path in files if not any(m.fits(path, deleted) for m in REDUCED)]
        reason = (f"{len(outside)} changed path(s) fit no reduced mode." if outside else
                  "The changed paths span several components (no single reduced mode fits them all).")
        return Decision(files=files, outside=outside, reason=reason)
    narrowest = fitting[0]
    selected = next((mode for mode in fitting if mode.name in enabled), None)
    if selected is None:
        return Decision(classification=narrowest.name, files=files,
                        reason=f"{narrowest.description}, but `{SELECTION_VARIABLE}` does not enable "
                               f"`{narrowest.name}` (observe-only rollout); running everything.")
    return Decision(mode=selected.name, classification=narrowest.name, files=files,
                    reason=f"Every changed path fits the `{selected.name}` mode. Add the "
                           f"`{FORCE_FULL_LABEL}` label and re-run to run everything.")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def changed_files(head_sha: str) -> dict[str, str]:
    """The paths a PR merge commit changes relative to its base parent, with git's status
    letter (``A``, ``D``, ``M``, ...).

    Raises ValueError unless HEAD is a two-parent merge whose second parent is the PR head.
    """
    parents = _git("rev-list", "--parents", "-n", "1", "HEAD").split()[1:]
    if len(parents) != 2:
        raise ValueError(f"HEAD has {len(parents)} parent(s), expected GitHub's PR merge commit")
    if parents[1] != head_sha:
        raise ValueError(f"the merge commit's second parent {parents[1]} is not the PR head {head_sha}")
    # --no-renames lists a rename as a deletion and an addition; -z keeps unusual names
    # intact and gives "status NUL path NUL" pairs.
    fields = _git("diff", "--no-renames", "--name-status", "-z", parents[0], "HEAD").split("\0")[:-1]
    if len(fields) % 2:
        raise ValueError("unexpected git diff --name-status output")
    return {path: status for status, path in zip(fields[::2], fields[1::2])}


def pr_labels(repo: str, pr: int, token: str) -> list[str]:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues/{pr}/labels?per_page=100",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return [label["name"] for label in json.load(response)]


def classify(args: argparse.Namespace) -> Decision:
    if args.event != "pull_request":
        return Decision(reason=f"`{args.event}` runs always run everything.")
    try:
        labels = pr_labels(args.repo, args.pr, os.environ["GITHUB_TOKEN"])
    except Exception as exc:  # noqa: BLE001 - any failure means full validation
        return Decision(reason=f"Could not read the PR labels ({type(exc).__name__}); running everything.")
    if FORCE_FULL_LABEL in labels:
        return Decision(reason=f"The `{FORCE_FULL_LABEL}` label requests full validation.")
    try:
        changes = changed_files(args.head_sha)
    except (ValueError, subprocess.CalledProcessError, OSError) as exc:
        return Decision(reason=f"Could not determine the PR diff ({exc}); running everything.")
    enabled = {item.strip() for item in os.environ.get(SELECTION_VARIABLE, "").split(",") if item.strip()}
    deleted = frozenset(path for path, status in changes.items() if status == "D")
    return classify_paths(sorted(changes), enabled, deleted)


def _append(variable: str, text: str) -> None:
    if path := os.environ.get(variable):
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)


def gate(mode_name: str, classify_result: str, needs: dict) -> tuple[bool, str]:
    """Whether the selected suites all ran and passed, with a Markdown report."""
    errors: list[str] = []
    rows: list[str] = []
    if classify_result != "success":
        errors.append(f"Change classification finished with result '{classify_result or 'missing'}'.")
    mode = MODES.get(mode_name)
    if mode is None:
        errors.append(f"Unknown or missing classification mode '{mode_name}'.")
        mode = MODES[FULL]  # judge every suite as required
    gated = set(needs) - {"classify"}
    if gated != set(SUITES):
        errors.append("The gate's needs do not match the suite registry in scripts/ci_changes.py: "
                      f"missing {sorted(set(SUITES) - gated)}, unregistered {sorted(gated - set(SUITES))}.")
    for job, name in SUITES.items():
        result = needs.get(job, {}).get("result", "missing")
        if job in mode.required:
            ok, selection = result == "success", "required"
        else:
            ok, selection = result in ("skipped", "success"), "intentionally omitted"
        if not ok:
            errors.append(f"{name} ({selection}) finished with result '{result}'.")
        shown = "skipped, not tested" if result == "skipped" else result
        rows.append(f"| {name} | {selection} | {shown} | {'ok' if ok else '**FAIL**'} |")
    report = ["### CI result (#687)", "", f"Mode: {mode.description} (`{mode_name or 'missing'}`).", "",
              "| Suite | Selection | Result | Gate |", "| --- | --- | --- | --- |", *rows, ""]
    report += [f"- {error}" for error in errors] or ["All required suites passed."]
    return not errors, "\n".join(report) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("classify")
    c.add_argument("--event", required=True)
    c.add_argument("--head-sha", default="")
    c.add_argument("--repo", default="")
    c.add_argument("--pr", type=int, default=0)
    g = sub.add_parser("gate")
    g.add_argument("--mode", default="")
    g.add_argument("--classify-result", default="")
    g.add_argument("--needs-json", required=True)
    p = sub.add_parser("paths")
    p.add_argument("files", nargs="+")
    args = parser.parse_args(argv)

    if args.command == "paths":
        decision = classify_paths(args.files, set(MODES))
        print(decision.summary())
        return 0
    if args.command == "classify":
        try:
            decision = classify(args)
        except Exception as exc:  # noqa: BLE001 - never fail open: report and run everything
            decision = Decision(reason=f"Classification error ({type(exc).__name__}); running everything.")
        _append("GITHUB_OUTPUT", f"mode={decision.mode}\n")
        _append("GITHUB_STEP_SUMMARY", decision.summary())
        print(decision.summary())
        return 0
    try:
        needs = json.loads(args.needs_json)
        if not isinstance(needs, dict):
            raise ValueError("not an object")
    except ValueError as exc:
        print(f"::error::Malformed needs JSON ({exc})", file=sys.stderr)
        return 1
    ok, report = gate(args.mode, args.classify_result, needs)
    _append("GITHUB_STEP_SUMMARY", report)
    print(report)
    if not ok:
        print("::error::CI result: required suites did not all pass; see the job summary.", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
