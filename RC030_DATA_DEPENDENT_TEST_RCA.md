# RC-030 Data-Dependent Test — Root Cause Analysis

Reproduced 2026-07-16 in a bare fresh clone of commit `dd8b3ad` (`git clone --no-hardlinks C:/ANTIBIO`,
`uv sync --frozen --extra tests --extra clinical`, no database files restored).

## Failure 1 — `tests/dose_verification_sandbox/test_evidence_integrity.py::test_source_databases_unchanged_by_evidence_generation`

```
def test_source_databases_unchanged_by_evidence_generation():
    import hashlib
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    db = repo_root / "assembled_regimens.sqlite"
>   h = hashlib.sha256(db.read_bytes()).hexdigest()
                       ^^^^^^^^^^^^^^^
...
E   FileNotFoundError: [Errno 2] No such file or directory: '...\antibio_rca_clone\assembled_regimens.sqlite'
```

- **Database path resolution:** `Path(__file__).resolve().parents[2] / "assembled_regimens.sqlite"` — repo-relative, not hardcoded to `C:\ANTIBIO`, but the file itself is gitignored (`*.sqlite` in `.gitignore`) and therefore absent from any fresh clone.
- **Test type:** production database verification (asserts a literal hardcoded SHA-256 — `9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9` — belonging to the *real* corpus). It is not testing sandbox logic; it is testing that one specific real file hasn't moved. This must not run as an ordinary unit test.
- **Minimum data actually required:** none, if the goal is to prove "the evidence-generation code path never mutates its source database." That property is a code-behavior fact (read-only open, no `INSERT`/`UPDATE`/`DELETE`) and can be proven with any SQLite file, including a synthetic one built in `tmp_path`.

## Failure 2 — `tests/dose_verification_sandbox/test_invariants.py::test_approved_object_count_is_zero`

```
def test_approved_object_count_is_zero():
    db = REPO_ROOT / "assembled_regimens.sqlite"
>   conn = _readonly_connect(db)
           ^^^^^^^^^^^^^^^^^^^^^
...
E   sqlite3.OperationalError: unable to open database file
```

- **Database path resolution:** `Path(__file__).resolve().parents[2] / "assembled_regimens.sqlite"` — same pattern, same gitignored absence.
- **Test type:** production database verification — asserts `COUNT(*) FROM assembled_regimens WHERE status = 'APPROVED'` on the real corpus. Sibling test `test_review_tasks_have_no_consensus_or_qa_verdict` in the same file already has the correct pattern (`if not db.exists(): pytest.skip(...)`); this one is missing it — pre-existing gap from the P5.6 Commit A baseline (`630a5f7`), not introduced by RC-030 Commit B.
- **Minimum data actually required:** none for a unit-level guarantee. "No task is approved without a decision" is a schema/logic property of the review-workbench data model (`review_tasks.lifecycle_state`, `review_decisions` row count) and is fully expressible with a synthetic two-table SQLite fixture — a 9,153-row real corpus is not needed to prove the invariant holds.

## Summary

Both failures share the same root cause: a test that hardcodes a dependency on a specific gitignored production file, with no existence check, used to assert a general behavioral property that doesn't actually require real data. Neither is a regression from Commit B — both predate it or were introduced in Commit B without a skip guard, but neither *needed* real data in the first place.
