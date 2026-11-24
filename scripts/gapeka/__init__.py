"""Pure parsers for GAPEKA: the 2025 register (Lampiran II of KP-DJKA 224/2024)
and the 2026 timetables (KP-DJKA 116/2026).

Nothing in this package does IO. The PDFs take nine and eighteen minutes to
extract, so reading them belongs in scripts/parse_gapeka.py and
scripts/cache_gapeka_2026.py, which cache the page text; these modules take
that text and turn it into trains, timetables, corridors and topology.
"""
