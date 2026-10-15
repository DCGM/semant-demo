# semANT OpenRouter model selection — 16 October 2026

**Status:** configuration decision from public provider information and code inspection; **no live provider runs or task-specific quality evaluation**. The table is a dated snapshot, not a continuously updated benchmark. Implementation PR: #372.

## 1. What the app actually needs

| Feature / call site | Workload and frequency | Requirement / implication |
| --- | --- | --- |
| `search_summary` — `features/summarization/templated.py`, called by `POST /api/search` and summaries | Generate titles for individual hits, per-hit short summaries, and overall search-result summaries. Several separate calls may run for one Search action; public and frequent | **No reasoning**, low latency and low output cost. Ground short outputs in supplied historical Czech-language text, never invent sources |
| `question` — `features/summarization/service.py` | One answer from supplied search-result snippets; `temperature=0`, **`max_tokens=300`** | Strong instruction and citation compliance; **minimal/low reasoning only**, because thinking tokens count toward 300 and can leave an empty visible answer |
| `span_chat` — `features/annotations/span_chat.py` / `FeatureChat` | Stream chat about a selected annotation, with document context and history; existing call requests `temperature=0.4` and `max_tokens=1024` | Responsive, robust Czech/German/English, low reasoning. Stream must yield visible text, not reasoning-only output |
| Basic `RagGenerator` | Retrieve public chunks + one answer call (also one rewrite on history) | Economical tier appropriate; no tool-calling requirement |
| `IncrementalAdaptiveRagGenerator` | LangGraph: language detection, question rewrite, sufficiency/metadata checks, multiple queries, grading and answer, possibly retries. **Several model calls for one visible answer**, often with JSON-oriented outputs | Low-effort reasoning is a conservative speed/cost choice; premium tier only as explicit alternative. Same tier is used at **all** graph nodes, so there is no cheap classification-tier routing per node |
| `xmartiAgentRag` | Tool-calling agent plus synthesis/assessment/query expansion subcalls; current code requests **temperatures 0.2–0.7** | **Tool calling is mandatory**; multiple model calls make premium default disproportionately expensive. Use capable mid-tier and low reasoning |
| Topicer AI annotation suggestions | External Topicer service and its own model configuration | **Outside this change** and outside the backend LLM gateway; not covered by these tiers or its cost telemetry |

References: [LLM tier catalog](../semant_demo_backend/semant_demo/configs/llm_models.yaml), [gateway](../semant_demo_backend/semant_demo/adapters/llm/gateway.py), [basic RAG](../semant_demo_backend/semant_demo/features/rag/pipelines/rag_generator.py), [adaptive RAG](../semant_demo_backend/semant_demo/features/rag/pipelines/incremental_rag.py), [agentic RAG](../semant_demo_backend/semant_demo/features/rag/pipelines/agentic_rag.py).

The former default tiers were self-hosted Ollama Qwen 2.5 32B (tiny), OpenRouter Gemma 3 12B without a configured price (small), GPT-4.1 mini (medium) and GPT-5.1 (large). This release selects **only OpenRouter-hosted models**; it does not delete the unused Ollama/native Google adapters, nor change provider credentials.

## 2. OpenRouter desk-research shortlist

All costs are **USD per one million input / output tokens** for standard online inference (not batch) as displayed by OpenRouter around **16 October 2026**. Public OpenRouter per-provider p50 latency and throughput are **only indicative**, not semANT end-to-end timings or controlled, same-prompt measurements. Latency varies with prompt length, provider and reasoning effort; the separate throughput number is generation speed. Estimated quality is qualitative, not a measured semANT score.

