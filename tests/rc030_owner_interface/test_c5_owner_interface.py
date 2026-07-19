"""RC-030 C5 — governance tests for the offline owner-review interface's
deterministic builder and generated HTML. Exercises the actual CLI
(subprocess) rather than importing generated/rc030_recovery/build_interface.py
as a package, since that directory is a build workspace, not an installed
package. Static source scans (network/innerHTML/leak checks) run against
the real template and real built output — not assumed clean.

No real database touched. No network access. No genuine owner event
created (all test data is synthetic, matching the discipline used
elsewhere in the RC-030 test suite).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RECOVERY_DIR = ROOT / "generated" / "rc030_recovery"
BUILDER = RECOVERY_DIR / "build_interface.py"
TEMPLATE = RECOVERY_DIR / "owner_review_template.html"
DATASET_ALL = RECOVERY_DIR / "owner_review_data.json"

# owner_control_sample_data.json is intentionally NOT committed (it bundles
# AI-audit comparison fields per record — see RC030_C5_EXACT_ALLOWLIST.md).
# Tests that need "a control-mode dataset" build a small synthetic one
# instead of depending on that excluded file, so this suite runs fully in a
# fresh clone rather than silently skipping (a real gap caught during this
# turn's fresh-clone verification — the original version of this file gated
# every test behind that file's presence).
DATASET_CONTROL = RECOVERY_DIR / "owner_control_sample_data.json"  # optional, local-only

pytestmark = pytest.mark.skipif(
    not (BUILDER.is_file() and TEMPLATE.is_file() and DATASET_ALL.is_file()),
    reason="RC-030 owner-review interface build workspace not present in this checkout",
)


def _run_builder(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BUILDER), *args],
        capture_output=True, text=True, cwd=str(ROOT),
    )


def _synthetic_control_dataset(tmp_path: Path, n: int = 3) -> Path:
    """A small synthetic stand-in for the excluded AI-bearing control-sample
    dataset, matching its record shape closely enough to exercise the
    builder's `--mode control` path without needing the excluded file."""
    records = [
        {
            "regimen_id": str(1000 + i), "regimen_version": 1,
            "evidence_hash": f"{i:064x}", "pdf_hash": f"{(i+1):064x}",
            "source_pdf": f"synthetic_{i}.pdf", "source_page": "1",
            "source_quote": "synthetic quote", "context_before": "", "context_after": "",
            "antibiotic": "test", "diagnosis": "test", "dose": 1, "unit": "g",
            "route": "iv", "frequency": 1, "duration_recommended": 1,
            "parser_candidate": "FIXED_PER_DAY", "parser_version": "v" * 8,
            "ai_proposed_verdict": "CORRECT_FIXED_DAILY", "ai_confidence": 0.9,
            "ai_evidence_explanation": "synthetic", "ai_risk_flags": [],
            "workload_category": "A",
        }
        for i in range(n)
    ]
    path = tmp_path / "synthetic_control_dataset.json"
    path.write_text(json.dumps({"schema_version": 1, "records": records}), encoding="utf-8")
    return path


# ── Deterministic build (Phase 17) ────────────────────────────────────────

def test_builder_help_text():
    result = _run_builder("--help")
    assert result.returncode == 0
    assert "--dataset" in result.stdout
    assert "--mode" in result.stdout
    assert "--check" in result.stdout


def test_control_mode_always_stamps_test_event_true():
    """C7 regression: test_event was hardcoded false in the event-creation
    function for every mode, including 'control' -- browser-synthetic
    verdicts recorded on the control-sample interface were silently
    indistinguishable from genuine OWNER_LOCAL events by this flag. Found
    by inspecting a real event recorded during C7 Part VII browser
    validation. The fix must reference both a per-record test_event flag
    and MODE === "control" in the event object literal."""
    source = TEMPLATE.read_text(encoding="utf-8")
    assert 'test_event: r.test_event === true || MODE === "control"' in source


