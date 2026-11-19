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
ALL_ON = {ci.DOCS, ci.FRONTEND, ci.DEPLOY}
FE = "semant_demo_frontend/"


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
    "docs/weaviate-audit-2026-10/inventory-2026-10-16b.json",
    "docs/screenshot.png",
    "docs/README.MD",
    ".github/workflows/ci-cd.yml",
    ".github/ISSUE_TEMPLATE/nested/x.md",
    "scripts/ci_changes.py",
    "Makefile",
    "notes/new.md",  # unknown directory
])
def test_any_path_outside_the_allowlist_selects_full_validation(path):
    decision = ci.classify_paths(["docs/DEVELOPMENT.md", path], ALL_ON)

    assert (decision.mode, decision.classification) == (ci.FULL, ci.FULL)
    assert decision.outside == [path]


def test_empty_diff_selects_full_validation():
    assert ci.classify_paths([], DOCS_ON).mode == ci.FULL


def test_documentation_only_change_runs_everything_until_the_mode_is_enabled():
    decision = ci.classify_paths(["docs/DEVELOPMENT.md"], set())

    assert (decision.mode, decision.classification) == (ci.FULL, ci.DOCS)
    assert "observe-only" in decision.reason


# --- the frontend mode ----------------------------------------------------------------------

FRONTEND_PATHS = [
    FE + "src/features/search/SearchPage.vue",
    FE + "src/shared/api/client.ts",
    FE + "test/unit/searchPage.spec.ts",
    FE + "test/e2e/search.spec.ts",
    FE + "test/e2e/helpers/login.ts",
    FE + "test/fixtures/longPassage.ts",
    FE + "public/icons/favicon-32x32.png",
    FE + "index.html",
    FE + "README.md",
    "docs/UI_GUIDELINES.md",  # documentation may come with it
]


def test_frontend_only_paths_select_the_frontend_mode():
    decision = ci.classify_paths(FRONTEND_PATHS, ALL_ON)

    assert (decision.mode, decision.classification) == (ci.FRONTEND, ci.FRONTEND)


def test_the_narrowest_enabled_mode_that_fits_is_selected():
    assert ci.classify_paths(["docs/DEVELOPMENT.md"], ALL_ON).mode == ci.DOCS
    decision = ci.classify_paths(["docs/DEVELOPMENT.md"], {ci.FRONTEND})
    assert (decision.mode, decision.classification) == (ci.FRONTEND, ci.DOCS)


def test_frontend_only_change_runs_everything_until_the_mode_is_enabled():
    decision = ci.classify_paths(FRONTEND_PATHS, DOCS_ON)

    assert (decision.mode, decision.classification) == (ci.FULL, ci.FRONTEND)
    assert "observe-only" in decision.reason


@pytest.mark.parametrize("path", [
    FE + "package.json",
    FE + "package-lock.json",
    FE + ".nvmrc",
    FE + ".npmrc",
    FE + "openapitools.json",
    FE + "quasar.config.js",
    FE + "playwright.config.ts",
    FE + "vitest.config.ts",
    FE + "tsconfig.json",
    FE + "typecheck-baseline.json",
    FE + ".eslintrc.js",
    FE + "scripts/api-client.sh",
    FE + "src/generated/api/apis/DefaultApi.ts",
    FE + "src/features/documents/originalSource.ts",
    FE + "test/e2e/shard_durations.json",
    FE + "new-config.json",
    "semant_demo_backend/semant_demo/main.py",
    "semant_demo_backend/tests/fixtures/text_offsets.json",  # read by a frontend unit test
    "scripts/browser_shards.py",
    "Makefile",
])
def test_shared_or_backend_paths_with_frontend_changes_select_full_validation(path):
    decision = ci.classify_paths([FE + "src/App.vue", path], ALL_ON)

    assert (decision.mode, decision.classification) == (ci.FULL, ci.FULL)
    assert decision.outside == [path]


def test_deleting_a_browser_spec_selects_full_validation():
    spec = FE + "test/e2e/search.spec.ts"

    assert ci.classify_paths([spec], ALL_ON, deleted=frozenset({spec})).mode == ci.FULL
    unit = FE + "test/unit/old.spec.ts"
    assert ci.classify_paths([unit], ALL_ON, deleted=frozenset({unit})).mode == ci.FRONTEND
    assert ci.classify_paths([spec], ALL_ON).mode == ci.FRONTEND


