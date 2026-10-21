"""Summary length levels (#360): configuration, both summarizers, the use cases and the routes."""
from types import SimpleNamespace

import pytest
import yaml
from asgi_lifespan import LifespanManager
from classconfig.configurable import ConfigError
from httpx import ASGITransport, AsyncClient

from semant_demo.config import SCRIPT_PATH
from semant_demo.features.search.schemas import SearchRequest
from semant_demo.features.summarization import service
from semant_demo.features.summarization.document import TemplatedDocumentSummarizer, load_document_summarizer
from semant_demo.features.summarization.schemas import SummaryLength
from semant_demo.features.summarization.templated import SummaryLengths, TemplatedSearchResultsSummarizer, \
    load_summarizer
from semant_demo.main import create_app
from semant_demo.routes.dependencies import get_summarizer
from semant_demo.utils.template import Template
from tests.app_support import make_test_config, offline_weaviate
from tests.auth_support import auth_headers, register
from tests.fakes import FakeLlm
from tests.test_summarization import test_document_service as documents
from tests.test_summarization.test_service import results

CONFIGS = SCRIPT_PATH / "configs"
LENGTHS = {"default": "short", "short": 50, "detailed": 250}
# Echoes what the prompts get, so a test can see the chosen level without depending on the wording.
ECHO = Template("length={{ length }} brevity={{ brevity }}")


def search_summarizer(llm, lengths=LENGTHS) -> TemplatedSearchResultsSummarizer:
    summarizer = load_summarizer(str(CONFIGS / "search_summarizer.yaml"), llm)
    summarizer.gen_results_summary_lengths = SummaryLengths.model_validate(lengths)
    summarizer.gen_results_summary_system_prompt = ECHO
    return summarizer


def document_summarizer(llm, lengths=LENGTHS) -> TemplatedDocumentSummarizer:
    summarizer = load_document_summarizer(str(CONFIGS / "document_summarizer.yaml"), llm)
    summarizer.gen_summary_lengths = SummaryLengths.model_validate(lengths)
    summarizer.gen_summary_system_prompt = ECHO
    return summarizer


def sent(llm) -> str:
    """The system prompt of the only model call."""
    [(_, messages, _)] = llm.calls
    return messages[0]["content"]


SUMMARIZERS = [
    (TemplatedSearchResultsSummarizer, "search_summarizer.yaml", "gen_results_summary"),
    (TemplatedDocumentSummarizer, "document_summarizer.yaml", "gen_summary"),
]


def write_config(tmp_path, name: str, change) -> str:
    """The bundled configuration ``name`` changed by ``change`` (a function of the loaded YAML)."""
    config = yaml.safe_load((CONFIGS / name).read_text())
    change(config)
    path = tmp_path / name
    path.write_text(yaml.safe_dump(config, allow_unicode=True))
    return str(path)


@pytest.mark.parametrize("cls, name, prefix", SUMMARIZERS)
def test_bundled_length_levels(cls, name, prefix):
    lengths: SummaryLengths = getattr(cls.create(str(CONFIGS / name)), f"{prefix}_lengths")

    assert lengths.default == SummaryLength.short
    assert lengths.short < lengths.detailed


@pytest.mark.parametrize("cls, name, prefix", SUMMARIZERS)
def test_a_configuration_from_before_length_levels_loads_with_the_defaults(tmp_path, cls, name, prefix):
    def before_360(config):
        del config[f"{prefix}_lengths"]

    summarizer = cls.create(write_config(tmp_path, name, before_360))

    assert getattr(summarizer, f"{prefix}_lengths").resolve(None)[0] == SummaryLength.short


@pytest.mark.parametrize("cls, name, prefix", SUMMARIZERS)
def test_a_malformed_length_level_fails_at_load(tmp_path, cls, name, prefix):
    def malformed(config):
        config[f"{prefix}_lengths"]["short"] = 0

    with pytest.raises(ConfigError, match="short"):
        cls.create(write_config(tmp_path, name, malformed))


async def test_the_token_limit_is_the_model_options_for_every_level():
    # The level sets only the word limit; the token limit stays a safety limit (#441 review).
    llm = FakeLlm()
    summarizer = search_summarizer(llm)
    summarizer.gen_results_summary_model_options.max_completion_tokens = 700

    for length in SummaryLength:
        await service.summarize(summarizer, "results", results("Lhota."), length=length)

    assert [options["max_tokens"] for _, _, options in llm.calls] == [700] * len(SummaryLength)


