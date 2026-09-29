import json
from unittest.mock import patch, AsyncMock

import pytest

from extractor_llm import (
    _DATA_FENCE_END,
    _DATA_FENCE_START,
    _build_extraction_prompt,
    _build_validation_prompt,
    close_shared_provider,
    extract_regimens,
    parse_llm_json,
    source_quote_supported,
    validate_regimens,
)
from llm.cache import LLMCache
from llm.json_payload import LLMJSONParseError
from llm.llm_provider import LLMProvider


def test_parse_llm_json_plain():
    result = parse_llm_json('[{"a": 1}]')
    assert result == [{"a": 1}]


def test_parse_llm_json_with_fences():
    result = parse_llm_json('```json\n[{"a": 1}]\n```')
    assert result == [{"a": 1}]


@pytest.mark.parametrize("raw", [
    '{"results": []}',
    '```json\n{"results": []}\n```',
    'Ответ модели: {"results": []}',
])
def test_parse_llm_json_object(raw):
    """F-1: this was `xfail(strict=False)`, so it passed whether or not C-6 was fixed.

    The old implementation probed "[" before "{", so `{"results": []}` came back as
    the `[1]` fragment of any list-looking text that happened to appear first.
    """
    assert parse_llm_json(raw) == {"results": []}


def test_parse_llm_json_empty_array():
    result = parse_llm_json('[]')
    assert result == []


@pytest.mark.asyncio
async def test_extract_regimens_returns_list(sample_item, mock_llm_extract_response):
    section_data = {
        "relevant_text": "Амоксициллин 500 мг 3 раза в день",
        "relevant_pages": [12],
        "sections_found": [{"section": "Лечение", "page": 12}],
    }
    with patch("extractor_llm.create_provider") as provider_factory:
        provider = AsyncMock(spec=LLMProvider)
        provider.chat.return_value = mock_llm_extract_response
        provider_factory.return_value = provider
        regimens = await extract_regimens(sample_item, section_data)

    assert len(regimens) == 1
    assert regimens[0]["antibiotic"] == "амоксициллин"
    assert regimens[0]["antibiotic_normalized"] == "amoxicillin"
    assert regimens[0]["guideline_name"] == "Внебольничная пневмония"
    assert "source_quote" in regimens[0]


@pytest.mark.asyncio
async def test_extract_regimens_empty(sample_item):
    section_data = {"relevant_text": "", "relevant_pages": [], "sections_found": []}
    with patch("extractor_llm.create_provider") as provider_factory:
        provider = AsyncMock(spec=LLMProvider)
        provider.chat.return_value = {"choices": [{"message": {"content": "[]"}}]}
        provider_factory.return_value = provider
        regimens = await extract_regimens(sample_item, section_data)

    assert regimens == []


@pytest.mark.asyncio
async def test_validate_regimens_pass(sample_regimen, mock_llm_validate_response):
    section_data = {"relevant_text": "Амоксициллин 500-1000 мг 3 раза в день"}
    with patch("extractor_llm.create_provider") as provider_factory:
        provider = AsyncMock(spec=LLMProvider)
        provider.chat.return_value = mock_llm_validate_response
        provider_factory.return_value = provider
        results = await validate_regimens([sample_regimen], section_data)

    assert len(results) == 1
    assert results[0]["valid"] is True
    assert results[0]["confidence"] >= 0.9


@pytest.mark.asyncio
async def test_validate_regimens_fail(sample_regimen):
    section_data = {"relevant_text": "Нет антибиотиков здесь."}
    fail_response = {
        "choices": [{
            "message": {
                "content": '{"results":[{"index":0,"valid":false,"confidence":0.3,"issues":["dose not found in text"],"corrected":null}]}'
            }
        }]
    }
    with patch("extractor_llm.create_provider") as provider_factory:
        provider = AsyncMock(spec=LLMProvider)
        provider.chat.return_value = fail_response
        provider_factory.return_value = provider
        results = await validate_regimens([sample_regimen], section_data)

    assert results[0]["valid"] is False
    assert results[0]["confidence"] < 0.9
    assert len(results[0]["issues"]) > 0


