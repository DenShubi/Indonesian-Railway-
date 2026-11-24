# Every Train on Java Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Animate 1,764 trains across the whole Java rail network, sourced from the GAPEKA 2025 register already in the repository, without losing the published calling times the three existing commuter regions have.

**Architecture:** The register becomes the primary data source instead of a validator. Its train rows give every service; its `JARAK ANTAR STASIUN` tables give a national topology of 396 stations with official km posts. One island-wide OSM rail graph replaces the three deliberately-isolated regional graphs, and trip geometry is stored as a library of per-station-pair segments that trips reference by key, so shared trunk route is stored once. Keyframes exist only where a time is published, which is what keeps the bundle small and the departures board honest.

**Tech Stack:** Python 3.11 (pdfplumber, networkx, scipy, numpy, requests), pytest for the pipeline; TypeScript, Vite, MapLibre GL JS, three.js, vitest for the app.

**Spec:** [docs/superpowers/specs/2026-11-11-all-java-trains-design.md](../specs/2026-11-11-all-java-trains-design.md)

## Global Constraints

- No API keys, no accounts, no paid services. Every dependency stays free.
- `pdfplumber==0.11.4`, `pillow<12` — pinned; a newer pdfplumber demands Pillow >= 12.2 and breaks other installs.
- Overpass is a donated service. Cache under `data/osm/`, refetch only on `--force`, never hammer.
- Bundle target: **under 1.5 MB gzipped**. Raw may be 1.5–2.5 MB.
- Keyframes exist **only where a time is published**. For a register-sourced train that is origin, destination, and any via point the relasi names. Intermediate chain stations are geometry and km-check anchors only, and never enter `callsByStop`.
- Easing is **bounded by distance** (~2 km of acceleration and braking), not by fraction of leg.
- Verification: the three published regions keep **zero tolerance**. The national pass fails only above **2% of relasi disagreeing, or any single relasi off by more than 10%**.
- FAKULTATIF trains (75 of them) are **off by default**.
- Yogyakarta: published times win. The register's Yogyakarta rows are suppressed, keyed on **service name plus region, never train number**. Final count is **1,764**, and that is what the README claims.
- `dist/` and `public/data/bundle.json` stay generated, never committed.
- **Commit messages follow the repository's own style**, not this plan's `feat:`
  examples: sentence-case imperative subject, no type prefix, with a body saying
  why. See `git log` — "Lift the body red to a carriage red". The subjects in
  this plan's commit steps are placeholders; write one in the house style.
- The register PDF takes ~9 minutes to extract with pdfplumber. No test may open it; page text is cached and tests use fixtures.

## Review Focus

Five failure modes the spec implies but which no task's happy path exercises. Each has its test assigned to the task that owns the code.

1. **A run crossing midnight, and the one that crosses two.** The register prints plain `HH:MM:SS`, so a train departing 22:35 and arriving 01:20 has arrival < departure. Untreated it runs backwards or never appears; the existing simulation expects times past 86400 for these. The obvious "arrival before departure, add a day" rule is **not sufficient**: Kenlimas Cargo `2501-2504-2505-2508` runs 23:25 to 02:15 over 26 h 50 min, so that rule puts it 24 h short. The `duration` column is authoritative, and it is `HH.MM` — `float('26.50')` is 26 h 30, not 26 h 50. → test in Task 7.
2. **A relasi that passes the same station twice.** The circular Dhoho and Penataran runs already call at Wonokromo and Gubeng twice, and `make_bundle.py` has a first-pass projection rule for it. A national router that ignores this collapses the monotonic km cursor to the end of the line. → test in Task 3.
3. **A junction station in two corridors with different km origins.** SMT, BBG, CKP and CU each appear in several corridor tables at different cumulative km. Treating those as different nodes splits the graph; mixing the km rebases distances wrongly. → test in Task 2.
4. **Two services sharing one relasi.** A FAKULTATIF path, a freight working and a passenger train can run the same origin-destination pair. Segment keys must be category-blind while route assignment stays per-service, or colours merge. → test in Task 6.
5. **An Overpass tile with zero elements.** `overpass()` currently treats a zero-element response as failure and retries every endpoint. Tiling the island guarantees tiles that are legitimately empty sea, which would loop through all endpoints and abort the fetch. → test in Task 4.

---

## File Structure

**New:**
- `scripts/gapeka/__init__.py` — package marker.
- `scripts/gapeka/rows.py` — pure parsers for the register's train rows. No IO.
- `scripts/gapeka/tables.py` — pure parsers for the `JARAK ANTAR STASIUN` corridor matrices. No IO.
- `scripts/gapeka/topology.py` — the national station graph and relasi routing. No IO.
- `scripts/parse_gapeka.py` — CLI: PDF → `data/gapeka/pages.json`, `trains.json`, `network.json`.
- `scripts/build_java_network.py` — CLI: `network.json` + `trains.json` → `data/gapeka/relasi.json`.
- `tests/conftest.py`, `tests/fixtures/*.txt` — register page fixtures, lifted verbatim from the PDF.
- `tests/test_rows.py`, `tests/test_tables.py`, `tests/test_topology.py`, `tests/test_shapes.py`, `tests/test_bundle.py`, `tests/test_stations.py`, `tests/test_fetch_osm.py`, `tests/test_validate.py`
- `src/sim/__tests__/trains.test.ts`, `src/data/__tests__/bundle.test.ts`, `src/map/__tests__/trackLayer.test.ts`, `src/map/__tests__/stationLayer.test.ts`
- `pytest.ini`, `vitest.config.ts`

**Modified:**
- `scripts/fetch_osm.py` — island pseudo-region, tiling, empty-tile tolerance.
- `scripts/build_stations.py` — 396 register codes, km-post placement fallback.
- `scripts/build_shapes.py` — one island graph, A\*, segment library, length-scaled RDP.
- `scripts/build_gtfs.py` — national routes and trips, endpoint-only stop_times.
- `scripts/make_bundle.py` — segment-referencing shapes, trip metadata, Yogyakarta suppression.
- `scripts/validate.py` — island bbox, national route-id scheme.
- `scripts/validate_gapeka.py` — national pass with a failure budget.
- `scripts/check-geometry.mjs` — walk the segment library.
- `src/data/bundle.ts` — segment assembly at load, new trip fields.
- `src/sim/trains.ts` — bounded easing.
- `src/map/trackLayer.ts` — segment features, category colour priority.
- `src/map/stationLayer.ts` — station rank, island-view filtering.
- `src/ui/linePanel.ts` — category groups, FAKULTATIF chip.
- `src/ui/trainPanel.ts` — provenance line, category badge.
- `src/main.ts` — wiring for the above.
- `package.json`, `requirements.txt`, `README.md`, `data/regions.json`

