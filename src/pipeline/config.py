"""config.py — все константы и настройки проекта."""

import json
import os
from pathlib import Path

# Corpus-root resolution.
#
# The corpus (PDFs, metadata.sqlite, clinrecs.json, knowledge_base.json) is a
# large research asset deliberately kept OUTSIDE git. It used to be resolved as
# ``Path(__file__).parents[3] / "clinrec_downloader"`` — a Windows-layout
# assumption: with the repo at ``C:\ANTIBIO``, ``C:\ANTIBIO\src\pipeline\config.py``
# reached ``C:\`` and so produced ``C:\clinrec_downloader``. On any other layout
# that expression silently returned a non-existent path, and it changed meaning
# whenever this file changed depth (the L-31 defect class already fixed in
# ``src/pipeline/extraction/config.py``).
#
# Resolution order — deliberately the same as the sanctioned engine locator
# ``clinical_engine/corpus/locator.py``, so the two layers can never disagree:
#   1. env ``ANTIBIO_CORPUS_DIR``                          — documented override
#   2. ``clinical_engine/corpus/corpus_config.json``        — committed default
#   3. sibling of the repository root                       — legacy fallback

_REPO_MARKER = Path("pyproject.toml")
_CORPUS_ENV_VAR = "ANTIBIO_CORPUS_DIR"
_CORPUS_CONFIG_REL = Path("clinical_engine") / "corpus" / "corpus_config.json"
_CORPUS_DIR_NAME = "clinrec_downloader"


