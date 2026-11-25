"""Extract GAPEKA 2026 once, into the text cache the pipeline reads.

The source is "KP DJKA 116 TAHUN 2026 GAPEKA JAWA.pdf", the 2026 Grafik
Perjalanan Kereta Api for Java under decree KP-DJKA 116/2026, valid from
1 December 2026. It is 1,887 pages and 61 MB, and it is NOT committed: git
keeps every version of a binary forever and 61 MB is past GitHub's warning
threshold. The copy the committed cache came from is the user's own download
of decree KP-DJKA 116/2026, kept outside the repository, so its path is an
argument. This script is the only thing that opens it, and it is
never run by the build; what it writes is committed instead:

  data/gapeka/2026/pages.json   {"<0-based page>": "<text>"} for all 1,887
                                pages, as pdfplumber 0.11.4's extract_text()
                                gives them -- about 3.5 MB
  data/gapeka/2026/words.json   {"<page>": [[x0, top, text], ...]} for the
                                twelve distance-table pages, 1875-1886, which
                                tables.recover_vertical_codes() reads

Words are kept for those twelve pages only because no other parser reads
coordinates, and coordinates for every page would multiply the file many times
over for nothing. They are rounded to a tenth of a point, as the 2025 cache
rounds them, which is finer than any gap tables.py measures.

A full text extraction takes about eighteen minutes (1,105 s measured, on the
machine that made the committed cache); the twelve pages of words take a few
seconds more. --pages-from reuses an extraction already made -- a JSON file of
the same {"<page>": "<text>"} shape -- instead of spending those eighteen
minutes again, and still reads the words from the PDF. It trusts that text:
beyond checking that it covers pages 0-1886, nothing compares it with the PDF
it is meant to have come from, not even a spot check of one page. The
committed pages.json was written that way, from an extract_text() dump made
with the same pdfplumber version.

Usage:  python scripts/cache_gapeka_2026.py <pdf> [--pages-from <pages.json>]
"""
import argparse
import json
import pathlib
import time

import pdfplumber

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'gapeka' / '2026'

PAGES = 1887
WORD_PAGES = range(1875, 1887)      # JARAK ANTAR STASIUN, 0-based


def extract_pages(pdf) -> dict[str, str]:
    started = time.time()
    pages = {}
    for at, page in enumerate(pdf.pages):
        pages[str(at)] = page.extract_text() or ''
        print(f'  page {at + 1}/{len(pdf.pages)} at {time.time() - started:.0f}s',
              end='\r', flush=True)
    print()
    return pages


def extract_words(pdf) -> dict[str, list]:
    return {str(at): [[round(w['x0'], 1), round(w['top'], 1), w['text']]
                      for w in pdf.pages[at].extract_words()]
            for at in WORD_PAGES}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('pdf', type=pathlib.Path)
    parser.add_argument('--pages-from', type=pathlib.Path,
                        help='reuse an existing {"<page>": "<text>"} extraction')
    args = parser.parse_args()

    with pdfplumber.open(args.pdf) as pdf:
        if len(pdf.pages) != PAGES:
            raise SystemExit(f'{args.pdf.name} has {len(pdf.pages)} pages, '
                             f'not the {PAGES} GAPEKA 2026 prints')
        if args.pages_from:
            pages = json.loads(args.pages_from.read_text(encoding='utf-8'))
            print(f'page text from {args.pages_from} ({len(pages)} pages)')
        else:
            print(f'extracting {args.pdf.name} (about eighteen minutes)...')
            pages = extract_pages(pdf)
        words = extract_words(pdf)

    if sorted(pages, key=int) != [str(at) for at in range(PAGES)]:
        raise SystemExit(f'page text must cover pages 0-{PAGES - 1} exactly')
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in (('pages.json', pages), ('words.json', words)):
        path = OUT / name
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')),
                        encoding='utf-8')
        print(f'  -> {path.relative_to(ROOT)} ({path.stat().st_size / 1e6:.2f} MB, '
              f'{len(data)} pages)')


if __name__ == '__main__':
    main()