---

### Task 1: Test harness and register train rows

**Files:**
- Create: `pytest.ini`, `scripts/gapeka/__init__.py`, `scripts/gapeka/rows.py`, `tests/fixtures/register_rows.txt`
- Test: `tests/test_rows.py`
- Modify: `requirements.txt` (add `pytest>=8.0`), `package.json` (add `"test:py": "pytest -q"`)

**Interfaces:**
- Produces:
  - `parse_train_row(line: str) -> dict | None` — keys `no, jenis, service, ident, relasi, via, operator, km, dep, arr, duration`. `relasi` is `(origin, destination)`; `via` is a tuple of intermediate codes, empty for a plain `A-B`. `km` is a float. `None` when the line is not a train row.
  - `CATEGORIES: dict[int, str]` — page index → register category name.
  - `category_for_page(page: int) -> str`

> **Superseded after Task 1 shipped.** A page→category map cannot be exact:
> pages 4, 11, 13 and 29 each hold the end of one section and the start of
> another, so Eksekutif and Ekonomi Lokal (Feeder) never own a page and ~40
> trains would take a sibling's category. The register instead prints a banner
> at each section start — `KELAS KERETA API : ARGO REGULER : 28 FAKULTATIF : 2`
> — which gives the category *and* its expected counts. Task 4 adds
> `scan_categories` on that banner and stops using `category_for_page`; leave
> Task 1's function and its test in place, unused, rather than reopening a
> committed task.

- [ ] **Step 1: Write the failing tests**

`tests/fixtures/register_rows.txt` holds these lines verbatim from the PDF (pages 4, 13, 29):

```
1 1 REGULER ARGO BROMO ANGGREK ARGO BROMO ANGGREK 1 SBI-GMR PT. KAI 720,109 720 09:10:00 16:55:00 07.45
8 708 REGULER COMMUTER LINE YOGYAKARTA COMMUTER LINE YOGYAKARTA 8 YK-PL PT. KCI 65,458 65 18:08:00 19:28:00 01.20
```

```python
def test_parses_a_plain_relasi():
    row = parse_train_row(LINES[0])
    assert row['no'] == '1'
    assert row['service'] == 'ARGO BROMO ANGGREK'      # the doubled cell is halved
    assert row['relasi'] == ('SBI', 'GMR')
    assert row['via'] == ()
    assert row['km'] == 720.109                         # "720,109" is 720.109 km
    assert row['dep'] == '09:10' and row['arr'] == '16:55'
    assert row['operator'] == 'PT. KAI'
    assert row['jenis'] == 'REGULER'

def test_parses_a_via_relasi():
    row = parse_train_row('... GMR - SBI - JR ...')     # build from the fixture pattern
    assert row['relasi'] == ('GMR', 'JR')
    assert row['via'] == ('SBI',)

def test_strips_commuter_line_prefix_but_keeps_the_name():
    assert parse_train_row(LINES[1])['service'] == 'COMMUTER LINE YOGYAKARTA'

def test_rejects_a_heading_line():
    assert parse_train_row('NO.NOMOR KA NAMA KA RELASI') is None

def test_category_comes_from_the_page():
    assert category_for_page(4) == 'Argo'
    assert category_for_page(29) == 'Barang'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_rows.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'scripts.gapeka.rows'`

- [ ] **Step 3: Implement `rows.py`**

Start from the row regex already proven in `scripts/validate_gapeka.py:34-37`; it matches all 1,775 rows unchanged. Two additions: split `relasi` on `-` with each part stripped, taking first and last as origin/destination and the middle as `via`; and halve the doubled service-name cell, keeping the halved value only when the full text starts with it.

`CATEGORIES` maps page index to the register's own section order: 4 Argo, 5 Eksekutif, 5–6 Eksekutif Campuran, 7 Ekonomi Jarak Jauh, 8–9 Ekonomi Lokal, 10 Bandara YIA, 11 Bandara SMO / Ekonomi Lokal Feeder, 12–13 Commuter Line Daop 6 YK, 13 Commuter Line Bandara Soetta, 14–28 Commuter Line Daop 1 Jak, 29–31 Barang. Confirm each boundary against the table of contents on page 1 while implementing.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_rows.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pytest.ini requirements.txt package.json scripts/gapeka tests
git commit -m "feat: parse GAPEKA register train rows"
```

---

### Task 2: Corridor distance tables

**Files:**
- Create: `scripts/gapeka/tables.py`, `tests/fixtures/register_tables.txt`
- Test: `tests/test_tables.py`

**Interfaces:**
- Produces:
  - `parse_corridor_block(lines: list[str]) -> list[Corridor]` where `Corridor` is a dataclass `{name: str, stations: list[tuple[str, float]]}`, each tuple `(code, cumulative_km_from_head)`.
  - `parse_inline_pairs(line: str) -> list[tuple[str, str, float]]` — the short branches printed as `CTA-NMO 13,267`.
  - `split_side_by_side(rows: list[Row]) -> list[list[Row]]` — splits where the row index resets.

- [ ] **Step 1: Write the failing tests**

Fixture: pages 52, 55 and 62 verbatim (52 for a clean header and inline pairs, 55 for the interleaved header, 62 for side-by-side tables).

```python
def test_station_order_comes_from_row_labels_not_the_header():
    # Page 55's header arrives interleaved: "O/D C 1KP C 2BR PW 3K ..."
    corridor = parse_corridor_block(PAGE_55)[0]
    assert [c for c, _ in corridor.stations][:3] == ['CKP', 'CBR', 'PWK']
    assert len(corridor.stations) == 42

def test_cumulative_km_comes_from_the_first_value_in_each_row():
    corridor = parse_corridor_block(PAGE_55)[0]
    assert corridor.stations[0] == ('CKP', 0.0)
    assert corridor.stations[1][1] == 7.636
    assert corridor.stations[-1][1] == 245.562

def test_row_one_first_value_cross_checks_the_head():
    # row 1's first value is d(1,2) and must equal station 2's cumulative km
    for corridor in parse_corridor_block(PAGE_55):
        assert corridor.stations[1][1] > 0

def test_cumulative_km_is_strictly_increasing():
    for corridor in parse_corridor_block(PAGE_52):
        kms = [km for _, km in corridor.stations]
        assert kms == sorted(kms) and len(set(kms)) == len(kms)

def test_side_by_side_tables_split_on_index_reset():
    corridors = parse_corridor_block(PAGE_62)
    assert len(corridors) == 2
    assert [c for c, _ in corridors[1].stations] == ['TRK', 'TLN', 'SDA']