# ---------------------------------------------------------------------------
# C-6 -- a truncated or unrecoverable LLM payload must RAISE, never resolve to a
# partial/wrong object.  The old code returned the `[1]` fragment of
# `Список: [1] и ещё текст. {"dose": ...}` and the inner `{"dose": "500 мг"}` of a
# truncated array, silently emptying extraction_validated.json.
# ---------------------------------------------------------------------------

def test_parse_llm_json_prefers_the_real_object_over_a_prose_list_fragment():
    assert parse_llm_json('Список: [1] и ещё текст. {"dose":"500 мг"}') == {"dose": "500 мг"}


def test_parse_llm_json_lifts_the_payload_out_of_surrounding_prose():
    raw = 'Вот результат:\n[{"dose":"500 мг"}]\nСпасибо.'
    assert parse_llm_json(raw) == [{"dose": "500 мг"}]


def test_parse_llm_json_raises_on_truncated_array():
    with pytest.raises(LLMJSONParseError):
        parse_llm_json('[{"dose":"500 мг"},{"dose":"')


def test_parse_llm_json_raises_on_truncated_object():
    with pytest.raises(LLMJSONParseError):
        parse_llm_json('{"results":[{"index":0,')


def test_parse_llm_json_raises_on_truncated_fenced_array():
    with pytest.raises(LLMJSONParseError):
        parse_llm_json('```json\n[{"a":\n```')


def test_parse_llm_json_raises_on_no_json_at_all():
    with pytest.raises(LLMJSONParseError):
        parse_llm_json("модель ответила словами без JSON")


def test_parse_llm_json_raises_on_empty_content():
    with pytest.raises(LLMJSONParseError):
        parse_llm_json("   ")


def test_parse_llm_json_ignores_braces_inside_strings():
    raw = '{"source_quote": "ампоксициллин 500 мг [внутрь]", "dose": "500"}'
    assert parse_llm_json(raw) == {
        "source_quote": "ампоксициллин 500 мг [внутрь]", "dose": "500",
    }


def test_llm_json_parse_error_is_a_jsondecodeerror():
    assert issubclass(LLMJSONParseError, json.JSONDecodeError)


# ---------------------------------------------------------------------------
# M-21 / M-22 -- the guideline text is untrusted data and a corrected quote must
# be present in the source before it may be believed.
# ---------------------------------------------------------------------------

def test_prompts_fence_the_untrusted_source_text():
    section = {"relevant_text": "Амоксициллин 500 мг", "relevant_pages": [1]}
    prompt = _build_extraction_prompt({"Name": "ВП", "CodeVersion": "1_1"}, section)
    assert _DATA_FENCE_START in prompt and _DATA_FENCE_END in prompt
    assert "НЕПРОВЕРЕННЫЕ ДАННЫЕ" in prompt
    validate_prompt = _build_validation_prompt([{"a": 1}], section)
    assert _DATA_FENCE_START in validate_prompt and _DATA_FENCE_END in validate_prompt


def test_validation_prompt_asks_for_an_explicit_index():
    prompt = _build_validation_prompt([{"a": 1}], {"relevant_text": "x", "relevant_pages": []})
    assert '"index"' in prompt
    assert "index" in prompt.lower()


@pytest.mark.parametrize("quote,expected", [
    ("Амоксициллин 500 мг 3 раза в день", True),
    ("Амоксициллин   500 мг\n3 раза в день", True),   # re-wrapped PDF text
    ("Амоксициллин 5000 мг", False),                  # invented dose
    ("", False),
    (None, False),
    (123, False),
])
def test_source_quote_supported_requires_containment(quote, expected):
    section = {"relevant_text": "Амоксициллин 500 мг 3 раза в день в течение 7-10 дней"}
    assert source_quote_supported(quote, section) is expected


