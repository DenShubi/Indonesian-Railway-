"""Register page fixtures, read from tests/fixtures rather than from the PDF.

Extracting "Train Timetables/GAPEKA Jadwal Kereta.pdf" with pdfplumber takes
about nine minutes, so the test suite never opens it. Every fixture file holds
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
def cached_pages() -> dict[str, dict]:
    """The whole register as parse_gapeka.py cached it, or a skip.

    data/gapeka/pages.json is the committed extraction the pipeline runs off,
    so a test may read it; the PDF it came from takes nine minutes and no test
    opens that. A checkout that has not run the CLI yet skips instead.
    """
    path = pathlib.Path(__file__).resolve().parents[1] / 'data' / 'gapeka' / 'pages.json'
    if not path.exists():
        pytest.skip('data/gapeka/pages.json missing - run scripts/parse_gapeka.py')
    return json.loads(path.read_text(encoding='utf-8'))