def test_inline_pairs_are_picked_up():
    assert ('KEN', 'CGD', 6.439) in parse_inline_pairs('DU-TNG BPR - BST 12,300 KEN-CGD 6,439')

# Review Focus 3
def test_a_junction_station_keeps_each_corridors_own_km():
    smt_kms = [km for c in ALL_CORRIDORS for code, km in c.stations if code == 'SMT']
    assert len(smt_kms) > 1
    assert len(set(smt_kms)) > 1     # different origins, deliberately not merged here
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_tables.py -v`
Expected: FAIL, module not found

- [ ] **Step 3: Implement `tables.py`**

A matrix row is `CODE index num num ...`. Recover the ordered station list from the row labels, because on narrow pages the header is interleaved and unusable — the header is the only line `extract_text()` truncates, and the matrix rows are complete. Cumulative km is the first numeric token of each row — row *i*'s distance to station 1 — because it is the one anchor every row carries whatever the header did. Station 1's own cumulative km is 0, and row 1's first value is d(1,2), used as a cross-check. Numbers are Indonesian-formatted: `.` groups thousands, `,` is the decimal point. A comma-less token must be **rejected**, or vertical-text wreckage (`LJ BR GL 98 76 25 ,, …` on pages 55 and 58) reads as a station. A block ends at a line that is not a matrix row; split a block into corridors on the matrix's own symmetry, comparing at the precision the register printed.

Corridor names come from the uppercase title lines above each block.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_tables.py -v`
Expected: PASS, 7 tests

- [ ] **Step 5: Commit**

```bash
git add scripts/gapeka/tables.py tests/test_tables.py tests/fixtures/register_tables.txt
git commit -m "feat: parse GAPEKA inter-station distance tables"
```

---

### Task 3: National topology and relasi routing

**Files:**
- Create: `scripts/gapeka/topology.py`
- Test: `tests/test_topology.py`

**Interfaces:**
- Consumes: `Corridor` from Task 2, `parse_train_row` output from Task 1.
- Produces:
  - `recover_vertical_codes(words: list, page: int) -> dict[int, str]` in `scripts/gapeka/tables.py` — **step 1 of this task, before any graph is built.** Four chain stations are unrecoverable from page text alone, because pages 55 and 58 print a stretch of one matrix as vertical text that `extract_text()` returns as wreckage (`LJ BR GL 98 76 25 ,, …`). The codes are `CBB` and `LP` (Padalarang–Sukabumi) and `JRL` and `LBG` (Banjar–Kroya); their km are already parsed, since row 1 of each matrix prints them. The codes are legible in the garbled header and de-interleavable from the per-word `x0` coordinates, which the cache's `words` array carries and Task 2's text-only interface does not. Takes `words` as an argument, so it stays pure and the no-IO rule holds. Repairing the chains here is what dissolves the shortcut-edge hazard below; do not build the graph around a hole you can close. If a code genuinely cannot be recovered, say so in one line and fall back to the defensive rule.
  - `build_topology(corridors: list[Corridor], pairs: list[tuple[str, str, float]]) -> nx.Graph` — nodes are station codes, edges carry `weight` in km from consecutive corridor entries. A code in several corridors is **one node**; each corridor contributes only its own consecutive deltas, never its absolute km.
  - `route_relasi(graph, origin, destination, via=()) -> list[tuple[str, float]]` — the station chain with cumulative km from the origin, forced through each via point in order. **A relasi is keyed on `(origin, destination, via)`, never on the pair alone**: the register has 316 distinct triples but only 304 distinct pairs, so twelve differ by via point only, and 32 are circular with `origin == destination` (Dhoho, Penataran, the circular Cikarang workings, Joglosemarkerto). Keying on the pair would merge routes that are not the same route and send a circular run straight to a zero-length path.
  - `check_length(chain, register_km) -> float` — signed fractional disagreement.

- [ ] **Step 1: Write the failing tests**

Build a synthetic topology in the test: two corridors sharing a junction, plus a loop.

```python
def test_consecutive_deltas_not_absolute_km_become_edge_weights():
    g = build_topology([Corridor('X', [('A', 0.0), ('B', 10.0), ('C', 25.0)])], [])
    assert g['A']['B']['weight'] == 10.0
    assert g['B']['C']['weight'] == 15.0

# Review Focus 3
def test_a_junction_is_one_node_across_corridors():
    g = build_topology([
        Corridor('X', [('A', 0.0), ('J', 10.0)]),
        Corridor('Y', [('J', 0.0), ('B', 5.0)]),     # J at km 0 here, km 10 there
    ], [])
    assert route_relasi(g, 'A', 'B') == [('A', 0.0), ('J', 10.0), ('B', 15.0)]

def test_via_forces_the_longer_path():
    # A-B direct is 10 km; A-V-B is 30 km
    chain = route_relasi(G_TWO_WAYS, 'A', 'B', via=('V',))
    assert [c for c, _ in chain] == ['A', 'V', 'B']
    assert chain[-1][1] == 30.0

# Review Focus 2
def test_a_circular_run_may_repeat_a_station_with_increasing_km():
    chain = route_relasi(G_LOOP, 'A', 'A', via=('C',))
    codes = [c for c, _ in chain]
    assert codes[0] == codes[-1] == 'A'
    assert codes.count('C') == 1
    kms = [km for _, km in chain]
    assert kms == sorted(kms)        # monotonic even though a code repeats

def test_check_length_reports_the_fractional_gap():
    assert check_length([('A', 0.0), ('B', 100.0)], 110.0) == pytest.approx(-100 / 110 + 1, abs=0.01)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_topology.py -v`
Expected: FAIL, module not found

- [ ] **Step 3: Implement `topology.py`**

`route_relasi` concatenates `nx.shortest_path` over consecutive waypoints `[origin, *via, destination]`, accumulating km as it goes rather than reading any corridor's absolute values. A repeated code is allowed in the output chain — the cumulative km is what must stay monotonic, and it does by construction.

Two hazards the Task 2 review found in the chains this graph is built from:

- **A chain with a hole yields a shortcut edge that bypasses real stations.** `BJR - MA - KYA` lost four rows to vertical text, so it runs `KWG@52.694, KH@77.386, KYA@91.807` — a direct KH–KYA edge of 14.421 km. The same stretch exists on `CP - MA - KYA` as KH–MA + MA–SKP + SKP–KYA = 14.664 km, so every shortest path takes the shortcut and skips Maos, a genuine calling point. The km for the lost rows are **already parsed** (row 1 of the holed corridor prints them: JRL 65.502, LBG 72.190, MA 79.109, SKP 85.527); only the four codes are missing, which Task 4's `recover_vertical_codes` supplies. Recover them before building the graph, and this dissolves. If it cannot be recovered, drop a corridor edge when a path over the same endpoints with more stations and comparable length already exists.
- **Three station pairs get conflicting weights from different corridors**, of 408 (the figure was 2 of 399 before the chain repair added KH–MA and before the six inline branches were counted). `ATA–BBG` is 6.856 km on one corridor and 5.976 on another (BBG is printed at 163.822 and 162.942); `CN–CNP` is 1.600 versus 1.606; `KH–MA` is 1.723 against 1.966 on two other corridors. `nx.Graph` silently keeps whichever is written last. Detect a re-write of an existing edge weight and either keep the minimum deliberately or report it — do not let iteration order decide.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_topology.py -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add scripts/gapeka/topology.py tests/test_topology.py
git commit -m "feat: national rail topology and relasi routing"
```

---

### Task 4: The register CLI and the island OSM fetch

**Files:**
- Create: `scripts/parse_gapeka.py`, `scripts/build_java_network.py`
- Modify: `scripts/fetch_osm.py`, `data/regions.json`
- Test: `tests/test_fetch_osm.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `data/gapeka/pages.json` — cached page text, so nothing downstream reopens the PDF.
  - `data/gapeka/trains.json`, `data/gapeka/network.json`, `data/gapeka/relasi.json`.
  - `tiles(bbox, step=1.0) -> list[tuple[float, float, float, float]]` in `fetch_osm.py`.
  - `overpass(query, bbox, allow_empty=False)` — the existing signature plus the flag.
  - `scan_categories(pages: dict[str, dict]) -> dict[str, str]` in
    `scripts/gapeka/rows.py` — train number → category, assigned by walking each
    page's lines in order and switching category at every
    `KELAS KERETA API : <NAME> REGULER : <n> FAKULTATIF : <m>` banner. This
    replaces `category_for_page`; see the note under Task 1.

- [ ] **Step 1: Write the failing tests**

```python
def test_tiles_cover_the_bbox_with_no_gaps():
    covered = tiles((-9.0, 105.0, -5.8, 114.7), step=1.0)
    assert len(covered) == 4 * 10
    assert min(s for s, _, _, _ in covered) <= -9.0
    assert max(n for _, _, n, _ in covered) >= -5.8

# Review Focus 5
def test_an_empty_tile_is_accepted_not_retried(monkeypatch):
    calls = []
    monkeypatch.setattr('scripts.fetch_osm.requests.post', recording_post(calls, elements=[]))
    assert overpass(RAIL_QUERY, SEA_TILE, allow_empty=True) == {'elements': []}
    assert len(calls) == 1        # one endpoint, no retry storm

def test_an_empty_response_still_fails_when_emptiness_is_not_expected(monkeypatch):
    with pytest.raises(SystemExit):
        overpass(RAIL_QUERY, LAND_BBOX, allow_empty=False)

def test_ways_repeated_across_tiles_are_deduplicated_by_id():
    merged = merge_rail([{'elements': [WAY_7]}, {'elements': [WAY_7, WAY_8]}])
    assert sorted(f['properties']['id'] for f in merged['features']) == [7, 8]

def test_categories_come_from_the_banner_not_the_page():
    cats = scan_categories(PAGES)
    assert cats['1'] == 'Argo'                  # page 4, above the Eksekutif banner
    assert cats['7000'] == 'Eksekutif'          # page 4, below it — a page map loses this
    assert cats['2501'] == 'Barang'

def test_every_banner_count_is_met():
    # the banner states REGULER and FAKULTATIF counts per section; they must tally
    for category, (reguler, fakultatif) in BANNER_COUNTS.items():
        trains = [t for t in TRAINS if t['category'] == category]
        assert sum(1 for t in trains if t['jenis'] == 'REGULER') == reguler
        assert sum(1 for t in trains if t['jenis'] == 'FAKULTATIF') == fakultatif
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_fetch_osm.py -v`
Expected: FAIL on the missing `tiles` and `allow_empty`

- [ ] **Step 3: Implement the fetch changes, then the two CLIs**

`data/regions.json` gains a `java` entry with `bbox: [-9.0, 105.0, -5.8, 114.7]`, `"pdf": null` and `"gapekaNumbering": true`, marked so `parse_timetable.py` skips it — it has no per-station PDF. A bbox wider than 2° is fetched tile by tile with `allow_empty=True` and merged on OSM way id.

`parse_gapeka.py` extracts page text once into `data/gapeka/pages.json` (reusing it on later runs unless `--force`), then writes `trains.json` and `network.json`. Print the counts: expect 1,775 trains and 396 station codes.

`build_java_network.py` builds the topology, routes all 316 relasi, and writes `relasi.json`. For each relasi it reports the worst `check_length` against the register km of trains using it, sorted worst first.

**Routing is by km match, not by shortest path.** Task 3's sanity run measured plain shortest-path routing at 256 of 316 relasi within tolerance, 30 of them over 10% — a clear budget failure. Two changes fix it:

- **Add the one genuinely missing edge.** Page 54 prints the route `KPB-DU-THB-MRI` over a matrix that stops at THB, so the register's tables carry no THB–MRI distance and shortest THB→MRI detours via Kampung Bandan and Gambir: 20.082 km where the register's own train rows print 6.026. Add that edge from the train-row data. On its own it drops the worst case from 233% to 25.8%.
- **Select the path by length.** Enumerate simple paths in increasing length with `nx.shortest_simple_paths` and take the one whose total best matches the km the register prints for trains on that relasi, stopping as soon as one is within tolerance. Cap the enumeration (a few hundred paths) and report any relasi that exhausts the cap rather than silently taking the shortest.

  `select_path(graph, origin, destination, via, register_km, cap=400) -> tuple[list, float]`.

  This is what recovers the routes with no via point to disambiguate them: `SGU - PSE` matches at 824.9 km against a printed ~825, but only as the **58th** simple path. Verified before this task was written.

The remaining offset groups Task 3 identified — Kampung Bandan reached the long way round (19 relasi), Solo/Madiun/Jombang to Jakarta by the southern line (8), Malang (5) — are all the same shape of problem and should dissolve under length selection. Report the count still outside tolerance after both changes; if it is not near zero, stop and say so rather than widening the budget.

- [ ] **Step 4: Run the tests and both CLIs**

Run: `pytest tests/test_fetch_osm.py -v`
Expected: PASS

Run: `python scripts/parse_gapeka.py && python scripts/build_java_network.py`
Expected: 1,775 trains, 396 codes, 316 relasi routed; the length report printed. Record any relasi over 10% in the commit message — Task 9 sets the budget that decides whether they fail the build.

