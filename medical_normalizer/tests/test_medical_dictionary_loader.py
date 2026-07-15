"""Tests for medical_dictionary/loader.py — JSON terminology loaders."""

from medical_dictionary import loader


class TestLoaderDrugSynonyms:
    def test_returns_dict(self):
        d = loader.load_drug_synonyms()
        assert isinstance(d, dict)

    def test_nonempty(self):
        d = loader.load_drug_synonyms()
        assert len(d) > 50

    def test_lowercase_keys(self):
        d = loader.load_drug_synonyms()
        for k in d:
            assert k == k.lower(), f"key not lowercase: {k!r}"

    def test_known_amoxicillin(self):
        d = loader.load_drug_synonyms()
        assert d["амоксициллин"] == "Амоксициллин"

    def test_known_brand(self):
        d = loader.load_drug_synonyms()
        assert d["сумамед"] == "Азитромицин"


class TestLoaderRoute:
    def test_returns_dict(self):
        d = loader.load_route_synonyms()
        assert isinstance(d, dict)

    def test_known_vv(self):
        d = loader.load_route_synonyms()
        assert d["в/в"] == "iv"

    def test_known_oral(self):
        d = loader.load_route_synonyms()
        assert d["внутрь"] == "oral"


class TestLoaderUnit:
    def test_returns_dict(self):
        d = loader.load_unit_normalization()
        assert isinstance(d, dict)

    def test_known_mg(self):
        d = loader.load_unit_normalization()
        assert d["мг"] == "mg"

    def test_known_g(self):
        d = loader.load_unit_normalization()
        assert d["г"] == "g"


class TestLoaderDrugAtc:
    def test_returns_dict(self):
        d = loader.load_drug_atc()
        assert isinstance(d, dict)

    def test_empty_until_review(self):
        d = loader.load_drug_atc()
        assert d == {}, "drug_atc must be empty until manual review"


class TestLoaderDrugGroups:
    def test_returns_dict(self):
        d = loader.load_drug_groups()
        assert isinstance(d, dict)

    def test_empty_until_review(self):
        d = loader.load_drug_groups()
        assert d == {}, "drug_groups must be empty until manual review"


class TestLoaderMetadata:
    def test_returns_dict(self):
        m = loader.load_metadata()
        assert isinstance(m, dict)

    def test_has_version(self):
        m = loader.load_metadata()
        assert "version" in m

    def test_has_files_inventory(self):
        m = loader.load_metadata()
        assert "files" in m
        assert "drug_synonyms.json" in m["files"]


class TestCaching:
    def test_cached_same_object(self):
        a = loader.load_drug_synonyms()
        b = loader.load_drug_synonyms()
        assert a is b

    def test_reload_clears_cache(self):
        a = loader.load_drug_synonyms()
        loader.reload_all()
        b = loader.load_drug_synonyms()
        assert a is not b
