"""Register page fixtures, read from tests/fixtures rather than from the PDF.

Extracting "Train Timetables/GAPEKA Jadwal Kereta.pdf" with pdfplumber takes
about nine minutes, so the test suite never opens it. Every fixture file holds
text copied verbatim out of a known page, and each records which page in a
comment, so a parser can be held to what the register actually prints.
"""
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