def test_dataset_pdf_hash_field_name_matches_template_reader():
    """C7 regression: the template reads r.pdf_hash (lowercase) and embeds
    it directly into every exported owner_fidelity_event; a dataset using
    'PDF_hash' (capitalized) silently produced `undefined`, which
    JSON.stringify drops -- every such event failed C4's validate_events()
    'missing required field' check. This is a real bug found by validating
    an actual browser-exported event under the committed C4 validator, not
    by static inspection alone."""
    source = TEMPLATE.read_text(encoding="utf-8")
    assert "r.pdf_hash" in source
    dataset = json.loads(DATASET_ALL.read_text(encoding="utf-8"))
    for r in dataset["records"][:5]:
        assert "PDF_hash" not in r, "dataset uses the wrong-case key that the template silently ignores"


def test_double_build_is_byte_identical(tmp_path):
    out1 = tmp_path / "build1.html"
    out2 = tmp_path / "build2.html"
    r1 = _run_builder("--dataset", str(DATASET_ALL), "--output", str(out1), "--mode", "all")
    r2 = _run_builder("--dataset", str(DATASET_ALL), "--output", str(out2), "--mode", "all")
    assert r1.returncode == 0, r1.stderr
    assert r2.returncode == 0, r2.stderr
    assert out1.read_bytes() == out2.read_bytes()


def test_printed_hash_matches_actual_file_bytes(tmp_path):
    """C7 regression: build_interface.py used to compute content_hash from a
    pre-write LF-only string, then write via write_text() without pinning
    newline, which applies platform newline translation (LF -> CRLF on
    Windows) -- the printed sha256 in the 'built ...' message never matched
    sha256(output_path.read_bytes()), even though --check still reported OK
    (it re-read through the same translation, comparing two LF-normalized
    strings to each other, never to the real file bytes). Any external hash
    check (sha256sum, fresh-clone verification) would disagree with the
    tool's own printed hash. Fixed by reading/writing with newline="\\n"
    pinned and asserting written bytes match before returning."""
    out = tmp_path / "hash_check.html"
    r = _run_builder("--dataset", str(DATASET_ALL), "--output", str(out), "--mode", "all")
    assert r.returncode == 0, r.stderr
    printed_hash = re.search(r"sha256=([0-9a-f]{64})", r.stdout).group(1)
    actual_hash = __import__("hashlib").sha256(out.read_bytes()).hexdigest()
    assert printed_hash == actual_hash


def test_check_mode_passes_against_a_matching_build(tmp_path):
    out = tmp_path / "build.html"
    r1 = _run_builder("--dataset", str(DATASET_ALL), "--output", str(out), "--mode", "all")
    assert r1.returncode == 0, r1.stderr
    r2 = _run_builder("--dataset", str(DATASET_ALL), "--output", str(out), "--mode", "all", "--check")
    assert r2.returncode == 0, r2.stderr
    assert "OK" in r2.stdout


def test_check_mode_fails_without_prior_build(tmp_path):
    out = tmp_path / "never_built.html"
    r = _run_builder("--dataset", str(DATASET_ALL), "--output", str(out), "--mode", "all", "--check")
    assert r.returncode != 0


def test_builder_refuses_missing_dataset(tmp_path):
    out = tmp_path / "build.html"
    r = _run_builder("--dataset", str(tmp_path / "does_not_exist.json"), "--output", str(out), "--mode", "all")
    assert r.returncode != 0
    assert "not found" in r.stderr


def test_builder_refuses_duplicate_evidence_hash(tmp_path):
    dataset = tmp_path / "dup_dataset.json"
    dataset.write_text(json.dumps({"records": [
        {"regimen_id": "1", "evidence_hash": "a" * 64},
        {"regimen_id": "2", "evidence_hash": "a" * 64},
    ]}), encoding="utf-8")
    out = tmp_path / "build.html"
    r = _run_builder("--dataset", str(dataset), "--output", str(out), "--mode", "all")
    assert r.returncode != 0
    assert "duplicate evidence_hash" in r.stderr