def test_frontend_paths_named_in_backend_code_force_full_validation():
    """A backend test reading a frontend file must not be omitted when that file changes."""
    import re
    named = set()
    for source in (ROOT / "semant_demo_backend").rglob("*.py"):
        if source.name == "test_ci_changes.py":
            continue
        named |= set(re.findall(r"semant_demo_frontend/[\w./-]*\w", source.read_text(encoding="utf-8")))
    assert FE + "src/features/documents/originalSource.ts" in named
    for path in named:
        assert not ci.MODES[ci.FRONTEND].fits(path), path


# --- the deploy mode ------------------------------------------------------------------------

DEPLOY_PATHS = [
    "deploy/Dockerfile",
    "deploy/docker-compose.app-test.yml",
    "deploy/.env.test.example",
    "semant_demo_backend/tests/test_deploy_mcp_rate_limit.py",
    "docs/DEPLOYMENT.md",
]


def test_deployment_only_paths_select_the_deploy_mode():
    decision = ci.classify_paths(DEPLOY_PATHS, ALL_ON)

    assert (decision.mode, decision.classification) == (ci.DEPLOY, ci.DEPLOY)


def test_deployment_only_change_runs_everything_until_the_mode_is_enabled():
    decision = ci.classify_paths(DEPLOY_PATHS, {ci.DOCS, ci.FRONTEND})

    assert (decision.mode, decision.classification) == (ci.FULL, ci.DEPLOY)


@pytest.mark.parametrize("path", [
    ".github/workflows/ci-cd.yml",
    "deploy/docker-compose.app.yaml",  # production-only, not previewed
    "deploy/docker-compose.database.yml",
    "deploy/docker-compose.topicer.yml",
    "deploy/update.sh",
    "deploy/.env.example",
    "deploy/test_sqlite_backup.sh",
    "scripts/python-locks.sh",
    "scripts/with-test-weaviate.sh",
    "semant_demo_backend/requirements-runtime.lock",
    "semant_demo_backend/pyproject.toml",
    "semant_demo_backend/tests/conftest.py",
    "semant_demo_backend/tests/test_dependency_locks.py",
    "semant_demo_backend/tests/integration/test_deploy_x.py",
    "semant_demo_backend/semant_demo/config.py",
    "data_tools/embedder/config.qwen.yaml",
])
def test_shared_paths_with_deployment_changes_select_full_validation(path):
    # Start with an allowed preview-tested file; the added path must force full CI.
    decision = ci.classify_paths(["deploy/Dockerfile", path], ALL_ON)

    assert (decision.mode, decision.classification) == (ci.FULL, ci.FULL)
    assert decision.outside == [path]


def test_deleting_a_deployment_contract_test_selects_full_validation():
    path = "semant_demo_backend/tests/test_deploy_image.py"
    assert ci.classify_paths([path], ALL_ON, deleted=frozenset({path})).mode == ci.FULL


def test_deployment_and_frontend_changes_together_select_full_validation():
    decision = ci.classify_paths(["deploy/Dockerfile", FE + "src/App.vue"], ALL_ON)

    assert decision.mode == ci.FULL
    assert decision.outside == []
    assert "several components" in decision.reason


def test_suites_the_deploy_mode_omits_do_not_read_deploy_files():
    """The frontend, integration and browser suites never read a deploy/ file that a
    deployment-only PR may change. Other deploy/ files (production-only scripts such as
    weaviate_backup.py, #469) force full CI, so these suites run whenever they change."""
    import re
    deploy = ci.MODES[ci.DEPLOY]
    sources = [*(ROOT / FE / "src").rglob("*.[tj]s"), *(ROOT / FE / "src").rglob("*.vue"),
               *(ROOT / FE / "test").rglob("*.ts"), *(ROOT / FE).glob("*.[tj]s"),
               *(ROOT / "semant_demo_backend" / "tests" / "integration").rglob("*.py"),
               ROOT / "semant_demo_backend" / "tests" / "e2e_server.py",
               ROOT / "scripts" / "with-test-weaviate.sh", ROOT / "scripts" / "integration_shards.py",
               ROOT / "scripts" / "browser_shards.py"]
    sources = [path for path in sources if "generated" not in path.parts]
    assert len(sources) > 100
    for source in sources:
        text = source.read_text(encoding="utf-8")
        assert not re.search(r"[\"']deploy[\"']", text), source
        for path in re.findall(r"\bdeploy/[\w./*-]*", text):
            path = path.rstrip(".")
            assert path != "deploy/" and not deploy.fits(path) and "*" not in path, (source, path)
    assert deploy.fits("deploy/Dockerfile") and not deploy.fits("deploy/weaviate_backup.py")


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

    assert ci.changed_files(head) == {"docs/A.md": "M", "old.md": "D", "src_renamed.md": "A"}


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
    monkeypatch.setattr(ci, "changed_files", lambda head: {"docs/DEVELOPMENT.md": "M"})


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