@pytest.mark.parametrize("length, expected", [
    (None, "length=short brevity=50"),
    (SummaryLength.short, "length=short brevity=50"),
    (SummaryLength.detailed, "length=detailed brevity=250"),
])
async def test_the_results_summary_follows_the_length_level(length, expected):
    llm = FakeLlm()

    await service.summarize(search_summarizer(llm), "results", results("Jan Novák byl kronikář."), length=length)

    assert sent(llm) == expected


async def test_the_configured_default_level_is_used_when_none_is_requested():
    llm = FakeLlm()

    await service.summarize(search_summarizer(llm, {**LENGTHS, "default": "detailed"}), "results", results("Lhota."))

    assert sent(llm) == "length=detailed brevity=250"


async def test_the_results_summary_of_a_search_uses_the_default_level():
    # A search request has no length level: its optional results summary is the configured default.
    llm = FakeLlm()
    request = SearchRequest(query="kronikář", tag_uuids=[], positive=False, automatic=False,
                            search_title_generate=False, search_summary_generate=False,
                            search_results_summary_generate=True)
    response = results("Jan Novák byl kronikář.")

    failures = await search_summarizer(llm)(request, response)

    assert failures == [] and response.results_summary == "fake reply"
    assert sent(llm) == "length=short brevity=50"


@pytest.mark.parametrize("length, expected", [
    (None, "length=short brevity=50"),
    (SummaryLength.detailed, "length=detailed brevity=250"),
])
async def test_the_document_summary_follows_the_length_level(length, expected):
    llm = FakeLlm()

    response = await service.summarize_document(documents.FakeDocuments([documents.chunk(0)]),
                                                documents.FakeCollections(), document_summarizer(llm),
                                                documents.OWNER, documents.DOCUMENT, documents.COLLECTION,
                                                length=length)

    assert response.summary == "fake reply"
    assert sent(llm) == expected


@pytest.mark.parametrize("name", ["search_summarizer.yaml", "document_summarizer.yaml"])
def test_bundled_prompts_ask_for_a_different_summary_per_level(name):
    config = yaml.safe_load((CONFIGS / name).read_text())
    prompt = next(Template(value) for key, value in config.items() if key.endswith("summary_system_prompt"))
    values = {"results": [], "chunks": [], "query": "q"}

    short = prompt.render({**values, "length": "short", "brevity": 100})
    detailed = prompt.render({**values, "length": "detailed", "brevity": 300})

    assert short != detailed
    assert "100" in short and "300" in detailed


@pytest.fixture
async def app(tmp_path):
    app = create_app(make_test_config(tmp_path), weaviate_connector=offline_weaviate)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield SimpleNamespace(app=app, client=client)


SEARCH_RESPONSE = results("Jan Novák byl kronikář.").model_dump(mode="json")


async def test_the_summarize_route_passes_the_length_level(app):
    llm = FakeLlm()
    app.app.dependency_overrides[get_summarizer] = lambda: search_summarizer(llm)

    response = await app.client.post("/api/summarize/results", params={"length": "detailed"}, json=SEARCH_RESPONSE)

    assert response.status_code == 200, response.text
    assert sent(llm) == "length=detailed brevity=250"


async def test_the_summarize_route_without_a_level_uses_the_default(app):
    llm = FakeLlm()
    app.app.dependency_overrides[get_summarizer] = lambda: search_summarizer(llm)

    response = await app.client.post("/api/summarize/results", json=SEARCH_RESPONSE)

    assert response.status_code == 200, response.text
    assert sent(llm) == "length=short brevity=50"


async def test_an_unknown_level_is_rejected_before_any_model_call(app):
    llm = FakeLlm()
    app.app.dependency_overrides[get_summarizer] = lambda: search_summarizer(llm)
    assert (await register(app.client, email="a@example.com", password="StrongPassw0rd!")).status_code == 201
    headers = await auth_headers(app.client, "a@example.com", "StrongPassw0rd!")

    summarize = await app.client.post("/api/summarize/results", params={"length": "medium"}, json=SEARCH_RESPONSE)
    document = await app.client.post(
        f"/api/user_collections/{documents.COLLECTION}/documents/{documents.DOCUMENT}/summary",
        params={"length": "medium"}, headers=headers)

    assert (summarize.status_code, document.status_code) == (422, 422)
    assert llm.calls == []