def test_builder_refuses_preloaded_verdict(tmp_path):
    dataset = tmp_path / "preloaded_dataset.json"
    dataset.write_text(json.dumps({"records": [
        {"regimen_id": "1", "evidence_hash": "a" * 64, "canonical_verdict": "REMAINS_AMBIGUOUS"},
    ]}), encoding="utf-8")
    out = tmp_path / "build.html"
    r = _run_builder("--dataset", str(dataset), "--output", str(out), "--mode", "all")
    assert r.returncode != 0
    assert "forbidden preloaded" in r.stderr


def test_builder_refuses_missing_evidence_hash(tmp_path):
    dataset = tmp_path / "no_hash_dataset.json"
    dataset.write_text(json.dumps({"records": [{"regimen_id": "1"}]}), encoding="utf-8")
    out = tmp_path / "build.html"
    r = _run_builder("--dataset", str(dataset), "--output", str(out), "--mode", "all")
    assert r.returncode != 0
    assert "evidence_hash" in r.stderr


def test_real_dataset_has_no_duplicate_unit_ids():
    records = json.loads(DATASET_ALL.read_text(encoding="utf-8"))["records"]
    hashes = [r["evidence_hash"] for r in records]
    assert len(hashes) == len(set(hashes)), f"{DATASET_ALL} has duplicate evidence_hash values"


def test_optional_local_control_dataset_has_no_duplicate_unit_ids():
    if not DATASET_CONTROL.is_file():
        pytest.skip("owner_control_sample_data.json is intentionally not committed; only checked if present locally")
    records = json.loads(DATASET_CONTROL.read_text(encoding="utf-8"))["records"]
    hashes = [r["evidence_hash"] for r in records]
    assert len(hashes) == len(set(hashes)), f"{DATASET_CONTROL} has duplicate evidence_hash values"


# ── Static source safety (Part IX / Phase 13-14) ──────────────────────────

