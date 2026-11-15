"""Change-aware PR validation, scripts/ci_changes.py and scripts/check_doc_links.py (#687).

Reduced validation must be granted only on a positive, complete classification, and the
"CI result" gate must never pass a failed, missing, cancelled or skipped required suite.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


ci = load("ci_changes")
links = load("check_doc_links")
WORKFLOW = yaml.safe_load((ROOT / ".github" / "workflows" / "ci-cd.yml").read_text())["jobs"]
DOCS_ON = {ci.DOCS}


# --- classification of paths -------------------------------------------------------------

@pytest.mark.parametrize("files", [
    ["README.md"],
    ["CONTRIBUTING.md", "AGENTS.md", "docs/DEVELOPMENT.md"],
    ["docs/adr/0005-testing-contract.md", "docs/archive/refactor-2026/README.md"],
    ["deploy/README.md", ".github/pull_request_template.md", ".github/ISSUE_TEMPLATE/ui-change.md"],
])
def test_documentation_only_paths_select_the_docs_mode(files):
    decision = ci.classify_paths(files, DOCS_ON)

    assert (decision.mode, decision.classification) == (ci.DOCS, ci.DOCS)


@pytest.mark.parametrize("path", [
    "semant_demo_backend/README.md",  # pyproject.toml readme: installed with the package
    "data_tools/embedder/README.md",
    "semant_demo_frontend/src/generated/api/docs/Values.md",  # generated client
    "semant_demo_frontend/README.md",
    "docs/weaviate-audit-2026-10/inventory-2026-10-16b.json",
    "docs/screenshot.png",
    "docs/README.MD",
    "deploy/docker-compose.app.yaml",
    ".github/workflows/ci-cd.yml",
    ".github/ISSUE_TEMPLATE/nested/x.md",
    "scripts/ci_changes.py",
    "Makefile",
    "notes/new.md",  # unknown directory
])
def test_any_path_outside_the_allowlist_selects_full_validation(path):
    decision = ci.classify_paths(["docs/DEVELOPMENT.md", path], DOCS_ON)

    assert (decision.mode, decision.classification) == (ci.FULL, ci.FULL)
    assert decision.outside == [path]


def test_empty_diff_selects_full_validation():
    assert ci.classify_paths([], DOCS_ON).mode == ci.FULL


def test_documentation_only_change_runs_everything_until_the_mode_is_enabled():
    decision = ci.classify_paths(["docs/DEVELOPMENT.md"], set())

    assert (decision.mode, decision.classification) == (ci.FULL, ci.DOCS)
    assert "observe-only" in decision.reason


def test_summary_lists_omitted_suites_and_the_paths():
    summary = ci.classify_paths(["docs/DEVELOPMENT.md"], DOCS_ON).summary()

    assert "| Integration tests | intentionally omitted |" in summary
    assert "| Documentation checks | required |" in summary
    assert "| PR preview | intentionally omitted |" in summary
    assert "`docs/DEVELOPMENT.md`" in summary


# --- the PR diff from the merge commit ----------------------------------------------------

def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def merge_repo(tmp_path, monkeypatch):
    """A base branch that moved on, and a PR merged into it like GitHub's merge commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "ci@example.invalid")
    git(repo, "config", "user.name", "CI")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "docs").mkdir()
    (repo / "docs" / "A.md").write_text("a\n")
    (repo / "app.py").write_text("x = 1\n")
    (repo / "old.md").write_text("old\n" * 20)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    git(repo, "checkout", "-qb", "pr")
    git(repo, "mv", "old.md", "src_renamed.md")  # rename out of the allowlisted root
    (repo / "docs" / "A.md").write_text("changed\n")
    git(repo, "commit", "-qam", "pr")
    head = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "main")
    (repo / "app.py").write_text("x = 2\n")  # the base moved on: not the PR's change
    git(repo, "commit", "-qam", "base moved")
    git(repo, "merge", "-q", "--no-ff", "-m", "merge", "pr")
    monkeypatch.chdir(repo)
    return repo, head


def test_diff_lists_both_sides_of_a_rename_and_only_the_prs_changes(merge_repo):
    _, head = merge_repo

    assert ci.changed_files(head) == ["docs/A.md", "old.md", "src_renamed.md"]