Run: `python scripts/fetch_osm.py java`
Expected: one `data/osm/java/rail.geojson` and a `stations.csv` with its `railway:ref` coverage printed. Measured: the rail cache is 3.0 MB and 8,783 ways, not the 15–25 MB first guessed, and it is committed like the regional caches.

- [ ] **Step 5: Commit**

```bash
git add scripts/parse_gapeka.py scripts/build_java_network.py scripts/fetch_osm.py data/regions.json data/gapeka tests/test_fetch_osm.py
git commit -m "feat: register CLI and island-wide OSM fetch"
```

---

### Task 5: Station coordinates for the register's 396 codes

**Files:**
- Modify: `scripts/build_stations.py`
- Test: `tests/test_stations.py`

**Interfaces:**
- Consumes: `data/gapeka/network.json`, `data/osm/java/stations.csv`.
- Produces:
  - `place_by_km(polyline: list[tuple[float, float]], cumulative_km: list[float], km: float) -> tuple[float, float]`
  - `data/stations.csv` gains a `source` value of `km-post` alongside the existing `osm` and `previous`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_code_matched_on_railway_ref_wins():
    rows = build(codes=['YK'], osm=[{'ref': 'YK', 'lat': -7.789, 'lon': 110.363}])
    assert rows['YK']['source'] == 'osm'

def test_an_unmatched_code_is_placed_at_its_km_along_the_corridor():
    # a straight 100 km corridor from (0,0) to (0,~0.9deg); 25 km in is a quarter along
    lat, lon = place_by_km(STRAIGHT_POLYLINE, STRAIGHT_KMS, 25.0)
    assert lat == pytest.approx(-0.2249, abs=1e-3)

def test_km_placement_is_reported_not_silent(capsys):
    build(codes=['ZZZ'], osm=[])
    assert 'ZZZ' in capsys.readouterr().out

def test_a_km_placed_station_is_excluded_from_junction_ranking():
    assert rank_of('ZZZ') == 'other'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_stations.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the two-pass placement**

Pass one: match each of the 396 codes on OSM `railway:ref`. Pass two, for the rest: a corridor is routed between its *matched* stations only, then each unmatched station is placed at its official km along that routed polyline. Unmatched stations are interior to a matched span, which is why this terminates — assert that and fail loudly if a corridor has fewer than two matched stations.

**The register's 396 codes are not the complete station list of Java.** Its distance tables measure between the stations it cares about and omit some minor halts the regional PDFs call at: Gadobangkong (`GK`) and Leuwigoong (`LO`) are called at by 45 Bandung trips in today's feed and appear in no corridor table. Such stations have no km post and **cannot** be km-placed; they must come from OSM or from the existing `data/stations.csv`, exactly as today. The set of codes to resolve is the register's 396 **plus** every code the three published regions call at, and no published-region station may be dropped — assert that.

**Measured once the island station cache landed** (`data/osm/java/stations.csv`, 502 stations, 454 with a code): **380 of the 396 register codes match a `railway:ref` directly.** The sixteen that do not are `BPR BST CGD GS KDO KLM KMR MGA MSR MST PSJ PWR SOA STM TAU TOJB`. Most are interior to a corridor with matched neighbours and go to the km-post pass as planned. Two cases need more than the plan provides:

- **A duplicated `railway:ref` must be disambiguated, never resolved first-match-wins.** OSM tags two real stations `TGR`: Tegalluar Summarecon near Bandung (−6.964, 107.715) and Temuguruh near Banyuwangi (−8.310, 114.202), 650 km apart. The register's `TGR` sits between `SGJ` and `KSL` on Ketapang–Bangil, so it is Temuguruh. `build_stations.py` today does `by_ref.setdefault(...)`, and in sorted order that keeps **Tegalluar** — an East Java station placed in West Java. Where a ref is ambiguous, choose the candidate nearest the code's own corridor neighbours, and report every ambiguity resolved. Test it with `TGR`.
- **A short branch with no matched station cannot be km-placed.** The airport station `BST` appears only in the inline pair `BPR–BST`, and `BPR` is unmatched too, so there is no matched anchor to measure from — and 64 Commuter Line Bandara Soetta trains end there. `CGD`, at the end of `KEN–CGD`, has one anchor but no routed polyline to walk. The register does name both ends in full in its corridor title lines (`BATUCEPER - BANDARA SOEKARNO HATTA`, `KRENCENG - CIGADING`), and 48 OSM stations carry no code, so match these few by **name** against the title lines, as a last pass after `railway:ref` and km post. A station that none of the three passes can place fails the build loudly; it is never silently dropped or guessed.

Note the ordering constraint this creates: Task 6 must expose its routing helper so this task can call it, or this pass runs after Task 6. Implement the helper in Task 6 first and import it here.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_stations.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/build_stations.py tests/test_stations.py
git commit -m "feat: place register stations by km post when OSM has no ref"
```

---

### Task 6: Segment library

**Files:**
- Modify: `scripts/build_shapes.py`
- Test: `tests/test_shapes.py`

**Interfaces:**
- Produces:
  - `segment_key(a: str, b: str) -> str` — `"A>B"`, direction-sensitive, category-blind.
  - `route_segment(graph, snap, a, b) -> list[tuple[float, float]]` — A\* with a haversine heuristic.
  - `rdp_tolerance(length_km: float) -> float` — 8 m under 20 km, rising to 60 m above 300 km.
  - `gtfs/segments.txt` — `segment_id,pt_lat,pt_lon,pt_sequence,dist_traveled`.
  - `gtfs/trips.txt` gains a `segments` column: the ordered `|`-joined segment keys.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_segment_is_stored_once_for_every_trip_using_it():
    lib = build_segments(trips=[['A', 'B', 'C'], ['A', 'B', 'D']])
    assert sorted(lib) == ['A>B', 'B>C', 'B>D']

# Review Focus 4
def test_segment_keys_ignore_service_and_category():
    lib = build_segments(trips=[['A', 'B']], categories=['Argo', 'Barang', 'Commuter Line'])
    assert list(lib) == ['A>B']

def test_the_reverse_direction_is_its_own_segment():
    assert segment_key('A', 'B') != segment_key('B', 'A')

def test_astar_finds_the_same_path_as_dijkstra():
    assert route_segment(G, SNAP, 'A', 'Z') == nx.shortest_path(G, SNAP['A'], SNAP['Z'], weight='weight')

def test_rdp_tolerance_grows_with_length():
    assert rdp_tolerance(10) == 8.0
    assert rdp_tolerance(400) == 60.0
    assert rdp_tolerance(100) > rdp_tolerance(50)

def test_station_nodes_survive_simplification():
    out = rdp(PTS, 60.0, LAT0, pinned={PTS[3]})
    assert PTS[3] in out

def test_an_unroutable_pair_is_flagged_not_silently_straightened():
    seg, straight = route_segment_reporting(G_DISCONNECTED, SNAP, 'A', 'Z')
    assert straight is True
    assert len(seg) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_shapes.py -v`
