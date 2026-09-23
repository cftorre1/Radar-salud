from src.radar_salud.models import RawItem
from src.radar_salud.quality import clean_technical_text, has_technical_garbage
from src.radar_salud.analysis import analyze_superintendencia


def item(title, text, updated=None):
    return RawItem(
        source_slug='superintendencia_salud', title=title,
        url='https://example.com', source_name='Superintendencia de Salud',
        source_type='official', raw_text=text,
        metadata={'description': text, 'updated_through': updated, 'extracted_numbers': []},
    )


def test_jsonld_is_cleaned():
    dirty='Boletín IP - Junio 2026 {"@context":"https://schema.org","@graph":[]}'
    assert clean_technical_text(dirty) == 'Boletín IP - Junio 2026'
    assert has_technical_garbage(dirty)


def test_financial_why_it_matters_is_specific():
    r=analyze_superintendencia(item('Estadísticas Financieras del Sistema ISAPRE a marzo 2026','Resultados financieros comparados IFRS', 'marzo 2026'))
    assert 'sostenibilidad financiera' in r.why_it_matters
    assert 'entre Isapres' in r.why_it_matters
    assert 'base oficial comparable' in r.why_it_matters


def test_ges_editorial_copy_is_specific():
    r=analyze_superintendencia(item('Estadística Trimestral de Casos GES (AUGE)','Casos GES y tasas de uso', 'marzo 2026'))
    assert 'utilización por patología' in r.why_it_matters
    assert 'casos y tasas de uso GES' in r.what_happened