@pytest.mark.asyncio
async def test_validate_regimens_raises_on_unrecoverable_payload(sample_regimen):
    """C-6: a truncated verdict must fail the guideline, not blank the output file."""
    truncated = {"choices": [{"message": {"content": '[{"index":0,"valid":' }}]}
    with patch("extractor_llm.create_provider") as provider_factory:
        provider = AsyncMock(spec=LLMProvider)
        provider.chat.return_value = truncated
        provider_factory.return_value = provider
        with pytest.raises(LLMJSONParseError):
            await validate_regimens([sample_regimen], {"relevant_text": "x"})


@pytest.mark.asyncio
async def test_validate_regimens_raises_on_prose_only_payload(sample_regimen):
    with patch("extractor_llm.create_provider") as provider_factory:
        provider = AsyncMock(spec=LLMProvider)
        provider.chat.return_value = {
            "choices": [{"message": {"content": "Извините, я не могу выполнить запрос."}}]
        }
        provider_factory.return_value = provider
        with pytest.raises(LLMJSONParseError):
            await validate_regimens([sample_regimen], {"relevant_text": "x"})


@pytest.mark.asyncio
async def test_validate_regimens_drops_non_object_results(sample_regimen):
    payload = '{"results":[{"index":0,"valid":true,"confidence":0.95}, "мусор"]}'
    with patch("extractor_llm.create_provider") as provider_factory:
        provider = AsyncMock(spec=LLMProvider)
        provider.chat.return_value = {"choices": [{"message": {"content": payload}}]}
        provider_factory.return_value = provider
        results = await validate_regimens([sample_regimen], {"relevant_text": "x"})
    assert results == [{"index": 0, "valid": True, "confidence": 0.95}]


# ---------------------------------------------------------------------------
# H-28 -- the provider (and therefore the cache and the connection pool) is
# constructed per PROCESS, not per call.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shared_provider_is_created_once_and_reused(mock_llm_extract_response):
    with patch("extractor_llm.create_provider") as provider_factory:
        provider = AsyncMock(spec=LLMProvider)
        provider.chat.return_value = mock_llm_extract_response
        provider_factory.return_value = provider
        section = {"relevant_text": "Амоксициллин 500 мг 3 раза в день", "relevant_pages": [1]}
        await extract_regimens({"Name": "ВП", "CodeVersion": "1_1"}, section)
        await extract_regimens({"Name": "ВП2", "CodeVersion": "1_2"}, section)
        assert provider_factory.call_count == 1
        assert provider.close.await_count == 0, "per-call close() destroys the cache"


@pytest.mark.asyncio
async def test_close_shared_provider_is_idempotent():
    await close_shared_provider()
    await close_shared_provider()


# ---------------------------------------------------------------------------
# LLM cache key must cover everything that can change the answer (H-28).
# ---------------------------------------------------------------------------

def test_cache_key_covers_temperature_and_provider_chain():
    base = LLMCache.make_key("s", "u", "m")
    assert base != LLMCache.make_key("s", "u", "m", temperature=0.9)
    assert base != LLMCache.make_key("s", "u", "m", provider_chain=["anthropic"])
    assert base != LLMCache.make_key("s", "u", "m", max_tokens=8192)
    assert base == LLMCache.make_key("s", "u", "m", temperature=0.0, provider_chain=[])
    # key order in the extra kwargs must not change the key
    assert LLMCache.make_key("s", "u", "m", a=1, b=2) == LLMCache.make_key("s", "u", "m", b=2, a=1)


def test_cache_eviction_is_lru_and_keeps_size_bounded():
    cache = LLMCache(max_size=3)
    for i in range(5):
        cache.set(f"k{i}", {"i": i})
    assert cache.size == 3
    # the most recently used key survived, the oldest did not
    assert cache.get("k4") == {"i": 4}
    assert cache.get("k0") is None
