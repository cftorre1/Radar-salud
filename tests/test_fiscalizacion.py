from radar_salud.superintendencia_fiscalizacion import parse_listing, PAGES, _amount


def listing(rows):
    return '<table><tr><th>Fecha de publicación</th><th>Prestador</th><th>Título</th><th>Resumen</th><th>Materia</th></tr>' + ''.join(
        '<tr>' + ''.join(f'<td>{cell}</td>' for cell in row) + '</tr>' for row in rows) + '</table>'


def test_sis_2026_emission_is_independent_of_contradictory_source_publication():
    # Source columns verified 11 Oct: 7462 labels publication 2025 and emission 2026.
    html = listing([['23/09/2025', '', '<a href="/normativa/resolucion-exenta-ip-n-7462-emision-23-09-2026/">Resolución Exenta IP/N° 7462 - Emisión: 23/09/2026</a>',
        'Sancionase al pago de una multa por 400 Unidades Tributarias Mensuales a Clínica Sanatorio Alemán, por una infracción del artículo 141 bis. Fecha emisión: 23 de septiembre de 2026.', 'Cheque en garantía']])
    raw, = parse_listing(html, *PAGES[2])
    assert raw.event_date == '2026-09-23'
    assert raw.metadata['publication_date'] == '2025-09-23'
    assert raw.metadata['date_conflicts'] == ['publication_precedes_emission']
    assert raw.metadata['regulated_entity'] == 'Clínica Sanatorio Alemán'
    assert (raw.metadata['sanction_amount'], raw.metadata['sanction_unit']) == (400, 'UTM')


def test_sis_reposition_uses_current_act_and_entity_column_not_prior_act_date():
    html = listing([['20/08/2026', 'Centro Médico y Dental Red Salud Alameda',
        '<a href="/fiscalizacion/9774">Resolución Exenta IF/N°9774 - Emisión: 20/08/2026</a>',
        'ACOGER PARCIALMENTE el recurso de reposición interpuesto por el prestador CENTRO MÉDICO Y DENTAL RED SALUD ALAMEDA, en contra de la Resolución Exenta IF/N° 7409, de 22 de julio de 2025, rebajando la multa impuesta a 120 UF.', 'GES']])
    raw, = parse_listing(html, *PAGES[2])
    assert raw.event_date == '2026-08-20'
    assert raw.metadata['regulated_entity'] == 'Centro Médico y Dental Red Salud Alameda'
    assert raw.metadata['sanction_effect'] == 'amendment'
    assert raw.metadata['sanction_amount'] == 120


def test_sis_deduplicates_aliases_but_preserves_two_acts_for_same_actor():
    rows = [['15/09/2026', '', f'<a href="/normativa/{number}/">Resolución Exenta IP/N°{number} - Emisión: 08/09/2026</a>',
        'Sancionase al pago de una multa por 50 Unidades de Fomento a Clínica Los Carrera, por una infracción.', 'Cheque'] for number in ['6835', '6836']]
    rows.append([*rows[0][:2], rows[0][2].replace('/6835/', '/6835/?utm_source=x#top'), *rows[0][3:]])
    items = parse_listing(listing(rows), *PAGES[2])
    assert len(items) == 2
    assert all(raw.event_date == '2026-09-08' for raw in items)
    assert all(raw.metadata['publication_date'] == '2026-09-15' for raw in items)


def test_sis_invalid_table_date_and_navigation_cannot_prove_discovery():
    rows = [['31/02/2026', '', '<a href="/normativa/1">Resolución Exenta IP/N°1</a>', 'Multa', 'GES'],
            ['15/09/2026', '', '<a href="/">Inicio de fiscalización</a>', 'Menú', 'GES']]
    assert parse_listing(listing(rows), *PAGES[2]) == []