@pytest.mark.parametrize("value", ["", "Docs", "doc", "full"])
def test_the_mode_runs_only_when_enabled(docs_pr, monkeypatch, value):
    monkeypatch.setenv(ci.SELECTION_VARIABLE, value)

    assert ci.classify(args()).mode == ci.FULL


def test_classify_reads_deletions_from_the_diff(docs_pr, monkeypatch):
    monkeypatch.setenv(ci.SELECTION_VARIABLE, "docs, frontend")
    spec = FE + "test/e2e/search.spec.ts"
    monkeypatch.setattr(ci, "changed_files", lambda head: {spec: "M"})
    assert ci.classify(args()).mode == ci.FRONTEND

    monkeypatch.setattr(ci, "changed_files", lambda head: {spec: "D"})
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
    data[ci.PREVIEW_JOB] = {"result": results.get("deploy_test_pr", "skipped"), "outputs": {}}
    return data


DOCS_SKIPPED = {job.replace("-", "_"): "skipped" for job in ci.SUITES if job != "docs-check"}
FRONTEND_SKIPPED = {job.replace("-", "_"): "skipped" for job in ci.SUITES
                    if job not in ci.MODES[ci.FRONTEND].required}


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


def test_gate_passes_frontend_mode_with_backend_suites_omitted():
    ok, report = ci.gate(ci.FRONTEND, "success", needs(**FRONTEND_SKIPPED))

    assert ok, report
    assert set(FRONTEND_SKIPPED) == {"test_backend", "test_integration", "python_locks", "api_client_drift"}
    assert "| Backend tests | intentionally omitted | skipped, not tested | ok |" in report
    assert "| Browser smoke tests | required | success | ok |" in report


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
@pytest.mark.parametrize("job", ["docs_check", "test_frontend", "test_browser"])
def test_gate_fails_frontend_mode_when_a_required_suite_did_not_succeed(job, result):
    ok, _ = ci.gate(ci.FRONTEND, "success", needs(**{**FRONTEND_SKIPPED, job: result}))

    assert not ok


def test_gate_passes_deploy_mode_with_app_suites_omitted():
    omitted = {job.replace("-", "_"): "skipped" for job in ci.SUITES if job not in ci.MODES[ci.DEPLOY].required}
    ok, report = ci.gate(ci.DEPLOY, "success", needs(**omitted, deploy_test_pr="success"))

    assert ok, report
    assert set(omitted) == {"test_frontend", "test_integration", "test_browser", "python_locks"}
    assert "| Backend tests | required | success | ok |" in report
    assert "| PR preview deployment | required | success | ok |" in report


@pytest.mark.parametrize("job", ["docs_check", "test_backend", "api_client_drift"])
def test_gate_fails_deploy_mode_when_a_required_suite_was_skipped(job):
    omitted = {j.replace("-", "_"): "skipped" for j in ci.SUITES if j not in ci.MODES[ci.DEPLOY].required}

    assert not ci.gate(ci.DEPLOY, "success", needs(**{**omitted, job: "skipped", "deploy_test_pr": "success"}))[0]


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped", "missing"])
def test_deploy_mode_requires_successful_preview(result):
    omitted = {j.replace("-", "_"): "skipped" for j in ci.SUITES if j not in ci.MODES[ci.DEPLOY].required}
    ok, report = ci.gate(ci.DEPLOY, "success", needs(**{**omitted, "deploy_test_pr": result}))
    assert not ok
    assert "PR preview deployment (required)" in report


@pytest.mark.parametrize("mode", [ci.FULL, ci.DOCS, ci.FRONTEND])
def test_other_modes_keep_preview_failures_non_blocking(mode):
    omitted = {j.replace("-", "_"): "skipped" for j in ci.SUITES if j not in ci.MODES[mode].required}
    ok, report = ci.gate(mode, "success", needs(**{**omitted, "deploy_test_pr": "failure"}))
    assert ok, report
    assert "| PR preview deployment | not required | failure | n/a |" in report


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


@pytest.mark.parametrize("mode", ["", "front", "DOCS", "Frontend"])
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
    assert set(WORKFLOW["ci-result"]["needs"]) == {"classify", ci.PREVIEW_JOB, *ci.SUITES}
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


def test_preview_still_starts_without_waiting_for_application_tests():
    assert WORKFLOW[ci.PREVIEW_JOB]["needs"] == ["classify"]


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