| Model (OpenRouter ID) | Price in / out | Public speed indication | Reasoning options / likely semANT fit | Decision |
| --- | ---: | --- | --- | --- |
| [Gemma 4 26B A4B](https://openrouter.ai/google/gemma-4-26b-a4b-it) | **$0.042 / $0.22** (cheapest displayed provider; others vary) | Provider performance highly variable (single-digit to ~80 output tok/s) | Reasoning optional; very cheap; multilingual, citation and JSON quality less certain than hosted frontier-tier offerings | **Reserve**, attractive for later, but not the speed/consistency default |
| [Claude Haiku 5.5](https://openrouter.ai/anthropic/claude-haiku-5.5) | **$0.10 / $0.50** | Roughly 1–2.6 s listed p50 provider latency; ~120–200 output tok/s | Adaptive reasoning defaults on, **can be disabled** for short summaries; `low` for RAG. Strong expected instruction following and good throughput at unusually low price | **Select for tiny and small** |
| [GPT-6 Luna](https://openrouter.ai/openai/gpt-6-luna) | **$0.10 / $0.50** | ~1.9–2.6 s; ~55–80 tok/s on standard providers | Effort-controlled reasoning, tools supported; good general alternative but less generation throughput than Haiku | Alternate to Haiku, **not** current default |
| [GPT-5.6 Luna](https://openrouter.ai/openai/gpt-5.6-luna) | $0.20 / $1.20 | ~2.2 s and ~56 tok/s at listed OpenAI endpoint | Low reasoning works; newer GPT-6 Luna is cheaper | Do not select |
| [Gemini 3.5 Flash Lite](https://openrouter.ai/google/gemini-3.5-flash-lite) | $0.30 / $2.50 | Variable provider latency/throughput, including slower Flex routes | Fast focused model but output price above Haiku and expected quality below Flash flagship | Not selected |
| [Gemini 3.8 Flash](https://openrouter.ai/google/gemini-3.8-flash) | **$0.75 / $3.75 temporary 50%-off** (normal list **$1.50 / $7.50**) | ~1.7–2.6 s, ~76–140 tok/s on listed standard endpoints | Stronger expected answer synthesis, multilingual handling, JSON and tools; selectable reasoning `low` for interactivity; OpenRouter public benchmark refers to **high** effort, not our configuration | **Select for medium** |
| [GPT-5.4 mini](https://openrouter.ai/openai/gpt-5.4-mini) | $0.75 / $4.50 | ~0.9–1.3 s; ~37–46 tok/s | Reasoning-capable, good fallback, slower output than Gemini 3.8 Flash by displayed throughput | Not selected |
| [Claude Sonnet 5.5](https://openrouter.ai/anthropic/claude-sonnet-5.5) | **$2.00 / $10.00** | ~1.9–2.7 s, ~79–106 tok/s standard routes | Strong expected synthesis/instruction following; **thinking always on**, `low` effort balances cost; premium multi-call RAG still expensive | **Select as optional large** |
| [GPT-5.1](https://openrouter.ai/openai/gpt-5.1) (previous large) | $1.25 / $10.00 | Provider-dependent | Capable, but older generation and similar output cost to Sonnet 5.5 | Replace |
| [GPT-4.1 mini](https://openrouter.ai/openai/gpt-4.1-mini) (previous medium) | $0.40 / $1.60 | Provider-dependent | Low overhead non-reasoning choice, but newer models provide better expected complex synthesis | Replace |

**Do not compare published benchmark scores at different reasoning effort settings.** For example, OpenRouter lists Artificial Analysis intelligence scores for [Gemini 3.8 Flash at high](https://openrouter.ai/google/gemini-3.8-flash) and [Haiku 5.5 at max](https://openrouter.ai/anthropic/claude-haiku-5.5); they are not our low/off profiles and are not tests of historical documents, Czech or citations.

Pricing caveats:
- OpenRouter can select multiple providers with different endpoint rates; the lowest listed model price is **not a bound** on every routed call.
- Gemini 3.8 Flash currently displays a **50% discount**. To avoid silently underestimating future spending, the configured tier uses the *undiscounted* `$1.50/$7.50` list price for cost telemetry (rather than the currently discounted amount).
- Haiku 5.5 charges **5× the base token rates for prompts above 100,000 tokens**. Long-context, routing, provider changes and cache pricing are not represented in semANT's simple cost estimation. Usage telemetry is still not an enforceable quota; use #371 for quota protection, and retain existing provider spending caps.
- We selected **no batch variants or Flex routes** for synchronous web UX; they can be cheaper but have different latency/availability implications.

## 3. Selected server-side tiers and reasoning policy

| Tier | Model | Reasoning sent via OpenRouter | Temperature | Intended use | Configured price in / out |
| --- | --- | --- | --- | --- | ---: |
| **tiny** | `anthropic/claude-haiku-5.5` | `reasoning.enabled: false` | **Omit** | Frequent search titles, per-hit and overall summaries | $0.10 / $0.50 |
| **small** | `anthropic/claude-haiku-5.5` | `reasoning.effort: low; exclude: true` | **Omit** | Economical basic/adaptive RAG | $0.10 / $0.50 |
| **medium** | `google/gemini-3.8-flash` | `reasoning.effort: low; exclude: true` | Allowed as requested by features | Questions, streamed span discussion, default RAG, agentic RAG | $1.50 / $7.50 (undiscounted conservative) |
| **large** | `anthropic/claude-sonnet-5.5` | `reasoning.effort: low; exclude: true` | **Omit** | Optional premium adaptive RAG | $2.00 / $10.00 |

**Why the same Haiku model for tiny and small?** They represent **different execution profiles**. For abundant short summaries, turn off thinking entirely. For inexpensive RAG, allow modest internal reasoning. Different cost/behavior profiles are useful even where the nominal model price is identical.

**OpenRouter protocol:** all active tiers use `provider: openai` (this means the existing **OpenAI-compatible adapter**), routed to `OPENAI_API_URL`, default `https://openrouter.ai/api/v1`. `reasoning` is passed via LangChain ChatOpenAI `extra_body`; the per-tier `supports_temperature: false` causes the gateway to omit legacy feature-requested temperatures for Claude. This is necessary because [Claude Haiku 5.5 rejects non-default sampling temperatures](https://platform.claude.com/docs/en/models/haiku-5-5/migration-guide). The original feature parameters remain for Gemini and other capable models.

OpenRouter [normalizes reasoning controls](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens). Reasoning tokens **are billed** and generally **consume the response's `max_tokens`** even with `exclude: true`; exclusion only hides returned reasoning. `question` has `max_tokens=300`, so we intentionally use *low* effort instead of `medium` or `high`. Higher effort could improve sophisticated tasks but costs more and risks a truncated/empty answer. Do not claim the public high-effort benchmark scores apply to our low-effort profiles.

## 4. RAG configuration and UX changes

- The default `rag` tier is **medium** (Gemini 3.8 Flash), instead of **large**, to reduce multi-call usage cost. Allowed alternatives remain `small, medium, large`.
- Shipped demo configurations: premium **Adaptive-RAG Sonnet 5.5**; economical **Adaptive-RAG Haiku 5.5**; default-priced **Agentic-RAG Gemini 3.8 Flash**; economical **Basic-RAG Haiku 5.5**. The older optional `configs/rag/configs` folder gets consistent display names too. Some historical **filenames and stable IDs** contain old vendor/model words; they remain unchanged deliberately to avoid breaking saved `rag_id` references.
- Model selection stays on the backend; browser clients cannot send arbitrary provider/model IDs. Tool calling remains configured for `medium` and `large`, and not offered in the `small` RAG tier (the existing agentic use-case rejects that tier).
- RAG citation correctness, multilingual historical/OCR quality, cost per complete operation and real provider routing are **not validated** by this configuration-only decision. Gather feedback or run a targeted check later if the defaults misbehave.

## 5. Verification and rollout

This PR includes fake-provider contract checks for `reasoning`, `temperature` omission, server-side prices/tiers and updated expected provider/model IDs. It intentionally **does not** run a comparative quality/speed study or paid OpenRouter requests.

Before deployment, confirm `OPENAI_API_URL` is OpenRouter and `OPENAI_API_KEY` is valid for the configured account, verify that account allows selected models, and inspect CI/fake-provider checks. Existing #371 backend quotas are **not** implemented here. With genuine traffic, monitor model errors, blank/truncated answers, tool-call failures, per-operation duration and aggregate estimated costs. Revisit model prices periodically, especially promotional Gemini prices.

Further improvements if needed (separate scope): per-node model tiers in adaptive RAG (cheap routing/classification vs stronger answer synthesis); flexible per-feature reasoning effort; preserving OpenRouter encrypted thinking blocks across tool turns; more precise provider usage accounting for caching/long context. None is required to select today's defaults.
