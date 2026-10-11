from pathlib import Path
import pytest
from radar_salud.sources import load_sources, source_index


def test_duplicate_registration_cannot_silently_replace_an_accepted_source():
    with pytest.raises(ValueError, match="Duplicate source registration: clinic"):
        source_index([{"slug": "clinic", "method": "reviewed"}, {"slug": "clinic", "method": "other"}])


def test_integrated_clinical_source_retains_occupational_document_contract():
    sources = load_sources(Path("config/sources.json"))
    index = source_index(sources)
    assert len(index) == len(sources)
    clinical = index["clinicas_achs_salud"]
    assert clinical["method"] == "article_scoped_occupational_newsroom"
    assert clinical["force_category"] is True
