"""The register's train rows, parsed straight from the text pdfplumber yields.

Every row here is verbatim from tests/fixtures/register_rows.txt; the index
constants name which quirk each line was chosen for.
"""
import pytest

from scripts.gapeka.rows import (CATEGORIES, category_for_page, parse_train_row,
                                scan_categories, scan_sections)

PLAIN, YOGYAKARTA, VIA, FREIGHT, RAGGED = range(5)

HEADING = ('JENIS KA NAMA KERETA API NAMA IDENTITAS KERETA API LINTAS PELAYANAN '
           'PENYELENGGARA JARAK PERJALANAN')


def test_parses_a_plain_relasi(register_rows):
    row = parse_train_row(register_rows[PLAIN])
    assert row['no'] == '1'
    assert row['service'] == 'ARGO BROMO ANGGREK'      # the doubled cell is halved
    assert row['ident'] == '1'
    assert row['relasi'] == ('SBI', 'GMR')
    assert row['via'] == ()
    assert row['km'] == 720.109                        # "720,109" is 720.109 km
    assert row['dep'] == '09:10' and row['arr'] == '16:55'
    assert row['operator'] == 'PT. KAI'
    assert row['jenis'] == 'REGULER'
    assert row['duration'] == '07.45'


def test_parses_a_via_relasi(register_rows):
    row = parse_train_row(register_rows[VIA])             # 'GMR - SBI - JR'
    assert row['relasi'] == ('GMR', 'JR')
    assert row['via'] == ('SBI',)
    assert row['no'] == '32-33'                           # a paired through run
    assert row['ident'] == '2'                            # not the urut column, which is 1
    assert row['dep'] == '19:55' and row['arr'] == '09:00'  # crosses midnight as-is


def test_ragged_dash_spacing_still_splits(register_rows):
    row = parse_train_row(register_rows[RAGGED])          # 'CP - SLO -GBN - SBI'
    assert row['relasi'] == ('CP', 'SBI')
    assert row['via'] == ('SLO', 'GBN')
    assert row['jenis'] == 'FAKULTATIF'


def test_parses_a_freight_row(register_rows):
    row = parse_train_row(register_rows[FREIGHT])
    assert row['no'] == '2501-2504-2505-2508'
    assert row['service'] == 'KENLIMAS CARGO'
    assert row['relasi'] == ('KLM', 'KEN') and row['via'] == ('KPB',)
    assert row['km'] == 887.449
    # The register's only run over 24 h, and the only row where subtracting the
    # clock times (which gives 2 h 50) disagrees with the duration column.
    # HH.MM, so this is 26 h 50 min -- float('26.50') would be 26 h 30.
    assert row['duration'] == '26.50'
    assert row['dep'] == '23:25' and row['arr'] == '02:15'


def test_keeps_the_commuter_line_prefix_in_the_service_name(register_rows):
    assert parse_train_row(register_rows[YOGYAKARTA])['service'] == \
        'COMMUTER LINE YOGYAKARTA'


def test_halves_the_service_cell_only_when_it_doubles_exactly(register_rows):
    once = register_rows[PLAIN].replace('ANGGREK ARGO BROMO ANGGREK', 'ANGGREK')
    assert parse_train_row(once)['service'] == 'ARGO BROMO ANGGREK'
    mixed = register_rows[PLAIN].replace('ARGO BROMO ANGGREK ARGO BROMO ANGGREK',
                                         'ARGO BROMO ANGGREK ARGO WILIS')
    assert parse_train_row(mixed)['service'] == 'ARGO BROMO ANGGREK ARGO WILIS'


def test_rejects_a_heading_line():
    assert parse_train_row('NO.NOMOR KA NAMA KA RELASI') is None
    assert parse_train_row(HEADING) is None
    assert parse_train_row('') is None


def test_category_comes_from_the_page():
    assert category_for_page(4) == 'Argo'
    assert category_for_page(29) == 'Barang'
    assert set(CATEGORIES) == set(range(4, 32))      # every page that holds rows


def test_categories_come_from_the_banner_not_the_page(register_sections):
    cats = scan_categories(register_sections)
    assert cats['1'] == 'Argo'                   # page 4, above the Eksekutif banner
    assert cats['32-33'] == 'Eksekutif'          # page 4, below it
    assert cats['2501-2504-2505-2508'] == 'Barang'
    # ... which is exactly what the page map gets wrong.
    assert category_for_page(4) == 'Argo' != cats['32-33']


def test_a_section_meets_the_count_its_own_banner_claims(register_sections):
    argo = next(s for s in scan_sections(register_sections) if s.name == 'ARGO')
    assert argo.claimed == (28, 2)
    assert argo.tally == argo.claimed


def test_the_freight_sections_collapse_to_one_category(register_sections):
    freight = [s for s in scan_sections(register_sections)
               if s.name.startswith('BARANG')]
    assert len(freight) == 2                     # BHP and Petikemas, both page 29
    assert {s.category for s in freight} == {'Barang'}


def test_a_duty_roster_section_holds_no_train_rows(register_sections):
    duty = next(s for s in scan_sections(register_sections)
                if s.klasifikasi == 'DINAS')
    assert duty.name == 'DINAS RANGKAIAN DAOP 1 JAK'
    assert duty.trains == ()                     # its rows print no ident column
    assert duty.claimed == (73, 4)               # and so never meet the banner


def test_a_row_above_the_first_banner_is_refused(register_sections):
    orphan = {'0': {'text': register_sections['4']['text'].split('\n')[9]}}
    with pytest.raises(ValueError, match='above the first'):
        scan_sections(orphan)


def test_every_train_banner_tallies_over_the_whole_register(cached_pages):
    """The free end-to-end check: eighteen banners, 1,775 rows, no slack."""
    sections = scan_sections(cached_pages)
    trains = [s for s in sections if s.trains]
    assert len(trains) == 18
    assert [s.name for s in trains if s.tally != s.claimed] == []
    assert sum(len(s.trains) for s in trains) == 1775
    assert sum(sum(s.claimed) for s in trains) == 1775
    # The thirteen duty rosters claim 464 movements that are not trains.
    duty = [s for s in sections if not s.trains]
    assert all(s.klasifikasi == 'DINAS' for s in duty)
    assert sum(sum(s.claimed) for s in duty) == 464