Expected: FAIL

- [ ] **Step 3: Rework `build_shapes.py`**

One graph for the `java` region, built by the existing `build_graph` unchanged — its stitching and hole-bridging carry over, and `BRIDGE = 6000.0` stays. Replace `nx.shortest_path` with `nx.astar_path` and a haversine heuristic, because the island graph is roughly twenty times a regional one. Route per station pair rather than per trip chain, cache by `segment_key`, and keep the existing detour guard and `straightened` reporting, now per segment.

The three published regions keep their own graphs and their current per-trip shapes; this task adds the segment path alongside, it does not replace it. `gtfs/shapes.txt` stays for them.

- [ ] **Step 4: Run the tests, then the build**

Run: `pytest tests/test_shapes.py -v`
Expected: PASS, 7 tests

Run: `python scripts/build_shapes.py`
Expected: roughly 450 segments; every straightened pair listed with its gap.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_shapes.py tests/test_shapes.py gtfs/segments.txt gtfs/trips.txt
git commit -m "feat: segment library routed over one island graph"
```

---

### Task 7: National GTFS

**Files:**
- Modify: `scripts/build_gtfs.py`, `scripts/validate.py`
- Test: `tests/test_validate.py`

**Interfaces:**
- Produces:
  - `route_id` scheme: `CL_<REGION>_<LINE>` kept for the three published regions; `KA_<CATEGORY>_<SERVICE>` for register services.
  - `secs_from_duration(dep: str, duration: str) -> tuple[int, int]` — departure in seconds from midnight and arrival as `departure + duration`, with `duration` read as `HH.MM`. Derives the arrival rather than reconciling the printed one, so a run of any length works.
  - `stop_times.txt` rows only for published calls: origin, destination and via points for register trains.

- [ ] **Step 1: Write the failing tests**

```python
# Review Focus 1
def test_a_run_crossing_midnight_gets_an_arrival_past_86400():
    assert secs_from_duration('22:35', '02.45') == (81300, 90000)

def test_a_run_inside_one_day_is_untouched():
    assert secs_from_duration('09:10', '07.45') == (33000, 60900)

def test_duration_is_hhmm_not_a_decimal():
    # the register's only run over 24 h; float('26.50') would be 24 h 30 m short
    dep, arr = secs_from_duration('23:25', '26.50')
    assert arr - dep == 1610 * 60
    assert arr % 86400 == 2 * 3600 + 15 * 60     # lands on the printed 02:15

def test_a_register_trip_has_only_published_calls():
    rows = stop_times_for(TRAIN_WITH_30_STATION_CHAIN)
    assert len(rows) == 2

def test_a_via_relasi_gets_three_calls():
    assert len(stop_times_for(TRAIN_GMR_SBI_JR)) == 3

def test_validate_accepts_coordinates_across_the_island():
    assert validate_coords([('BOO', -6.595, 106.79), ('KTG', -8.19, 114.37)]) == []

def test_national_route_ids_are_distinct_per_service():
    assert route_id('Argo', 'ARGO BROMO ANGGREK') != route_id('Argo', 'ARGO SEMERU')
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_validate.py -v`
Expected: FAIL

- [ ] **Step 3: Implement**

`validate.py`'s coordinate check currently warns outside an East Java bbox; widen it to the island bbox from `data/regions.json`. Its speed check stays as-is and now covers intercity trains, where an end-to-end average over a routed distance is a genuinely useful sanity check.

- [ ] **Step 4: Run the tests, then the build**

Run: `pytest tests/test_validate.py -v && python scripts/build_gtfs.py && python scripts/validate.py`
Expected: PASS; `stop_times.txt` around 10k rows, not 100k.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_gtfs.py scripts/validate.py tests/test_validate.py gtfs
git commit -m "feat: emit national trains into the GTFS feed"
```

---

### Task 8: Bundle

**Files:**
- Modify: `scripts/make_bundle.py`
- Test: `tests/test_bundle.py`

**Interfaces:**
- Produces, in `data/bundle.json`:
  - `segments: {key: {c, d}}` replacing per-trip `shapes` for register trips; `shapes` retained for the three published regions.
  - trip gains `g` (segment key list, omitted when `s` is set), `c` (category), `o` (operator), `f` (true when FAKULTATIF), `t` (`"published"` | `"endpoint"`), `x` (true when any segment was straightened).
  - `suppress_duplicates(trips) -> list` — drops register trips whose `(service, region)` a published trip already covers.

- [ ] **Step 1: Write the failing tests**

```python
def test_yogyakarta_register_trips_are_suppressed_by_service_and_region():
    kept = suppress_duplicates([
        {'id': 'pub', 'service': 'COMMUTER LINE YOGYAKARTA', 'region': 'yogyakarta', 't': 'published', 'n': '661'},
        {'id': 'reg', 'service': 'COMMUTER LINE YOGYAKARTA', 'region': 'yogyakarta', 't': 'endpoint', 'n': '708'},
    ])
    assert [t['id'] for t in kept] == ['pub']

def test_suppression_never_keys_on_train_number():
    # 661 and 708 are the same service; numbering is exactly what disagrees
    assert len(suppress_duplicates(SAME_SERVICE_DIFFERENT_NUMBERS)) == 1

def test_surabaya_keeps_both_published_and_distinct_register_services():
    assert len(suppress_duplicates(SURABAYA_MIXED)) == len(SURABAYA_MIXED)

def test_the_final_count_is_1764():
    assert len(json.load(open('data/bundle.json'))['trips']) == 1764

def test_a_register_trip_references_segments_not_a_shape():
    trip = trip_by_id('KA_ARGO_ARGO_BROMO_ANGGREK_1')
    assert 'g' in trip and 's' not in trip
    assert len(trip['k']) == 2

def test_keyframe_distances_are_non_decreasing_for_every_trip():
    for trip in BUNDLE['trips']:
        ds = [c[2] for c in trip['k']]
        assert ds == sorted(ds)

def test_raw_bundle_gzips_under_the_target():
    assert len(gzip.compress(open('data/bundle.json', 'rb').read())) < 1_500_000
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bundle.py -v`
Expected: FAIL

- [ ] **Step 3: Implement**

Keep `proj()` exactly as it is for published trips — its first-pass rule is what makes the circular Dhoho and Penataran runs work, and the comment at `make_bundle.py:44-57` explains why. Register trips need no projection: their keyframe distances come from the segment library's cumulative distance at each published call.

