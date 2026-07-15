"""Read-only invariants that must hold before, during, and after using the
sandbox: no clinical object gets approved, no data gets mutated, the Clinical
Engine stays disconnected from the sandbox's data path."""
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _readonly_connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)


def test_approved_object_count_is_zero():
    db = REPO_ROOT / "assembled_regimens.sqlite"
    conn = _readonly_connect(db)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM assembled_regimens WHERE status = 'APPROVED'")
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_review_tasks_have_no_consensus_or_qa_verdict():
    db = REPO_ROOT / "review_workbench_p56.sqlite"
    if not db.exists():
        import pytest
        pytest.skip("review_workbench_p56.sqlite not present in this checkout")
    conn = _readonly_connect(db)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM review_tasks WHERE "
            "(consensus_result IS NOT NULL AND consensus_result != '') OR "
            "(qa_verdict IS NOT NULL AND qa_verdict != '')"
        )
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_sandbox_module_never_imports_clinical_engine():
    import dose_verification_sandbox as pkg
    pkg_dir = Path(pkg.__file__).parent
    for py_file in pkg_dir.glob("*.py"):
        for line in py_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(("import clinical_engine", "from clinical_engine")):
                raise AssertionError(f"{py_file} imports clinical_engine — must stay disconnected: {stripped}")


def test_sandbox_never_opens_source_db_for_write():
    import dose_verification_sandbox.snapshot as snap
    text = Path(snap.__file__).read_text(encoding="utf-8")
    assert "mode=ro" in text
    assert "INSERT" not in text.upper()
    assert "UPDATE" not in text.upper()
    assert "DELETE" not in text.upper()


def test_issues_module_writes_only_to_local_sandbox_data():
    import dose_verification_sandbox.issues as issues
    assert "dose_verification_sandbox" in str(issues.ISSUES_PATH)
    assert issues.ISSUES_PATH.name == "issues.json"
