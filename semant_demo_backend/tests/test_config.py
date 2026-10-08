"""Each setting has one effective source: one assignment, one environment variable."""
import ast
import inspect
import textwrap
from collections import Counter

import pytest

from semant_demo.config import Config


def _config_init_tree() -> ast.FunctionDef:
    source = textwrap.dedent(inspect.getsource(Config.__init__))
    return ast.parse(source).body[0]


def test_each_setting_is_assigned_once():
    assigned = Counter(
        target.attr
        for node in ast.walk(_config_init_tree())
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self"
    )
    duplicated = {name: count for name, count in assigned.items() if count > 1}
    assert assigned, "no settings found; test is not inspecting Config"
    assert duplicated == {}


def test_each_environment_variable_is_read_once():
    read = Counter(
        node.args[0].value
        for node in ast.walk(_config_init_tree())
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    )
    duplicated = {name: count for name, count in read.items() if count > 1}
    assert read, "no environment reads found; test is not inspecting Config"
    assert duplicated == {}


def test_explicit_environ_ignores_process_environment(monkeypatch):
    monkeypatch.setenv("TOPICER_URL", "http://from-process-env")
    monkeypatch.setenv("SQL_DB_URL", "sqlite+aiosqlite:///from-process-env.db")

    config = Config(environ={})

    assert config.TOPICER_URL == "http://topicer:8089"
    assert config.SQL_DB_URL == "sqlite+aiosqlite:///tasks.db"


def test_default_constructor_reads_process_environment(monkeypatch):
    monkeypatch.setenv("SQL_DB_URL", "sqlite+aiosqlite:///from-process-env.db")

    assert Config().SQL_DB_URL == "sqlite+aiosqlite:///from-process-env.db"


def test_topicer_defaults_keep_previously_effective_values():
    # The removed duplicate block was always overridden by these values.
    config = Config(environ={})

    assert config.TOPICER_URL == "http://topicer:8089"
    assert config.TOPICER_CONFIG_NAME == "openai"
    assert config.TOPICER_TIMEOUT == 600.0
    assert not hasattr(config, "TOPICER_READ_WRITE_TIMEOUT")


@pytest.mark.parametrize(
    ("env_name", "raw_value", "attribute", "expected"),
    [
        ("SQL_DB_URL", "sqlite+aiosqlite:////tmp/x.db", "SQL_DB_URL", "sqlite+aiosqlite:////tmp/x.db"),
        ("JWT_SECRET", "s3cret", "JWT_SECRET", "s3cret"),
        ("TOPICER_URL", "http://t:1", "TOPICER_URL", "http://t:1"),
        ("TOPICER_CONFIG_NAME", "cfg", "TOPICER_CONFIG_NAME", "cfg"),
        ("TOPICER_TIMEOUT", "12.5", "TOPICER_TIMEOUT", 12.5),
        ("WEAVIATE_HOST", "w", "WEAVIATE_HOST", "w"),
        ("WEAVIATE_REST_PORT", "18080", "WEAVIATE_REST_PORT", 18080),
        ("WEAVIATE_GRPC_PORT", "15051", "WEAVIATE_GRPC_PORT", 15051),
        ("ALLOWED_ORIGIN", "http://ui", "ALLOWED_ORIGIN", "http://ui"),
        ("RAG_CONFIGS_PATH", "/rag", "RAG_CONFIGS_PATH", "/rag"),
    ],
)
def test_environment_variable_sets_setting(env_name, raw_value, attribute, expected):
    assert getattr(Config(environ={env_name: raw_value}), attribute) == expected


def test_span_chat_falls_back_to_openai_settings():
    config = Config(environ={"OPENAI_API_KEY": "k", "OPENAI_API_URL": "http://o", "OPENAI_MODEL": "m"})

    assert (config.SPAN_CHAT_API_KEY, config.SPAN_CHAT_API_URL, config.SPAN_CHAT_MODEL) == ("k", "http://o", "m")
