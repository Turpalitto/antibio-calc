import asyncio
import json
import logging
import re
from typing import Any

import httpx

from config import EXTRACTION_MODEL, EXTRACTION_VERSION, LLM_DELAY, VALIDATION_MODEL
from llm.llm_provider import create_provider

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT_SYSTEM = (
    "Ты врач-клинический фармаколог. Извлеки все схемы антибактериальной терапии "
    "из текста клинической рекомендации. Верни СТРОГО JSON массив."
)

_VALIDATION_PROMPT_SYSTEM = (
    "Ты аудитор медицинских данных. Проверь извлечённые схемы "
    "на соответствие исходному тексту."
)

_SOURCE_FIELDS = [
    "guideline_name", "code_version", "pdf_file",
    "page_number", "section_name", "source_quote",
]


def parse_llm_json(content: str) -> list | dict:
    content = content.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if fence_match:
        content = fence_match.group(1).strip()
    decoder = json.JSONDecoder()
    for start_char in ("[", "{"):
        start = content.find(start_char)
        if start == -1:
            continue
        try:
            obj, _ = decoder.raw_decode(content, start)
            return obj
        except json.JSONDecodeError:
            continue
    raise json.JSONDecodeError("No valid JSON found", content, 0)


MAX_TEXT_CHARS = 8000


def _truncate_text(text: str, max_chars: int = MAX_TEXT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[... текст обрезан ...]"


def _build_extraction_prompt(item: dict, section_data: dict) -> str:
    clinrec_name = item.get("Name", "")
    code_version = item.get("CodeVersion", "")
    pdf_filename = item.get("pdf_path", "").split("\\")[-1].split("/")[-1] if item.get("pdf_path") else ""
    mkb_codes = ", ".join(m.get("MkbCode", "") for m in (item.get("Mkbs") or []))
    relevant_text = _truncate_text(section_data.get("relevant_text", ""))
    page_range = str(section_data.get("relevant_pages", []))

    return f"""Клиническая рекомендация: {clinrec_name}
CodeVersion: {code_version}
МКБ: {mkb_codes}

Текст:
{relevant_text}

Извлеки схемы антибактериальной терапии. Для каждой:
- diagnosis, mkb, regimen_type (first_line|alternative|prophylaxis|empiric)
- antibiotic (как в тексте; если OR/или список без отдельных доз — оставь полное выражение как один antibiotic, не выдумывай варианты)
- dose, unit (мг|г|мг/кг|МЕ|мл)
- frequency, route (внутрь|в/в|в/м), duration, age_group (точно из текста, включая "с 3 месяцев" и т.п.)
- page_number (из маркера "--- Страница N ---")
- section_name, source_quote (точная цитата, полная для схемы)

Верни JSON массив []. Если нет схем — []. Если OR-блок без доз — всё равно извлеки как один с полным antibiotic."""


def _build_validation_prompt(regimens: list[dict], section_data: dict) -> str:
    relevant_text = _truncate_text(section_data.get("relevant_text", ""))
    page_range = str(section_data.get("relevant_pages", []))
    regimens_json = json.dumps(regimens, ensure_ascii=False, indent=2)

    return f"""Исходный текст (страницы {page_range}):
{relevant_text}

Извлечённые схемы (JSON):
{regimens_json}

Проверь каждую схему:
1. Соответствует ли JSON исходному тексту?
2. Указаны ли guideline_name, code_version, pdf_file, page_number, section_name?
3. Есть ли source_quote и соответствует ли она тексту?
4. Нет ли выдуманных дозировок?
5. Правильно ли указаны названия антибиотиков?
6. Правильно ли указаны возрастные группы?
7. Правильно ли указана длительность?

Верни JSON:
{{
  "results": [
    {{
      "index": 0,
      "valid": true,
      "confidence": 0.0-1.0,
      "issues": [],
      "corrected": null
    }}
  ]
}}"""


async def extract_regimens(item: dict, section_data: dict) -> list[dict]:
    if not section_data.get("relevant_text"):
        return []

    user_prompt = _build_extraction_prompt(item, section_data)

    provider = create_provider()
    try:
        response = await provider.chat(_EXTRACTION_PROMPT_SYSTEM, user_prompt, model=EXTRACTION_MODEL)
    finally:
        await provider.close()
    await asyncio.sleep(LLM_DELAY)

    try:
        msg = response["choices"][0]["message"]
        content = msg.get("content", "")
        reasoning = msg.get("reasoning_content", "")
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"LLM response missing content: {response}") from exc

    # If content empty or not parseable, try reasoning_content
    if not content.strip() and reasoning.strip():
        logger.info("Content empty for %s, extracting JSON from reasoning_content", item.get("Id"))
        # Find JSON array in reasoning text
        json_match = re.search(r"(\[.*?\]|\{.*\})", reasoning, re.DOTALL)
        if json_match:
            content = json_match.group(1)

    regimens = []
    if content.strip():
        try:
            regimens = parse_llm_json(content)
        except Exception:
            # Also try extracting JSON array from content via regex
            json_match = re.search(r"(\[.*?\])", content, re.DOTALL)
            if json_match:
                try:
                    regimens = parse_llm_json(json_match.group(1))
                except Exception:
                    pass

    if not isinstance(regimens, list):
        regimens = [regimens] if regimens else []

    # Filter out non-dict entries (model sometimes returns bare numbers/strings)
    regimens = [r for r in regimens if isinstance(r, dict)]

    clinrec_name = item.get("Name", "")
    code_version = item.get("CodeVersion", "")
    pdf_filename = item.get("pdf_path", "").split("\\")[-1].split("/")[-1] if item.get("pdf_path") else ""

    for r in regimens:
        if not r.get("guideline_name"):
            r["guideline_name"] = clinrec_name
        if not r.get("code_version"):
            r["code_version"] = code_version
        if not r.get("pdf_file"):
            r["pdf_file"] = pdf_filename
        if not r.get("diagnosis"):
            r["diagnosis"] = clinrec_name

    return regimens


async def validate_regimens(regimens: list[dict], section_data: dict) -> list[dict]:
    if not regimens:
        return []

    user_prompt = _build_validation_prompt(regimens, section_data)

    provider = create_provider()
    try:
        response = await provider.chat(_VALIDATION_PROMPT_SYSTEM, user_prompt, model=VALIDATION_MODEL)
    finally:
        await provider.close()
    await asyncio.sleep(LLM_DELAY)

    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"LLM response missing content: {response}") from exc
    result = parse_llm_json(content)

    if isinstance(result, dict) and "results" in result:
        return result["results"]
    elif isinstance(result, list):
        return result
    else:
        return [{"index": 0, "valid": False, "confidence": 0.0, "issues": ["malformed validation response"], "corrected": None}]


def check_source_fields(regimen: dict) -> bool:
    for field in _SOURCE_FIELDS:
        val = regimen.get(field)
        if not val or (isinstance(val, str) and not val.strip()):
            return False
    return True
