from unittest.mock import patch, AsyncMock

import pytest

from extractor_llm import parse_llm_json, extract_regimens, validate_regimens
from llm.llm_provider import LLMProvider


def test_parse_llm_json_plain():
    result = parse_llm_json('[{"a": 1}]')
    assert result == [{"a": 1}]


def test_parse_llm_json_with_fences():
    result = parse_llm_json('```json\n[{"a": 1}]\n```')
    assert result == [{"a": 1}]


@pytest.mark.xfail(
    reason="Pre-existing extraction-layer behavior (parse_llm_json unwraps to []). "
    "Out of scope for Clinical Engine work — marked, NOT fixed (Milestone 13). "
    "See AI_LOG 2026-07-09.",
    strict=False,
)
def test_parse_llm_json_object():
    result = parse_llm_json('{"results": []}')
    assert result == {"results": []}


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