def test_diff_refuses_a_merge_whose_second_parent_is_not_the_pr_head(merge_repo):
    with pytest.raises(ValueError, match="not the PR head"):
        ci.changed_files("0" * 40)


def test_diff_refuses_a_non_merge_checkout(merge_repo):
    repo, head = merge_repo
    git(repo, "checkout", "-q", "HEAD^1")

    with pytest.raises(ValueError, match="1 parent"):
        ci.changed_files(head)


# --- the classify command -----------------------------------------------------------------

def args(**overrides):
    values = {"event": "pull_request", "repo": "o/r", "pr": 7, "head_sha": "abc"}
    values.update(overrides)
    return type("Args", (), values)()


@pytest.fixture
def docs_pr(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv(ci.SELECTION_VARIABLE, "docs")
    monkeypatch.setattr(ci, "pr_labels", lambda repo, pr, token: [])
    monkeypatch.setattr(ci, "changed_files", lambda head: ["docs/DEVELOPMENT.md"])


def test_classify_selects_docs_for_a_documentation_only_pr(docs_pr):
    assert ci.classify(args()).mode == ci.DOCS


@pytest.mark.parametrize("event", ["push", "workflow_dispatch"])
def test_non_pr_events_always_run_everything(docs_pr, event):
    assert ci.classify(args(event=event)).mode == ci.FULL


def test_the_force_full_label_runs_everything(docs_pr, monkeypatch):
    monkeypatch.setattr(ci, "pr_labels", lambda repo, pr, token: ["documentation", ci.FORCE_FULL_LABEL])

    assert ci.classify(args()).mode == ci.FULL


def test_unreadable_labels_run_everything(docs_pr, monkeypatch):
    def fail(repo, pr, token):
        raise OSError("network down")
    monkeypatch.setattr(ci, "pr_labels", fail)

    assert ci.classify(args()).mode == ci.FULL


def test_an_undeterminable_diff_runs_everything(docs_pr, monkeypatch):
    def fail(head):
        raise ValueError("not a merge")
    monkeypatch.setattr(ci, "changed_files", fail)

    assert ci.classify(args()).mode == ci.FULL


@pytest.mark.parametrize("value", ["", "frontend", "Docs"])
def test_the_mode_runs_only_when_enabled(docs_pr, monkeypatch, value):
    monkeypatch.setenv(ci.SELECTION_VARIABLE, value)

    assert ci.classify(args()).mode == ci.FULL


def test_classify_writes_full_on_an_unexpected_error(docs_pr, monkeypatch, tmp_path):
    def crash(arguments):
        raise RuntimeError("bug")
    monkeypatch.setattr(ci, "classify", crash)
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    assert ci.main(["classify", "--event", "pull_request"]) == 0
    assert output.read_text() == "mode=full\n"


# --- the gate -----------------------------------------------------------------------------

def needs(default="success", **results):
    data = {"classify": {"result": "success", "outputs": {}}}
    for job in ci.SUITES:
        data[job] = {"result": results.get(job.replace("-", "_"), default), "outputs": {}}
    return data


DOCS_SKIPPED = {job.replace("-", "_"): "skipped" for job in ci.SUITES if job != "docs-check"}


def test_gate_passes_full_validation_when_everything_succeeded():
    ok, report = ci.gate(ci.FULL, "success", needs())

    assert ok, report


def test_gate_passes_docs_mode_with_omitted_suites_recorded_as_not_tested():
    ok, report = ci.gate(ci.DOCS, "success", needs(**DOCS_SKIPPED))

    assert ok, report
    assert "| Integration tests | intentionally omitted | skipped, not tested | ok |" in report


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped", "missing"])
@pytest.mark.parametrize("job", list(ci.SUITES))
def test_gate_fails_any_required_suite_that_did_not_succeed(job, result):
    ok, _ = ci.gate(ci.FULL, "success", needs(**{job.replace("-", "_"): result}))

    assert not ok


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
def test_gate_fails_docs_mode_when_the_documentation_check_did_not_succeed(result):
    ok, _ = ci.gate(ci.DOCS, "success", needs(**DOCS_SKIPPED, docs_check=result))

    assert not ok


@pytest.mark.parametrize("result", ["failure", "cancelled"])
def test_gate_fails_an_omitted_suite_that_ran_and_did_not_succeed(result):
    ok, _ = ci.gate(ci.DOCS, "success", needs(**{**DOCS_SKIPPED, "test_backend": result}))

    assert not ok


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped", ""])
def test_gate_fails_when_classification_did_not_succeed(result):
    ok, _ = ci.gate(ci.FULL, result, needs())

    assert not ok


@pytest.mark.parametrize("mode", ["", "frontend", "DOCS"])
def test_gate_fails_an_unknown_mode_even_when_everything_passed(mode):
    ok, _ = ci.gate(mode, "success", needs())

    assert not ok


def test_gate_fails_when_its_needs_do_not_match_the_registry():
    data = needs()
    data["new-suite"] = {"result": "success"}

    assert not ci.gate(ci.FULL, "success", data)[0]
    del data["new-suite"], data["test-browser"]
    assert not ci.gate(ci.FULL, "success", data)[0]


def test_gate_command_rejects_malformed_needs(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    assert ci.main(["gate", "--mode", "full", "--classify-result", "success", "--needs-json", "[]"]) == 1
    assert ci.main(["gate", "--mode", "full", "--classify-result", "success", "--needs-json", "{"]) == 1
    assert ci.main(["gate", "--mode", "full", "--classify-result", "success",
                    "--needs-json", json.dumps(needs())]) == 0


# --- the workflow matches the registry ----------------------------------------------------

def selection_condition(mode):
    return f"needs.classify.outputs.mode != '{mode}'"


def test_gate_job_needs_exactly_the_registered_suites():
    assert set(WORKFLOW["ci-result"]["needs"]) == {"classify", *ci.SUITES}
    assert "always()" in WORKFLOW["ci-result"]["if"]


def test_registered_suites_are_the_workflow_check_names():
    assert {job: WORKFLOW[job]["name"] for job in ci.SUITES} == ci.SUITES


def runs_unless_omitted(job, mode):
    """Whether ``job`` skips in ``mode`` only via the exact classify output."""
    spec = WORKFLOW[job]
    if selection_condition(mode) in spec.get("if", ""):
        return True
    upstream = spec.get("needs", [])
    return bool(upstream) and all(runs_unless_omitted(n, mode) for n in upstream if n in WORKFLOW)


@pytest.mark.parametrize("mode", [m for m in ci.MODES.values() if m.name != ci.FULL], ids=lambda m: m.name)
def test_omitted_jobs_skip_only_on_the_exact_mode_output(mode):
    for job in set(ci.SUITES) - mode.required:
        assert runs_unless_omitted(job, mode.name), job
    for job in mode.required:
        assert selection_condition(mode.name) not in WORKFLOW[job].get("if", ""), job


def test_jobs_conditioned_on_the_classification_need_it_and_tolerate_its_failure():
    for job, spec in WORKFLOW.items():
        condition = spec.get("if", "")
        if "needs.classify" in condition:
            assert "classify" in spec["needs"], job
            # Without !cancelled()/always(), a failed classification would skip the job.
            assert "!cancelled()" in condition or "always()" in condition, job


def test_deployments_require_the_gate():
    for job in ("deploy-production", "deploy-test-main"):
        assert "ci-result" in WORKFLOW[job]["needs"]


# --- documentation links ------------------------------------------------------------------

def test_link_check_reports_broken_relative_links_only(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "A.md").write_text("a")
    (tmp_path / "x.md").write_text(
        "[ok](docs/A.md#section) [ok](/docs/A.md) [web](https://example.com/missing.md) [anchor](#top)\n"
        "[bad](docs/Missing.md) ![img](./shot.png) `[code](nope.md)`\n"
        "```\n[fenced](nope.md)\n```\n"
        "[ref]: docs/Gone.md\n")
    monkeypatch.setattr(links, "ROOT", tmp_path)

    assert links.broken_links("x.md") == ["docs/Missing.md", "./shot.png", "docs/Gone.md"]


def test_repository_markdown_links_resolve():
    assert links.main() == 0
