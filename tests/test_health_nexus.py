from radar_salud.editorial_gate import health_not_main_subject, publication_ready


def _press(title, **kw):
    return {"title": title, "source_type": "press_high_trust", "source_name": "Pulso / La Tercera",
            "source_url": "https://example.cl/" + str(abs(hash(title))), "event_date": "2026-10-24",
            "what_happened": "Según la nota, el Minsal informó una base SAMU no operativa.",
            "why_it_matters": "Presión sobre la continuidad de atención prehospitalaria.", **kw}


def test_direccion_examples_are_rejected_even_with_a_health_angle_in_the_summary():
    for title in ("93 albergados y 40 aislados: el último balance de Senapred por el evento meteorológico desarrollado en 10 regiones",
                  "Aramco y Enex se suman a Copec y rechazan integrar listado de infraestructura crítica de ciberseguridad",
                  "Contraloría detecta irregularidades en cuidado de menores de edad en residencia de Mejor Niñez de Antofagasta"):
        assert health_not_main_subject(_press(title))
        assert publication_ready(_press(title))[1] == "health_not_main_subject"


def test_health_led_press_and_official_sources_pass():
    for title in ("ISP aprueba primer genérico de Ozempic en Chile", "UC Christus sufre ciberataque",
                  "Listas de espera bajan 8%", "Healthatom abre oficina en España", "Colmed critica proyecto",
                  "Diputados ingresan proyecto para personas celíacas"):
        assert not health_not_main_subject(_press(title)), title
    official = _press("Suseso participa en sesión especial de la Comisión de Minería", source_type="official")
    assert not health_not_main_subject(official)


def test_story_group_members_are_left_to_their_synthesis():
    url = "https://www.latercera.com/pulso/noticia/presupuesto-2027-minuta-politica-del-gobierno-reporta-alza-del-gasto-distinta-de-la-informada/"
    assert not health_not_main_subject(_press("Presupuesto 2027: minuta política", source_url=url))


def test_common_words_do_not_count_as_health():
    from radar_salud.editorial_gate import title_has_health_nexus
    for title in ("Gestión municipal mejora", "Nueva medición de pobreza", "Empresas sanitarias suben tarifas",
                  "Senado aprueba suma urgencia", "Aluvión en Las Condes", "Licencia de conducir digital"):
        assert not title_has_health_nexus(title), title
    for title in ("Clínica Las Condes reporta pérdidas", "GES suma patologías", "Salcobrand abre locales"):
        assert title_has_health_nexus(title), title
