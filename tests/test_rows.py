"""The register's train rows, parsed straight from the text pdfplumber yields.

Every 2025 row here is verbatim from tests/fixtures/register_rows.txt, and the
index constants name which quirk each line was chosen for. Every 2026 line is
verbatim from tests/fixtures/register_2026.txt, by page; the few Section
objects built by hand say so.
"""
from types import SimpleNamespace

import pytest

from scripts.gapeka.rows import (BANNER_ERRATA, CATEGORIES, BannerErratum, Section,
                                 banner_disagreements, category_for_page, match_runs,
                                 parse_train_row, scan_categories, scan_sections)

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


# GAPEKA 2026. Rows are verbatim from tests/fixtures/register_2026.txt, keyed
# by page; the whole-register tests read the committed 2026 cache.

def as_pages(register_2026, *pages):
    return {str(page): '\n'.join(register_2026[page]) for page in pages}


def test_a_2026_register_row_parses_with_seconds_omitted(register_2026):
    row = parse_train_row(register_2026[1828][3])
    assert row['no'] == '1' and row['dep'] == '08:15' and row['arr'] == '16:12'
    assert row['km'] == 720.109 and row['service'] == 'Anggrek'


def test_2025_rows_still_parse(register_rows):
    assert parse_train_row(register_rows[PLAIN])['dep'] == '09:10'
    assert len([line for line in register_rows if parse_train_row(line)]) == 5


def test_a_run_over_a_thousand_km_groups_its_rounded_km(register_2026):
    row = parse_train_row(register_2026[1829][0])     # "1.002,375 1.002"
    assert (row['no'], row['km']) == ('82-83', 1002.375)
    assert row['relasi'] == ('BD', 'KTG') and row['via'] == ('SGU',)


def test_an_identity_spelled_otherwise_still_gives_one_service_name(register_2026):
    assert parse_train_row(register_2026[1831][0])['service'] == 'Sri Tanjung'
    assert parse_train_row(register_2026[1835][0])['service'] == 'Bandara SMO'
    assert parse_train_row(register_2026[1837][1])['service'] == 'Commuter Line BST'


def test_a_duty_roster_row_is_not_a_train(register_2026):
    assert parse_train_row(register_2026[1854][2]) is None   # "Anggrek - GMR-JAKK"
    assert parse_train_row(register_2026[1854][1])['no'] == 'R951'


def test_a_banner_count_over_a_thousand_is_read_whole(register_2026):
    sections = scan_sections(as_pages(register_2026, 1837, 1838))
    soetta, jakarta = sections
    assert jakarta.claimed == (1055, 24) and jakarta.jumlah == 1079
    # The footer closing Soetta's section on the next page is Soetta's.
    assert (soetta.footer_rows, soetta.footer_km) == (70, 2907.47)


def test_a_stale_banner_erratum_is_refused():
    soetta = Section('COMMUTER LINE BANDARA SOETTA', 'x', 'PERKOTAAN', 1837, 70, 0,
                     tuple({'jenis': 'REGULER', 'km': 1.0} for _ in range(70)), 70)
    with pytest.raises(ValueError, match='not the'):
        banner_disagreements([soetta])                 # rows now meet the banner
    with pytest.raises(ValueError, match='found 0'):
        banner_disagreements([], BANNER_ERRATA)


def test_an_erratum_excuses_only_the_split_never_the_total():
    rows = tuple({'jenis': 'REGULER', 'km': 1.0} for _ in range(64)) + \
        tuple({'jenis': 'FAKULTATIF', 'km': 1.0} for _ in range(6))
    erratum = (BannerErratum(1, 'S', (70, 0), (64, 6)),)
    assert banner_disagreements([Section('S', 'x', 'k', 1, 70, 0, rows, 70, 70, 70.0)],
                                erratum) == []
    assert banner_disagreements([Section('S', 'x', 'k', 1, 70, 0, rows, 71, 70, 70.0)],
                                erratum) == ['S']      # JUMLAH says 71
    assert banner_disagreements([Section('S', 'x', 'k', 1, 70, 0, rows, 70, 70, 69.0)],
                                erratum) == ['S']      # footer km is a km short


def test_every_banner_tallies_against_its_section(cached_2026_pages):
    sections = scan_sections(cached_2026_pages)
    trains = [s for s in sections if s.trains]
    assert len(trains) == 19 and sum(len(s.trains) for s in trains) == 1815
    assert banner_disagreements(sections) == []
    # Without the erratum exactly one section is out, and only in its split.
    assert banner_disagreements(sections, ()) == ['COMMUTER LINE BANDARA SOETTA']
    # Every section's footer prints its km to the metre.
    assert all(abs(sum(t['km'] for t in s.trains) - s.footer_km) < 0.0005 for s in trains)
    # The fourteen duty rosters claim 538 movements that are not trains.
    duty = [s for s in sections if not s.trains]
    assert len(duty) == 14 and {s.klasifikasi for s in duty} == {'DINAS'}
    assert sum(sum(s.claimed) for s in duty) == 538


def test_the_soetta_banner_is_the_one_that_is_wrong(cached_2026_pages):
    # An F in the number marks a FAKULTATIF row everywhere in 2026, the six
    # Soetta rows included: so the rows are right, and the banner's 70/0 not.
    trains = [t for s in scan_sections(cached_2026_pages) for t in s.trains]
    assert all(('F' in t['no']) == (t['jenis'] == 'FAKULTATIF') for t in trains)
    assert sum(t['jenis'] == 'FAKULTATIF' for t in trains) == 101


def run(no):
    return SimpleNamespace(no=no)


def test_a_run_belongs_to_its_number_or_a_whole_part_of_a_paired_one():
    register = ['1', '32-33', '2501-2504-2505-2508']
    found = match_runs([run('1'), run('33'), run('2505'), run('3'), run('250')], register)
    assert found == {'1': '1', '33': '32-33', '2505': '2501-2504-2505-2508'}


def test_a_run_two_register_rows_claim_is_refused():
    with pytest.raises(ValueError, match='belongs to register rows'):
        match_runs([run('33')], ['32-33', '33-34'])


def test_every_register_row_but_the_four_empty_stock_moves_has_a_run(cached_2026_pages):
    from scripts.gapeka.timetables import parse_runs
    runs = parse_runs(cached_2026_pages)
    register = [t['no'] for s in scan_sections(cached_2026_pages) for t in s.trains]
    found = match_runs(runs, register)
    assert sorted(set(register) - set(found.values())) == ['R951', 'R952', 'R953', 'R954']
    # And every one of the 2,089 runs has its register row.
    assert len(found) == len(runs) == 2089