- [ ] **Step 4: Run the tests, then the build**

Run: `pytest tests/test_bundle.py -v && python scripts/make_bundle.py`
Expected: PASS; 1,764 trips, ~450 segments, gzipped size printed.

- [ ] **Step 5: Commit**

```bash
git add scripts/make_bundle.py tests/test_bundle.py
git commit -m "feat: bundle all 1,764 Java trains with a segment library"
```

---

### Task 9: National verification

**Files:**
- Modify: `scripts/validate_gapeka.py`, `scripts/check-geometry.mjs`

**Interfaces:**
- Produces: `national_pass(register, bundle) -> list[str]` and a budget gate — fails above 2% of relasi disagreeing, or any single relasi off by more than 10%.

- [ ] **Step 1: Write the failing test**

```python
def test_the_budget_tolerates_noise_but_not_a_gross_error():
    assert over_budget(disagreements=6, total=316, worst=0.04) is False     # 1.9%
    assert over_budget(disagreements=7, total=316, worst=0.04) is True      # 2.2%
    assert over_budget(disagreements=1, total=316, worst=0.11) is True      # one gross
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_validate.py::test_the_budget_tolerates_noise_but_not_a_gross_error -v`
Expected: FAIL

- [ ] **Step 3: Implement**

Keep the existing per-region pass and its zero tolerance untouched — it is the strongest check in the repo and the three published regions must keep passing it exactly as today. Add the national pass beside it. `check-geometry.mjs` walks `segments` as well as `shapes`.

**One documented exception, not a widened tolerance.** After Task 4's km-matched selection, 314 of 316 relasi agree with the register. The two that do not are `YIA - YK` and `YK - YIA`, the Yogyakarta airport branch, carrying 25 trains: the register prints 40.237 km where the best simple path measures 33.471. The shortfall is **exactly** the Wates–Kedundang edge, 6.766 km, so the official distance includes an out-and-back over that stretch — a path that revisits Kedundang, which is not a simple path and which `nx.shortest_simple_paths` therefore cannot enumerate at any cap. The chain we do produce (`YIA KDG STL RWL PTN YK`) is geographically correct; it merely omits a short reversal.

So the budget gate takes an **explicit exception list** naming these two relasi with that reason, rather than a tolerance wide enough to swallow a 16.8% error everywhere. An unexplained relasi over 10% still fails the build. If a later task teaches the selector to allow one reversal, delete the exception rather than keeping both.

**The register is not perfectly self-consistent, so do not cross-check its cells.** On page 55's 42-station Cikampek–Banjar matrix, four cells disagree with the cumulative km by exactly 1.042 km (rows RJP and IH against columns KNP and BJR). The cumulative km themselves are self-consistent and safe, which is what Task 5's km-post placement relies on; it is the off-diagonal cells that are wrong. Verify against cumulative km, never against the full matrix, or this will read as a pipeline bug.

- [ ] **Step 4: Run both verifications**

Run: `npm run verify:geometry && npm run verify:gapeka`
Expected: both pass; the national report prints its disagreement count against the budget.

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_gapeka.py scripts/check-geometry.mjs tests/test_validate.py
git commit -m "feat: national verification with a failure budget"
```

---

### Task 10: Runtime bundle and bounded easing

**Files:**
- Create: `vitest.config.ts`, `src/data/__tests__/bundle.test.ts`, `src/sim/__tests__/trains.test.ts`
- Modify: `src/data/bundle.ts`, `src/sim/trains.ts`, `package.json` (add `vitest`, `"test": "vitest run"`)

**Interfaces:**
- Consumes: the bundle fields from Task 8.
- Produces:
  - `BundleTrip` gains `g?: string[]`, `c: string`, `o: string`, `f?: boolean`, `t: 'published' | 'endpoint'`, `x?: boolean`.
  - `assembleShape(bundle, trip) -> BundleShape` — concatenates segments, sharing coordinate arrays by reference.
  - `EASE_METRES = 2000` in `trains.ts`, replacing `EASE_STRENGTH`.

- [ ] **Step 1: Write the failing tests**

```ts
it('assembles a trip shape from its segment list', () => {
  const shape = assembleShape(BUNDLE, TRIP_WITH_THREE_SEGMENTS);
  expect(shape.c.length).toBe(SEG_A.c.length + SEG_B.c.length + SEG_C.c.length - 2);
  expect(shape.d[shape.d.length - 1]).toBeCloseTo(TOTAL_KM, 3);
});

it('shares segment coordinates between trips rather than copying', () => {
  const a = assembleShape(BUNDLE, TRIP_1);
  const b = assembleShape(BUNDLE, TRIP_2);          // both use SEG_A
  expect(a.c[0]).toBe(b.c[0]);                      // same object identity
});

it('indexes only published calls into callsByStop', () => {
  const net = buildNetwork(BUNDLE_WITH_ONE_ENDPOINT_TRIP);
  expect(net.callsByStop.get('MIDDLE_STATION')).toBeUndefined();
});

it('hits every published time exactly', () => {
  for (const [arrival, , km] of TRIP.k) {
    expect(trainAt(TRIP, SHAPE, arrival)!.distance).toBeCloseTo(km, 3);
  }
});

it('runs at constant speed across the middle of a long leg', () => {
  // 700 km in 10 h: the two middle thirds must differ by under 2%
  const v1 = speedAt(LONG_TRIP, 0.4), v2 = speedAt(LONG_TRIP, 0.6);
  expect(Math.abs(v1 - v2) / v1).toBeLessThan(0.02);
});

