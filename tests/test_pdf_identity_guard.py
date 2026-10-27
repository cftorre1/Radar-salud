from src.radar_salud.regulatory_pipeline import pdf_identity_mismatch


def test_detects_another_acts_pdf():
    assert pdf_identity_mismatch("Resolución Exenta IF/N°11168",
                                 "https://www.superdesalud.gob.cl/app/uploads/2026/09/res-exenta-if-n11156-2026.pdf")
    assert pdf_identity_mismatch("Circular IF/N°501",
                                 "https://www.superdesalud.gob.cl/app/uploads/2026/x/res-exenta-if-n444-2026-1.pdf")


def test_accepts_matching_or_unnumbered_pdf():
    assert not pdf_identity_mismatch("Circular IF/N°537",
                                     "https://www.superdesalud.gob.cl/app/uploads/2026/10/circular-if-n-537-2026.pdf")
    assert not pdf_identity_mismatch("Resolución Exenta Nº132-2026",
                                     "https://www.superdesalud.gob.cl/app/uploads/2026/01/res-exenta-n132-2026.pdf")
    assert not pdf_identity_mismatch("Circular IF/N°537", "https://www.superdesalud.gob.cl/app/uploads/2026/10/documento.pdf")
    assert not pdf_identity_mismatch("Circular IF/N°537", None)


def test_cms_ids_and_gazette_editions_are_not_act_numbers():
    assert not pdf_identity_mismatch("Resolución Exenta IP/N° 1298",
                                     "https://superdesalud.gob.cl/normativa/668/articles-26530_recurso_1.pdf")
    assert not pdf_identity_mismatch("decreto Nº 64, de 2026", "https://www.diariooficial.interior.gob.cl/x/44531.pdf")
    assert pdf_identity_mismatch("Resolución Exenta IP/N°7976",
                                 "https://www.superdesalud.gob.cl/app/uploads/2026/10/res-exenta-ip-n-7676-centro-radiologico_0001.pdf")
