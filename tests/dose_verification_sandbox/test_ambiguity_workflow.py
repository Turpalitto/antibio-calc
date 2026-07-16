from dose_verification_sandbox.ambiguity_workflow import (
    record_resolution, list_resolutions, new_resolution_id,
)
from dose_verification_sandbox.semantics_models import AmbiguityResolution


def test_record_and_list_resolution(tmp_path):
    path = tmp_path / "resolutions.json"
    r = AmbiguityResolution(
        resolution_id=new_resolution_id(), semantics_id="ds_x", regimen_id="6488",
        resolution_type="SOURCE_CONFIRMS_PER_DAY", exact_quote="6 мг/кг 1 раз в сутки",
        source_pdf="x.pdf", source_page="12", rationale="explicit once-daily phrasing",
        reviewer_identity="owner", created_at="2026-07-16T00:00:00Z",
    )
    record_resolution(r, path=path)
    items = list_resolutions(path=path, regimen_id="6488")
    assert len(items) == 1
    assert items[0]["resolution_type"] == "SOURCE_CONFIRMS_PER_DAY"


def test_invalid_resolution_type_rejected():
    import pytest
    with pytest.raises(ValueError):
        AmbiguityResolution(
            resolution_id="x", semantics_id="ds_x", regimen_id="1",
            resolution_type="CLINICALLY_APPROVED", exact_quote="", source_pdf="", source_page="",
            rationale="", reviewer_identity="owner", created_at="2026-07-16T00:00:00Z",
        )