_NETWORK_MARKERS = ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource(", "navigator.sendBeacon")
_EXTERNAL_URL_RE = re.compile(r"https?://(?!localhost|127\.0\.0\.1)[a-zA-Z0-9.-]+")


def test_template_has_zero_network_code():
    source = TEMPLATE.read_text(encoding="utf-8")
    for marker in _NETWORK_MARKERS:
        assert marker not in source, f"template contains network API {marker!r}"


def test_template_has_no_external_urls():
    source = TEMPLATE.read_text(encoding="utf-8")
    matches = _EXTERNAL_URL_RE.findall(source)
    assert matches == [], f"template references external URL(s): {matches}"


def test_template_has_no_external_stylesheets_or_scripts():
    source = TEMPLATE.read_text(encoding="utf-8")
    assert "<link" not in source  # no external stylesheet/font link tags
    assert re.search(r'<script[^>]+src=', source) is None  # no external script src


def test_template_uses_textcontent_not_innerhtml_for_record_data():
    """innerHTML is only used to CLEAR a container (assigning "") or to build
    static/trusted markup — never to inject a record field directly. This
    is a source-level proxy: every `.innerHTML =` assignment in the file
    must either be an empty-string clear or not directly concatenate a `r.`
    (record) field."""
    source = TEMPLATE.read_text(encoding="utf-8")
    assignments = re.findall(r'\.innerHTML\s*=\s*([^;]+);', source)
    for rhs in assignments:
        assert rhs.strip() == '""', f"non-trivial innerHTML assignment found (must use textContent for record data): {rhs}"


def test_reviewer_id_is_a_fixed_string_literal_not_user_editable():
    source = TEMPLATE.read_text(encoding="utf-8")
    assert 'reviewer_id: "OWNER_LOCAL"' in source
    # no input/select/textarea element named or id'd for reviewer_id
    assert 'id="reviewerId' not in source
    assert 'name="reviewer_id"' not in source


def test_ai_provenance_fields_never_written_into_owner_event():
    source = TEMPLATE.read_text(encoding="utf-8")
    submit_fn = source[source.index("function submitVerdict"):source.index("document.getElementById(\"submitBtn\")")]
    for forbidden in ("review_origin", "owner_verified", "clinically_approved", "human_validated"):
        assert forbidden not in submit_fn


def test_stratum_field_not_rendered_before_submission():
    """Regression test for a real leak found during C5 verification: the
    `stratum` field is (for most records) identical to parser_semantic_type,
    so displaying it in the pre-submission badge would leak the parser's own
    classification. Only workload_category (a review-ordering label, not a
    parser output) may be shown before submission."""
    source = TEMPLATE.read_text(encoding="utf-8")
    render_fn = source[source.index("function render()"):source.index("function updateExportPreview()")]
    # Strip // line comments before checking — the function intentionally
    # documents *why* r.stratum is excluded in a comment, which must not
    # trip this check; only live (non-comment) code matters here.
    live_code = re.sub(r"//[^\n]*", "", render_fn)
    assert "r.stratum" not in live_code


def test_note_length_and_control_character_guards_present():
    source = TEMPLATE.read_text(encoding="utf-8")
    assert "MAX_NOTE_LENGTH" in source
    assert "CONTROL_CHAR_RE" in source


def test_verdict_select_has_no_preselected_value():
    source = TEMPLATE.read_text(encoding="utf-8")
    assert 'value="" selected disabled' in source  # placeholder option is selected+disabled
    # No option other than the placeholder carries the `selected` attribute
    option_tags = re.findall(r"<option[^>]*>", source)
    selected_options = [o for o in option_tags if "selected" in o]
    assert len(selected_options) == 1
    assert 'value=""' in selected_options[0]


# ── C4 taxonomy drift check (cross-checks JS source against Python) ───────

def test_ui_action_mapping_matches_c4_python_exactly():
    from dose_verification_sandbox.verdict_taxonomy import UI_ACTION_TO_CANONICAL as PY_MAPPING

    source = TEMPLATE.read_text(encoding="utf-8")
    match = re.search(r"const UI_ACTION_TO_CANONICAL = \{(.*?)\};", source, re.DOTALL)
    assert match, "could not locate UI_ACTION_TO_CANONICAL object literal in template"
    entries = re.findall(r'"([A-Z_]+)":\s*"([A-Z_]+)"', match.group(1))
    js_mapping = dict(entries)
    assert js_mapping == PY_MAPPING, "template's UI_ACTION_TO_CANONICAL has drifted from verdict_taxonomy.py"


# ── Real datasets never preload a verdict ─────────────────────────────────

def test_real_datasets_never_contain_a_preloaded_verdict():
    datasets = [DATASET_ALL] + ([DATASET_CONTROL] if DATASET_CONTROL.is_file() else [])
    for dataset in datasets:
        records = json.loads(dataset.read_text(encoding="utf-8"))["records"]
        for r in records:
            for forbidden in ("canonical_verdict", "ui_action", "human_fidelity_verdict", "owner_verdict"):
                assert forbidden not in r, f"{dataset} record {r.get('regimen_id')} pre-loads {forbidden!r}"


# ── Built output sanity (uses the real datasets, mirrors actual usage) ────

def test_built_all_mode_output_is_valid_html_and_has_expected_record_count(tmp_path):
    out = tmp_path / "all.html"
    r = _run_builder("--dataset", str(DATASET_ALL), "--output", str(out), "--mode", "all")
    assert r.returncode == 0, r.stderr
    html = out.read_text(encoding="utf-8")
    assert "__RECORDS_JSON__" not in html
    assert "__MODE__" not in html
    assert html.count('"regimen_id"') == 60


def test_built_control_mode_output_has_expected_record_count(tmp_path):
    dataset = _synthetic_control_dataset(tmp_path, n=3)
    out = tmp_path / "control.html"
    r = _run_builder("--dataset", str(dataset), "--output", str(out), "--mode", "control")
    assert r.returncode == 0, r.stderr
    html = out.read_text(encoding="utf-8")
    assert html.count('"regimen_id"') == 3


def test_storage_keys_are_mode_specific_and_distinct_from_legacy_keys():
    source = TEMPLATE.read_text(encoding="utf-8")
    assert "rc030_owner_review_c5_events_v1_${MODE}" in source
    assert "rc030_owner_review_c5_session_v1_${MODE}" in source
    # legacy dry-run / control-sample keys from the pre-C5 templates must not be reused
    assert "rc030_owner_fidelity_dryrun_v1" not in source
    assert "rc030_owner_control_sample_v1" not in source


# ── RC-030 C6.7 Part XI: range-review modes ────────────────────────────────

@pytest.mark.parametrize("mode", ["range-exact-review", "range-single-review", "range-unit-basis-review", "range-table-review", "range-engine-review", "range-blocked-evidence"])
def test_range_review_modes_are_accepted_by_the_builder(tmp_path, mode):
    dataset = _synthetic_control_dataset(tmp_path, n=2)
    out = tmp_path / "range.html"
    r = _run_builder("--dataset", str(dataset), "--output", str(out), "--mode", mode)
    assert r.returncode == 0, r.stderr
    html = out.read_text(encoding="utf-8")
    assert "__MODE__" not in html
    assert f'"{mode}"' in html
    assert html.count('"regimen_id"') == 2


def test_unknown_mode_is_rejected_by_the_builder(tmp_path):
    dataset = _synthetic_control_dataset(tmp_path, n=1)
    out = tmp_path / "bad.html"
    r = _run_builder("--dataset", str(dataset), "--output", str(out), "--mode", "range-exact-link-totally-safe")
    assert r.returncode != 0
    assert not out.exists()


@pytest.mark.parametrize("mode", ["range-exact-review", "range-single-review", "range-unit-basis-review", "range-table-review", "range-engine-review", "range-blocked-evidence"])
def test_range_review_modes_get_a_distinct_non_generic_banner(mode):
    source = TEMPLATE.read_text(encoding="utf-8")
    assert f'"{mode}":' in source
    # each range-review mode's banner text must be distinct from the plain "all" fallback
    banner_block_start = source.index("MODE_BANNER_TEXT")
    banner_block = source[banner_block_start:banner_block_start + 2000]
    assert mode in banner_block


@pytest.mark.parametrize("mode", ["range-exact-review", "range-single-review", "range-unit-basis-review", "range-table-review", "range-engine-review", "range-blocked-evidence"])
def test_range_review_modes_get_isolated_storage_keys(tmp_path, mode):
    # STORE_KEY/CURRENT_IDX_KEY are JS template literals (`..._${MODE}`),
    # evaluated in-browser at runtime from the MODE const -- the built HTML
    # source retains the literal `${MODE}` text (see
    # test_storage_keys_are_mode_specific_and_distinct_from_legacy_keys);
    # what a fresh build must get right is that MODE itself is correctly
    # substituted to this mode's own string, so each mode's runtime key is
    # distinct from every other mode's.
    dataset = _synthetic_control_dataset(tmp_path, n=1)
    out = tmp_path / f"{mode}.html"
    r = _run_builder("--dataset", str(dataset), "--output", str(out), "--mode", mode)
    assert r.returncode == 0, r.stderr
    html = out.read_text(encoding="utf-8")
    assert f'const MODE = "{mode}";' in html
    assert "rc030_owner_review_c5_events_v1_${MODE}" in html
    assert "rc030_owner_review_c5_session_v1_${MODE}" in html
