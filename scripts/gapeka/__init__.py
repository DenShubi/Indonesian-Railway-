"""Pure parsers for the GAPEKA 2025 register, Lampiran II of KP-DJKA 224/2024.

Nothing in this package does IO. The PDF takes about nine minutes to extract, so
reading it belongs in scripts/parse_gapeka.py, which caches the page text; these
modules take that text and turn it into trains, corridors and topology.
"""
