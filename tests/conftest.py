"""Register page fixtures, read from tests/fixtures rather than from the PDF.

Extracting "Train Timetables/GAPEKA Jadwal Kereta.pdf" with pdfplumber takes
about nine minutes, so the test suite never opens it. Every fixture file holds
text copied verbatim out of a known page, and each records which page in a
comment, so a parser can be held to what the register actually prints.
"""
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / 'fixtures'


def load_lines(name: str) -> list[str]:
    """Verbatim lines of a fixture file, minus its comments and blank lines."""
    text = (FIXTURES / name).read_text(encoding='utf-8')
    return [line for line in text.split('\n')
            if line.strip() and not line.startswith('#')]


@pytest.fixture(scope='session')
def register_rows() -> list[str]:
    return load_lines('register_rows.txt')
