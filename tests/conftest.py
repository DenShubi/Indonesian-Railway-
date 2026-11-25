"""Register page fixtures, read from tests/fixtures rather than from the PDF.

Extracting "Train Timetables/GAPEKA Jadwal Kereta.pdf" with pdfplumber takes
about nine minutes, and the 2026 edition about eighteen, so the test suite
never opens either. Every fixture file holds
text copied verbatim out of a known page, and each records which page in a
comment, so a parser can be held to what the register actually prints.
"""
import json
import pathlib
import re

import pytest

FIXTURES = pathlib.Path(__file__).parent / 'fixtures'
PAGE = re.compile(r'^#\s*page (\d+)\b')


def load_lines(name: str) -> list[str]:
    """Verbatim lines of a fixture file, minus its comments and blank lines."""
    text = (FIXTURES / name).read_text(encoding='utf-8')
    return [line for line in text.split('\n')
            if line.strip() and not line.startswith('#')]


def load_pages(name: str) -> dict[int, list[str]]:
    """Verbatim lines of a fixture file, grouped by the page they came from.

    A fixture that holds whole pages marks each with a "# page N" comment; the
    lines after it are that page's, in print order, so a parser can be handed a
    page exactly as the register lays it out.
    """
    pages: dict[int, list[str]] = {}
    page: list[str] | None = None
    for line in (FIXTURES / name).read_text(encoding='utf-8').split('\n'):
        marker = PAGE.match(line)
        if marker:
            page = pages.setdefault(int(marker.group(1)), [])
        elif line.strip() and not line.startswith('#') and page is not None:
            page.append(line)
    return pages


def load_words(name: str) -> dict[int, list]:
    """Word coordinates of a fixture file, grouped by page.

    Each line is "x0 top text", as pdfplumber's extract_words() gives it, under
    the same "# page N" markers load_pages() uses. A word comes back as the
    (x0, top, text) triple the cached extraction carries, which is what
    tables.recover_vertical_codes() reads.
    """
    pages: dict[int, list] = {}
    page: list | None = None
    for line in (FIXTURES / name).read_text(encoding='utf-8').split('\n'):
        marker = PAGE.match(line)
        if marker:
            page = pages.setdefault(int(marker.group(1)), [])
        elif line.strip() and not line.startswith('#') and page is not None:
            x0, top, text = line.split(' ', 2)
            page.append((float(x0), float(top), text))
    return pages


@pytest.fixture(scope='session')
def register_rows() -> list[str]:
    return load_lines('register_rows.txt')


@pytest.fixture(scope='session')
def register_tables() -> dict[int, list[str]]:
    return load_pages('register_tables.txt')


@pytest.fixture(scope='session')
def register_words() -> dict[int, list]:
    return load_words('register_words.txt')


@pytest.fixture(scope='session')
def register_sections() -> dict[str, dict]:
    """Fixture pages shaped as parse_gapeka.py's data/gapeka/pages.json is.

    scan_sections() reads a {"<page>": {"text": ...}} map, so the fixture's
    per-page lines are joined back into the page text they were lifted from.
    """
    return {str(page): {'text': '\n'.join(lines)}
            for page, lines in load_pages('register_sections.txt').items()}


@pytest.fixture(scope='session')
def timetable_pages() -> dict[str, str]:
    """The 2026 timetable fixture, shaped as data/gapeka/2026/pages.json is.

    The 2026 cache maps each page straight to its text, {"<page>": "<text>"},
    with no {"text": ...} wrapper, so the fixture's lines are joined back into
    page text the same way.
    """
    return {str(page): '\n'.join(lines)
            for page, lines in load_pages('timetables_2026.txt').items()}


@pytest.fixture(scope='session')
def cached_2026_pages() -> dict[str, str]:
    """All 1,887 pages of GAPEKA 2026 as cache_gapeka_2026.py cached them.

    data/gapeka/2026/pages.json is committed; the 61 MB PDF it came from is
    not, and no test opens it. A checkout without the cache skips.
    """
    path = (pathlib.Path(__file__).resolve().parents[1]
            / 'data' / 'gapeka' / '2026' / 'pages.json')
    if not path.exists():
        pytest.skip('data/gapeka/2026/pages.json missing - run scripts/cache_gapeka_2026.py')
    return json.loads(path.read_text(encoding='utf-8'))


@pytest.fixture(scope='session')
def register_2026() -> dict[int, list[str]]:
    return load_pages('register_2026.txt')


@pytest.fixture(scope='session')
def cached_2026_words() -> dict[str, list]:
    """The twelve 2026 distance-table pages' word coordinates, as cached."""
    path = (pathlib.Path(__file__).resolve().parents[1]
            / 'data' / 'gapeka' / '2026' / 'words.json')
    if not path.exists():
        pytest.skip('data/gapeka/2026/words.json missing - run scripts/cache_gapeka_2026.py')
    return json.loads(path.read_text(encoding='utf-8'))


@pytest.fixture(scope='session')
def cached_pages() -> dict[str, dict]:
    """The whole 2025 register as parse_gapeka.py cached it, or a skip.

    data/gapeka/2025/pages.json is committed. The pipeline now reads it only
    for the one corridor 2026 does not print, but the 2025 parser tests and
    the evidence for carrying that corridor forward run off it, so a test may
    read it; the PDF it came from no test opens. Without it, these skip.
    """
    path = (pathlib.Path(__file__).resolve().parents[1]
            / 'data' / 'gapeka' / '2025' / 'pages.json')
    if not path.exists():
        pytest.skip('data/gapeka/2025/pages.json missing - run scripts/parse_gapeka.py --force')
    return json.loads(path.read_text(encoding='utf-8'))