def repo_root() -> Path:
    """Repository root, located by marker rather than by fixed depth."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / _REPO_MARKER).is_file():
            return candidate
    # Same file depth as today; only reached outside a real checkout.
    return here.parents[2]


def _configured_corpus_dir() -> str | None:
    """The committed default from ``corpus_config.json``, or ``None``.

    Reads the JSON directly instead of importing ``clinical_engine``: this
    package currently has no dependency on the engine layer, and adding one
    would be an architectural change, not a path fix.
    """
    try:
        data = json.loads((repo_root() / _CORPUS_CONFIG_REL).read_text(encoding="utf-8"))
    except Exception:
        return None
    value = data.get("corpus_dir")
    if value is None:
        return None
    return str(value).strip() or None


def resolve_corpus_dir(env: dict | None = None) -> Path:
    """Corpus root: env override → committed config → repo-root sibling.

    Pure path resolution — it does not check that the path exists.
    """
    env = os.environ if env is None else env
    override = env.get(_CORPUS_ENV_VAR)
    if override and override.strip():
        return Path(override.strip())
    configured = _configured_corpus_dir()
    if configured:
        return Path(configured)
    return repo_root().parent / _CORPUS_DIR_NAME


BASE_DIR = resolve_corpus_dir()
# BASE_DIR == corpus root: PDFs, SQLite, JSON. Never committed to git.

API_BASE = "https://apicr.minzdrav.gov.ru"
API_LIST = f"{API_BASE}/api.ashx?op=GetJsonClinrecsFilterV2"
API_GET_PDF = f"{API_BASE}/api.ashx?op=GetClinrecPdf"

CLINRECS_JSON = BASE_DIR / "clinrecs.json"
DOWNLOADS_ALL = BASE_DIR / "downloads_all"
DOWNLOADS_ACTIVE = BASE_DIR / "downloads_active"
DOWNLOADS_ABX = BASE_DIR / "downloads_antibiotics"
DOWNLOADS_OTHER = BASE_DIR / "downloads_other"
DB_PATH = BASE_DIR / "metadata.sqlite"
ABX_JSON = BASE_DIR / "antibiotic_guidelines.json"

MAX_CONCURRENT = 10
REQUEST_TIMEOUT = 60
RETRY_COUNT = 5
RETRY_BACKOFF = 2
CHUNK_SIZE = 65536

WINDOWS_FORBIDDEN = '<>:"/\\|?*'
WINDOWS_FORBIDDEN_MAP = str.maketrans({
    '<':  '〈',   '>':  '〉',   ':':  ' -',
    '"':  "'",    '/':  '_',   '\\': '_',
    '|':  '-',    '?':  '',    '*':  '',
})

ANTIBIOTIC_NAMES = [
    "амоксициллин", "амоксициллин/клавуланат", "амоксициллина клавуланат",
    "ампициллин", "оксациллин", "пенициллин", "бензилпенициллин",
    "цефазолин", "цефалексин", "цефуроксим", "цефиксим",
    "цефтриаксон", "цефотаксим", "цефтазидим", "цефепим", "цефтаролин",
    "меропенем", "имипенем", "эртапенем", "дорипенем",
    "пиперациллин", "тазобактам", "пиперациллин-тазобактам",
    "азитромицин", "кларитромицин", "эритромицин", "джозамицин", "спирамицин",
    "доксициклин", "тетрациклин",
    "левофлоксацин", "ципрофлоксацин", "моксифлоксацин", "офлоксацин", "норфлоксацин",
    "амикацин", "гентамицин", "тобрамицин", "нетилмицин",
    "линезолид", "ванкомицин", "тейкопланин", "даптомицин",
    "клиндамицин", "метронидазол", "тинидазол",
    "рифампицин", "рифаксимин",
    "ко-тримоксазол", "триметоприм", "сульфаметоксазол",
    "нитрофурантоин", "фуразидин", "фосфомицин",
    "тигециклин", "колистин", "полимиксин",
    "цефтазидим-авибактам", "цефтазидима авибактам",
    "меропенем-ваборбактам", "меропенема ваборбактам",
    "цефтолозан-тазобактам", "цефтолозана тазобактам",
]

ANTIBIOTIC_KEYWORDS = [
    "антибиотик", "антибиотики",
    "антибактериальный", "антибактериальная терапия", "антибактериальной терапии",
    "антимикробная терапия", "антимикробной терапии",
    "антибиотикотерапия", "антибиотикопрофилактика",
    "этиотропная терапия", "этиотропной терапии",
    "эмпирическая терапия", "эмпирической терапии",
    "деэскалация терапии",
    "профилактическое назначение антибиотиков",
    "хирургическая антибиотикопрофилактика",
    "антимикробный", "антимикробное",
]

ADDITIONAL_TERMS = [
    "AWaRe", "J01", "резистентность", "чувствительность",
    "бактериальная инфекция", "бактериальный",
    "грамположительный", "грамотрицательный",
    "микробиологическое исследование",
    "посев", "антибиотикограмма",
    "антибиотикорезистентность",
]

EXTRACTION_VERSION = "1.0"

LLM_PROVIDER_CHAIN = ["deepseek", "anthropic"]

LLM_PROVIDER_CONFIGS = {
    "anthropic": {
        "base_url": "https://vip.j3gb.com/v1",
        "api_key": os.environ.get("ANTIBIO_ANTHROPIC_API_KEY", ""),
        "model": "claude-sonnet-4-20250514",
        "timeout": 300,
        "max_retries": 6,
    },
    "deepseek": {
        "base_url": "https://opencode.ai/zen/go/v1",
        "api_key": os.environ.get("ANTIBIO_DEEPSEEK_API_KEY", ""),
        "model": "deepseek-v4-flash",
        "timeout": 120,
        "max_retries": 1,
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": os.environ.get("ANTIBIO_OPENROUTER_API_KEY", ""),
        "model": "qwen3-14b",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key": os.environ.get("ANTIBIO_OPENAI_API_KEY", ""),
        "model": "gpt-4o",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key": os.environ.get("ANTIBIO_GEMINI_API_KEY", ""),
        "model": "gemini-2.5-flash",
    },
    "ollama": {
        "base_url": "http://127.0.0.1:11434",
        "model": "qwen3:14b",
    },
    "vllm": {
        "base_url": "http://127.0.0.1:8000/v1",
        "model": "qwen3-14b",
    },
    "local": {
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "qwen3:14b",
    },
}

EXTRACTION_MODEL = "deepseek-v4-flash"
VALIDATION_MODEL = "deepseek-v4-flash"
LLM_TIMEOUT = 300
LLM_MAX_RETRIES = 6
LLM_CONCURRENCY = 1
LLM_DELAY = 2.0

EXTRACTION_RAW_JSON = BASE_DIR / "extraction_raw.json"
EXTRACTION_VALIDATED_JSON = BASE_DIR / "extraction_validated.json"
REVIEW_REQUIRED_JSON = BASE_DIR / "review_required.json"
KNOWLEDGE_BASE_JSON = BASE_DIR / "knowledge_base.json"
EXTRACTION_PROGRESS_JSON = BASE_DIR / "extraction_progress.json"

SECTION_PATTERNS = [
    r"(?:^|\n)\s*(?:(?:РАЗДЕЛ\s+|Раздел\s+)?\d+(?:\.\d+)*[\.\)]?\s*)?(Лечение|Консервативное лечение|Медикаментозная терапия|Антибактериальная терапия|Этиотропная терапия|Эмпирическая терапия|Антибиотикопрофилактика|Антимикробная терапия|Хирургическая антибиотикопрофилактика|Периоперационная профилактика|Профилактика)",
]

DOSING_PATTERNS = [
    r"\d+\s*(?:мг|г|мг/кг|МЕ|мл|г/сут|мг/сут|мг/кг/сут)\b",
    r"(?:раз в день|каждые\s*\d+\s*(?:ч|час)|\d+\s*раз/сут|сут|курс\s*\d+|внутрь|внутривенно|внутримышечно)",
]

ATC_MAP = {
    "амоксициллин": ("amoxicillin", "J01CA04"),
    "амоксициллин/клавуланат": ("amoxicillin_clavulanate", "J01CR02"),
    "амоксициллина клавуланат": ("amoxicillin_clavulanate", "J01CR02"),
    "ампициллин": ("ampicillin", "J01CA01"),
    "оксациллин": ("oxacillin", "J01CF04"),
    "пенициллин": ("benzylpenicillin", "J01CE01"),
    "бензилпенициллин": ("benzylpenicillin", "J01CE01"),
    "цефазолин": ("cefazolin", "J01DB04"),
    "цефалексин": ("cephalexin", "J01DB01"),
    "цефуроксим": ("cefuroxime", "J01DC02"),
    "цефиксим": ("cefixime", "J01DD08"),
    "цефтриаксон": ("ceftriaxone", "J01DD04"),
    "цефотаксим": ("cefotaxime", "J01DD01"),
    "цефтазидим": ("ceftazidime", "J01DD02"),
    "цефепим": ("cefepime", "J01DE01"),
    "цефтаролин": ("ceftaroline", "J01DI01"),
    "меропенем": ("meropenem", "J01DH02"),
    "имипенем": ("imipenem", "J01DH51"),
    "эртапенем": ("ertapenem", "J01DH03"),
    "дорипенем": ("doripenem", "J01DH05"),
    "пиперациллин": ("piperacillin", "J01CA12"),
    "пиперациллин-тазобактам": ("piperacillin_tazobactam", "J01CR05"),
    "азитромицин": ("azithromycin", "J01FA10"),
    "кларитромицин": ("clarithromycin", "J01FA09"),
    "эритромицин": ("erythromycin", "J01FA01"),
    "джозамицин": ("josamycin", "J01FA07"),
    "спирамицин": ("spiramycin", "J01FA02"),
    "доксициклин": ("doxycycline", "J01AA02"),
    "тетрациклин": ("tetracycline", "J01AA01"),
    "левофлоксацин": ("levofloxacin", "J01MA12"),
    "ципрофлоксацин": ("ciprofloxacin", "J01MA02"),
    "моксифлоксацин": ("moxifloxacin", "J01MA14"),
    "офлоксацин": ("ofloxacin", "J01MA01"),
    "норфлоксацин": ("norfloxacin", "J01MA06"),
    "амикацин": ("amikacin", "J01GB06"),
    "гентамицин": ("gentamicin", "J01GB03"),
    "тобрамицин": ("tobramycin", "J01GB01"),
    "нетилмицин": ("netilmicin", "J01GB05"),
    "линезолид": ("linezolid", "J01XX08"),
    "ванкомицин": ("vancomycin", "J01XA01"),
    "тейкопланин": ("teicoplanin", "J01XA02"),
    "даптомицин": ("daptomycin", "J01XX09"),
    "клиндамицин": ("clindamycin", "J01FF01"),
    "метронидазол": ("metronidazole", "J01XD01"),
    "тинидазол": ("tinidazole", "J01XD02"),
    "рифампицин": ("rifampicin", "J04AB02"),
    "рифаксимин": ("rifaximin", "J04AX04"),
    "ко-тримоксазол": ("cotrimoxazole", "J01EE01"),
    "триметоприм": ("trimethoprim", "J01EA01"),
    "сульфаметоксазол": ("sulfamethoxazole", "J01EC01"),
    "нитрофурантоин": ("nitrofurantoin", "J01XE01"),
    "фуразидин": ("furazidin", "J01XE03"),
    "фосфомицин": ("fosfomycin", "J01XX01"),
    "тигециклин": ("tigecycline", "J01AA12"),
    "колистин": ("colistin", "J01XB01"),
    "полимиксин": ("polymyxin_b", "J01XB02"),
}