it('still brakes into a stop on a short commuter leg', () => {
  expect(speedAt(SHORT_TRIP, 0.97)).toBeLessThan(speedAt(SHORT_TRIP, 0.5));
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run`
Expected: FAIL

- [ ] **Step 3: Implement**

`assembleShape` concatenates each segment's `c` by reference and rebuilds `d` as a running total, dropping the duplicated joint point between consecutive segments. Easing: accelerate over `min(EASE_METRES, legLength / 2)` from each end and hold constant speed between, so the published arrival and departure are still hit exactly. Keep `smoothstep` for the eased portions.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run && npm run check`
Expected: PASS, no type errors

- [ ] **Step 5: Commit**

```bash
git add vitest.config.ts package.json src/data src/sim
git commit -m "feat: assemble trips from segments and bound train easing by distance"
```

---

### Task 11: Map layers

**Files:**
- Create: `src/map/__tests__/trackLayer.test.ts`, `src/map/__tests__/stationLayer.test.ts`
- Modify: `src/map/trackLayer.ts`, `src/map/stationLayer.ts`

**Interfaces:**
- Produces:
  - `CATEGORY_PRIORITY: string[]` — `['Commuter Line', 'Argo', 'Eksekutif', 'Ekonomi Jarak Jauh', 'Ekonomi Lokal', 'Bandara', 'Barang']`.
  - `segmentColor(categories: Set<string>, routes: Bundle['routes']) -> string` — highest priority wins; freight-only returns the neutral rail grey `#8a9099`.
  - `setVisibleRoutes(map, visible)` keeps its signature but filters on a `segments` property.
  - `stationRank(code, corridors) -> 'terminus' | 'junction' | 'other'`

- [ ] **Step 1: Write the failing tests**

```ts
it('gives a shared segment the highest-priority category colour', () => {
  expect(segmentColor(new Set(['Barang', 'Commuter Line']), ROUTES)).toBe(COMMUTER_COLOR);
});

it('draws a freight-only segment in neutral grey', () => {
  expect(segmentColor(new Set(['Barang']), ROUTES)).toBe('#8a9099');
});

it('hides a segment only when no visible route uses it', () => {
  expect(visibleSegments(BUNDLE, new Set(['KA_ARGO_X']))).toContain('A>B');
  expect(visibleSegments(BUNDLE, new Set())).toHaveLength(0);
});

it('ranks a station by how many corridors touch it', () => {
  expect(stationRank('SMT', CORRIDORS)).toBe('junction');
  expect(stationRank('MER', CORRIDORS)).toBe('terminus');
});

it('leaves a km-placed station unranked', () => {
  expect(stationRank('ZZZ', CORRIDORS)).toBe('other');
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run src/map`
Expected: FAIL

- [ ] **Step 3: Implement**

`toGeoJSON` in `trackLayer.ts` now emits one feature per segment rather than per shape, each carrying its category set; `routeOfShape` goes away. When one region or line is selected its own colour wins on its segments, which preserves today's look for the views that already exist. The station layer keeps `minzoom: 9` for the detailed views and shows only `terminus` and `junction` ranks below it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run && npm run check`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/map
git commit -m "feat: draw the segment library with category colour priority"
```

---

### Task 12: Panels and wiring

**Files:**
- Modify: `src/ui/linePanel.ts`, `src/ui/trainPanel.ts`, `src/main.ts`, `src/styles.css`

**Interfaces:**
- Consumes: Tasks 10 and 11.
- Produces: category-grouped chips, a FAKULTATIF toggle defaulting off, and a provenance line on the detail card.

- [ ] **Step 1: Write the failing test**

```ts
it('excludes fakultatif trips from the default visible set', () => {
  expect(defaultVisible(NET).has('KA_ARGO_PARAHYANGAN_FAKULTATIF')).toBe(false);
  expect(defaultVisible(NET).has('KA_ARGO_ARGO_BROMO_ANGGREK')).toBe(true);
});

it('labels an endpoint-timed train as such', () => {
  expect(renderTrainPanel(NET, ENDPOINT_STATE, 0, false)).toContain('Timed end to end');
});

it('labels a published train as such', () => {
  expect(renderTrainPanel(NET, PUBLISHED_STATE, 0, false)).toContain('Published calling times');
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run src/ui`
Expected: FAIL

- [ ] **Step 3: Implement**

`initLinePanel` groups by category instead of region, each group collapsible, chips keeping the existing dot-name-count markup and `--chip` custom property. The region picker keeps its `All Java` entry plus the three published regions. `trainPanel.ts` replaces the hardcoded `<span class="badge">Commuter</span>` with the trip's category, and adds one provenance line. No new colours, radii or type styles — the four radii and the OKLCH neutrals already in `styles.css` cover it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run && npm run check`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ui src/main.ts src/styles.css
git commit -m "feat: category groups, fakultatif toggle and timing provenance"
```

---

### Task 13: Documentation and live verification

**Files:**
- Modify: `README.md`, `package.json`

- [ ] **Step 1: Run the whole pipeline from scratch**

Run, in order:

```bash
python scripts/parse_gapeka.py && python scripts/build_java_network.py && python scripts/build_stations.py && python scripts/build_gtfs.py && python scripts/build_shapes.py && python scripts/validate.py && python scripts/make_bundle.py
```

Expected: 1,764 trips, ~450 segments, no non-monotonic trips.

- [ ] **Step 2: Run every check**

Run: `pytest -q && npx vitest run && npm run check && npm run verify:geometry && npm run verify:gapeka`
Expected: all pass.

- [ ] **Step 3: Verify in the browser**

Start the `jtv-dev` preview. Confirm, with a screenshot of each: the All Java view with trains across the island; a long-distance train selected, showing two calls and the end-to-end provenance line; a Surabaya commuter train selected, still showing its full published calling list; and the freight chip toggling grey segments on and off. Check the console for errors and the network panel for the bundle's transfer size.

- [ ] **Step 4: Update the README**

Rewrite the opening claim and the region table for 1,764 trains across the island. Add the register to the data-source table as the primary source. Extend the "four things worth knowing about" list with the parsing facts from Tasks 2 and 5 — the interleaved header, the first-value km rule, and km-post station placement. Record under known gaps that register-sourced trains are timed end to end, and that Yogyakarta's register rows are suppressed in favour of its published times.

- [ ] **Step 5: Commit**

```bash
git add README.md package.json
git commit -m "docs: 1,764 trains across Java"
```

---

## Self-Review

**Spec coverage.** Every section maps to a task: register parsing → 1, 2, 4; topology and relasi → 3; island OSM → 4; station coordinates → 5; segment library → 6; GTFS → 7; bundle and Yogyakarta suppression → 8; verification budget → 9; runtime and easing → 10; track and station layers → 11; panels → 12; README → 13. All seven post-review decisions are carried: 1 in Tasks 7, 8 and 10; 2 in Task 8; 3 in Task 9; 4 in Task 8's gzip test; 5 in Task 5; 6 in Task 7; 7 in Task 12.

**Known ordering constraint.** Task 5 needs Task 6's routing helper. Implement Task 6 first, or extract the helper as Task 6's first step. This is called out in Task 5, Step 3.

**Type consistency.** `segment_key`/`segmentColor`/`visibleSegments`, `assembleShape`, `place_by_km`, `stationRank`, `suppress_duplicates`, `secs_crossing_midnight`, `national_pass` and `route_relasi` each appear with one signature throughout. Trip fields `g`, `c`, `o`, `f`, `t`, `x` are defined once in Task 8 and consumed under those names in Tasks 10–12.

**Review Focus coverage.** All five have tests in the owning task: midnight in 7, repeated station in 3, junction km in 2, shared relasi in 6, empty tile in 4.

**Proportion.** Thirteen tasks against a spec of comparable length. Code blocks are test assertions and signatures; no function bodies are transcribed.
