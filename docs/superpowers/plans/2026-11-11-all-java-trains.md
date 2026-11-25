# Every Train on Java Implementation Plan — revision 2

> **For agentic workers:** Implement task by task, each followed by a fresh review before the next starts. Steps use checkbox (`- [ ]`) syntax for tracking. The `superpowers:subagent-driven-development` skill this header once named is not installed here; the loop is run by hand.

**Goal:** Animate every train in GAPEKA 2026 — 2,089 timetabled runs covering 1,811 of the register's 1,815 trains — at the times the timetables print, along real OpenStreetMap track.

**Architecture:** GAPEKA 2026 prints a station-by-station timetable for every train. Each run's printed station sequence is its route; each consecutive station pair is routed once over an island-wide OSM rail graph and stored in a shared segment library; every timetable row becomes a keyframe that knows whether it is a stop or a pass, and whether its time is printed or estimated. The register and the distance tables, parsed by Tasks 1-4, stop being sources of times and become independent checks on distance.

**Tech Stack:** Python 3.11 (pdfplumber, networkx, scipy, numpy, requests), pytest; TypeScript, Vite, MapLibre GL JS, three.js, vitest.

**Spec:** [docs/superpowers/specs/2026-11-11-all-java-trains-design.md](../specs/2026-11-11-all-java-trains-design.md), revision 2. Read it before any task: this plan argues from it.

**Repository:** `D:\Project\Indonesian-Railway-`. An older clone at `D:\Project\Java Train VIsualizer` is redundant; never work there.

## Global Constraints

- **Source:** GAPEKA 2026, decree KP-DJKA 116/2026, valid from 1 December 2026. The 61 MB PDF is **not committed**; the parser reads a committed text cache under `data/gapeka/2026/`. No test may open the PDF.
- **Counts the build must reproduce:** 2,089 timetabled runs, 48,685 station rows, 466 station codes; the register's 1,815 rows, 1,811 of them covered by a timetable. The four without one, `R951`-`R954`, are empty-stock moves and are not drawn.
- **Every printed time is kept exactly.** Untimed rows (`Ls -`, `Berh Sb`) get estimated times and an `estimated` flag, and the UI never shows an estimated time as a printed one.
- **A pass is never a call.** Passes stay out of the departures board and the route diagram's stops, and trains do not brake at them.
- The readings of `Ls` (passes) and `Berh Sb` (stops) are **inferences**: the document has no legend. Code that relies on them says so.
- Bundle under **1.5 MB gzipped**.
- FAKULTATIF runs are off by default.
- Overpass is a donated service. The island caches in `data/osm/java/` are committed and complete; no task refetches them, and no test touches the network.
- `pdfplumber==0.11.4`, `pillow<12` stay pinned. Run tests with `python -m pytest -q`; `pytest` is not on PATH.
- No IO in `scripts/gapeka/`: functions there take their data as arguments.
- Commit messages follow the repository's style — sentence-case imperative subject, no type prefix, a body saying why. Do not push.
- `dist/` and `public/data/bundle.json` stay generated, never committed.

## Review Focus

Five failure modes the spec implies but no happy path exercises. Each has its test in the task that owns the code.

1. **A contents-list entry counted as a train.** Every timetable section opens with a contents list that repeats each train's header line with no rows beneath it. Counting headers rather than runs with rows gives about 3,400 "trains". → Task 5.
2. **A run crossing midnight.** Printed times go backwards when the day turns (`23:58:00`, then `00:03:00`). Each step is short, so the rule is step-wise: a printed time earlier than the previous one has crossed midnight. Revision 1 learned that end-to-end arithmetic fails here — Kenlimas Cargo ran 26 h 50 min, so a single "arrival before departure, add a day" rule put it a day short. → Task 5.
3. **A trip that calls at a station twice.** In 2025 the circular Dhoho and Penataran ran as one trip through Wonokromo and Gubeng twice. **In 2026 no run calls at any station twice**: those services are printed as one-way legs (KA 435 Surabaya→Kertosono, KA 436 back by Blitar and Malang), which Task 5 confirmed over the whole document. Since each timetabled run is its own trip, a repeat can only appear if legs are ever merged. Task 5 pins "no run repeats a station" over the whole document; Task 10 keeps its non-decreasing-distance test as the guard, and any merge of legs would have to keep both visits. → Tasks 5 and 10.
4. **An express braking at the stations it runs through.** Easing on every keyframe would stop an Argo at each of the dozens of stations it passes, and indexing every keyframe would put it on their departures boards. → Task 12.
5. **An estimated time outside its neighbours.** An untimed row is estimated between the nearest printed times either side. That only works if every run's first and last rows are printed, and if consecutive untimed rows get times in order. → Task 5.

---

## Done: Tasks 1-4 (revision 1, on the 2025 register)

Built, reviewed and committed. What each left that revision 2 uses:

| Task | Commits | Carries over |
| --- | --- | --- |
| 1 Register rows | `b2a83f6`, `3a997b1` | `rows.py`: `parse_train_row`, `scan_sections`, `scan_categories`. Needs only optional seconds for 2026 (Task 6). |
| 2 Distance tables | `d3dd743`, `b68a453` | `tables.py`: the matrix parser, which reads the 2026 tables unchanged (36 corridors, all monotonic from 0). |
| 3 Topology | `be1044d`, `3479ee6` | `topology.py`: `build_topology`, `route_relasi`; `tables.py`: `recover_vertical_codes`. |
| 4 CLI and island fetch | `eb00f28` … `da57e8f` | `fetch_osm.py` and the committed island caches; the junction split (`69e9c18`) and the Wates/Kedundang erratum (`1fadee3`), both still needed because the 2026 tables carry the same data. `build_java_network.py`'s route selection is retired by Task 11. |

The fix round `69e9c18`-`da57e8f` was not given its own review. **Task 5's reviewer also reviews those six commits.**

---

## File Structure

**New:**
- `scripts/gapeka/timetables.py` — pure parser for the timetable pages: runs, rows, kinds, times.
- `scripts/cache_gapeka_2026.py` — builds `data/gapeka/2026/` from the PDF, once; never run by the build.
- `data/gapeka/2026/pages.json` (page text) and `data/gapeka/2026/words.json` (word coordinates, distance-table pages only).
- `data/gapeka/timetables.json` — output.
- `scripts/verify_distances.py` — the national distance check.
- `tests/test_timetables.py`, `tests/fixtures/timetables_2026.txt`, `tests/fixtures/register_2026.txt`, `tests/test_stations.py`, `tests/test_shapes.py`, `tests/test_gtfs.py`, `tests/test_bundle.py`, `tests/test_verify.py`.
- `vitest.config.ts`, `src/**/__tests__/*.test.ts`.

**Modified:**
- `scripts/gapeka/rows.py` (optional seconds), `scripts/parse_gapeka.py` (2026 cache, timetables), `scripts/build_stations.py`, `scripts/build_shapes.py`, `scripts/build_gtfs.py`, `scripts/validate.py`, `scripts/make_bundle.py`, `scripts/check-geometry.mjs`.
- `src/data/bundle.ts`, `src/sim/trains.ts`, `src/map/trackLayer.ts`, `src/map/stationLayer.ts`, `src/ui/linePanel.ts`, `src/ui/trainPanel.ts`, `src/main.ts`, `src/styles.css`.
- `package.json`, `.github/workflows/deploy.yml`, `README.md`.

**Retired from the build** (files stay, nothing reads them): `scripts/parse_timetable.py`, `scripts/build_java_network.py`, `scripts/validate_gapeka.py`'s 2025 per-region pass, the three regional timetable PDFs, and `data/gapeka/relasi.json`, deleted as a superseded output. The 2025 page cache is kept, moved to `data/gapeka/2025/pages.json`: the carried-forward Tegal–Cepu corridor and its evidence test read it.

---

### Task 5: The 2026 page cache and the timetable parser

**Files:**
- Create: `scripts/cache_gapeka_2026.py`, `scripts/gapeka/timetables.py`, `data/gapeka/2026/pages.json`, `data/gapeka/2026/words.json`, `tests/fixtures/timetables_2026.txt`
- Modify: `scripts/parse_gapeka.py`, `tests/conftest.py`
- Test: `tests/test_timetables.py`

**Interfaces:**
- Produces:
  - `Row(code: str, name: str, max_kmh: int, arr: int | None, dep: int | None, kind: str, note: str)` — times in seconds from midnight, already rolled past 86,400 where the run has crossed midnight. `kind` is one of `origin`, `destination`, `stop`, `pass`, `untimed_pass`, `untimed_stop`.
  - `Run(no: str, service: str, origin: str, destination: str, rows: tuple[Row, ...])`.
  - `parse_runs(pages: dict[str, str]) -> list[Run]` — reads both header forms, `KA 1 (Anggrek) Relasi SBI - GMR` and `KA 2107 (Commuter Line Tangerang) Lintas Pelayanan TNG - DU`; a header with no rows beneath it (a contents-list entry) is not a run.
  - `estimate_times(run: Run, km: list[float]) -> list[tuple[int, int, bool]]` — every row's `(arr, dep, estimated)`, interpolating untimed rows by distance between the nearest printed rows either side.
  - `data/gapeka/timetables.json` — one record per run: `{no, service, origin, destination, rows: [[code, name, max_kmh, arr, dep, kind, note]]}`.

- [ ] **Step 1: Build the cache**

`cache_gapeka_2026.py <pdf>` writes `pages.json` (`{"<page>": "<text>"}` for all 1,887 pages) and `words.json` (`{"<page>": [[x0, top, text], ...]}` for pages 1875-1886 only, which `recover_vertical_codes` needs). A text-only extraction already exists at `D:\Temp\TEMP\claude\38da35d2bebb0815\8151013e-a117-41b3-a2b5-5e3bfbed300d\scratchpad\g26\text26.json`; reuse it for `pages.json` rather than spending eighteen minutes, but `words.json` needs the PDF, at `C:\Users\Ridho\Downloads\KP DJKA 116 TAHUN 2026 GAPEKA JAWA.pdf`, for just those twelve pages. Record in the script's docstring where the PDF came from and how long a full run takes.

Run: `python scripts/cache_gapeka_2026.py "C:/Users/Ridho/Downloads/KP DJKA 116 TAHUN 2026 GAPEKA JAWA.pdf"`
Expected: `data/gapeka/2026/pages.json` of about 3.5 MB and 1,887 pages; `words.json` for twelve pages.

- [ ] **Step 2: Write the failing tests**

Fixture: verbatim lines from page 58 (KA 1 Anggrek, the start of the intercity section), page 669 (the commuter section's contents list and its first timetable), page 1300 (KA 2107-2109, Commuter Line Tangerang), one Dhoho or Penataran run, and a run that crosses midnight. Each block is commented with its page.

```python
def test_both_header_forms_are_read():
    runs = parse_runs(FIXTURE)
    assert {r.no for r in runs} >= {'1', '2107'}

# Review Focus 1
def test_a_contents_list_entry_is_not_a_run():
    runs = parse_runs(PAGE_669)
    assert [r.no for r in runs] == ['351']      # the contents list names many more

def test_row_kinds_come_from_what_the_columns_hold():
    kinds = [row.kind for row in run('2107').rows]
    assert kinds[0] == 'origin' and kinds[-1] == 'destination'
    assert kinds[2] == 'stop'                    # Batuceper, 20:13:00 20:14:00
    assert kinds[1] == 'untimed_stop'            # Tanah Tinggi, Berh Sb

def test_a_pass_carries_one_time():
    tandes = run('1').rows[1]
    assert tandes.kind == 'pass' and tandes.arr == tandes.dep == 8 * 3600 + 21 * 60

def test_an_operational_note_is_kept_but_does_not_change_the_kind():
    row = parse_row('5 Cikampek (CKP) 100 10:00:00 10:05:00 x ka 455 (ka 455 x)')
    assert row.kind == 'stop' and row.note.startswith('x ka 455')

# Review Focus 2
def test_a_run_crossing_midnight_rolls_its_later_times_past_86400():
    times = [r.dep or r.arr for r in run(MIDNIGHT).rows]
    assert times == sorted(times) and times[-1] > 86400

# Review Focus 3
def test_a_run_calling_at_a_station_twice_keeps_both_visits():
    codes = [r.code for r in run(DHOHO).rows]
    assert codes.count('WO') == 2

# Review Focus 5
def test_every_run_starts_and_ends_on_a_printed_time():
    for r in parse_runs(CACHE):
        assert r.rows[0].dep is not None and r.rows[-1].arr is not None

def test_estimated_times_fall_between_their_printed_neighbours_and_in_order():
    est = estimate_times(run('2107'), KM_2107)
    times = [t for a, d, _ in est for t in (a, d)]
    assert times == sorted(times)
    assert [e for _, _, e in est][1] is True     # Tanah Tinggi was estimated

def test_the_whole_document_parses_to_the_counts_the_spec_gives():
    runs = parse_runs(CACHE)
    assert len(runs) == 2089
    assert sum(len(r.rows) for r in runs) == 48685
    assert len({row.code for r in runs for row in r.rows}) == 466
```

- [ ] **Step 3: Run them to verify they fail**

Run: `python -m pytest tests/test_timetables.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'scripts.gapeka.timetables'`

- [ ] **Step 4: Implement `timetables.py`, and `parse_gapeka.py` writing `timetables.json`**

A row is `<n> <Name> (<CODE>) <max_kmh> <arr> <dep> [note]`, with `-` for no time, `Ls` in the arrival column for a pass, and `Berh Sb` in place of both times for an untimed stop. Station names contain spaces and sometimes brackets of their own; anchor on the last `(<CODE>)` before the speed. The six counts in the last test came from a probe and are the target; if the parser disagrees, find out why before changing the test.

- [ ] **Step 5: Run the tests, then the CLI**

Run: `python -m pytest -q && python scripts/parse_gapeka.py`
Expected: all pass; `timetables.json` written with 2,089 runs.

- [ ] **Step 6: Commit**

---

### Task 6: The 2026 register and distance tables

**Files:**
- Modify: `scripts/gapeka/rows.py`, `scripts/parse_gapeka.py`
- Create: `tests/fixtures/register_2026.txt`
- Test: `tests/test_rows.py`, `tests/test_tables.py`

**Interfaces:**
- Produces: `data/gapeka/trains.json` from the 2026 register (pages ~1828-1874), `data/gapeka/network.json` from the 2026 distance tables (pages 1875-1886), each regenerated in place. `match_runs(runs, register) -> dict[str, str]` — run number to the register number it belongs to, matching either the number itself or a part of a paired number such as `32-33`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_2026_register_row_parses_with_seconds_omitted():
    row = parse_train_row('2 1 REGULER Anggrek Anggrek 1 SBI-GMR PT. KAI 720,109 720 08:15 16:12 07.57')
    assert row['no'] == '1' and row['dep'] == '08:15' and row['km'] == 720.109

def test_2025_rows_still_parse():                # Task 1's fixtures must stay green
    assert parse_train_row(REGISTER_2025[0])['dep'] == '09:10'

def test_every_register_row_but_the_four_empty_stock_moves_has_a_run():
    unmatched = set(REGISTER_2026) - set(match_runs(RUNS, REGISTER_2026).values())
    assert sorted(unmatched) == ['R951', 'R952', 'R953', 'R954']

def test_every_banner_tallies_against_its_section():
    sections = scan_sections(PAGES_2026)
    assert [s.name for s in sections if s.trains and s.tally != s.claimed] == []

def test_the_2026_tables_carry_the_wates_kedundang_erratum():
    chain = corridor_from(KTA, NETWORK_2026)
    assert [c for c, _ in chain][3:5] == ['KDG', 'WT']
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_rows.py tests/test_tables.py -q`
Expected: the 2026 cases FAIL.

- [ ] **Step 3: Implement**

Make the seconds in `ROW`'s two time groups optional; every 2025 assertion must still hold. **Settle the banner reconciliation**: the banners read so far claim 1,274 trains against 1,809 register rows, while in 2025 they tallied exactly. Find how the commuter sections word their banners. If a section genuinely prints no count, say so in the code and test the sections that do. Do not loosen the tally to make it pass. The distance tables run through `recover_vertical_codes` with the twelve pages' words, then `apply_errata`; report whether vertical-text recovery was needed on any 2026 page.

Also list every run with no register row — the probe found about four — and give each a category from its timetable section, flagged, rather than a silent default.

**Two corrections to the 2026 tables, both measured after Task 5** (see the spec's "One corridor is missing from the 2026 tables"):
- **Carry the Tegal–Semarang–Brumbung–Gambringan–Cepu corridor forward from 2025.** Page 1880 prints its title but not its matrix, and has no image. Take it from the 2025 network, apply the Wates/Kedundang erratum as for every corridor, and record its provenance on the corridor so the report can say which table came from which edition. Pin, in a test, the evidence that justifies it: of the corridors both editions print, all agree station for station except Tanah Abang–Merak at Serpong (24.278 → 23.201). If that ever stops being true, the test must fail rather than the carry-forward silently staying. Without this corridor the Brumbung `Junction` raises its "out of date" error — the guard is right to.
- **Alias the tables' `BET` to `SBE`** (Benteng), which the 2026 timetables and OSM both use, at identical km. A named alias, like the erratum, with the evidence in its comment.

- [ ] **Step 4: Run the tests, then the CLI**

Run: `python -m pytest -q && python scripts/parse_gapeka.py`
Expected: all pass; `trains.json` and `network.json` regenerated from 2026.

- [ ] **Step 5: Delete the superseded 2025 outputs and commit**

`git rm data/gapeka/relasi.json data/gapeka/pages.json`, then commit.

---

### Task 7: Station coordinates for the 466 codes

**Files:**
- Modify: `scripts/build_stations.py`, `scripts/build_shapes.py`
- Test: `tests/test_stations.py`

**Interfaces:**
- Produces:
  - `route_between(graph, a: tuple[float, float], b: tuple[float, float]) -> list[tuple[float, float]]` in `build_shapes.py` — A* over the island graph with a haversine heuristic. Task 8 reuses it.
  - `place_by_km(polyline, cumulative_km, km) -> tuple[float, float]`.
  - `data/stations.csv`, one row per timetable code, `source` one of `osm-ref`, `osm-name`, `km-post`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_code_matched_on_railway_ref_wins():
    assert build(codes={'YK': 'Yogyakarta'}, osm=[OSM_YK])['YK']['source'] == 'osm-ref'

def test_a_code_with_no_ref_is_matched_on_its_printed_name():
    rows = build(codes={'BST': 'Bandara Soekarno Hatta'}, osm=[OSM_BST_NO_REF])
    assert rows['BST']['source'] == 'osm-name'

def test_a_ref_on_two_stations_takes_the_one_nearest_its_neighbours():
    # OSM tags Tegalluar Summarecon (Bandung) and Temuguruh (Banyuwangi) both TGR;
    # the timetables put TGR between SGJ and KSL, so it is Temuguruh.
    rows = build(codes={'TGR': 'Temuguruh'}, osm=[OSM_TEGALLUAR, OSM_TEMUGURUH],
                 neighbours={'TGR': ['SGJ', 'KSL']}, placed=SGJ_KSL)
    assert rows['TGR']['lon'] == pytest.approx(114.2018, abs=1e-3)

def test_a_code_placed_by_km_post_lies_on_its_corridor():
    lat, lon = place_by_km(STRAIGHT_POLYLINE, STRAIGHT_KMS, 25.0)
    assert lat == pytest.approx(-0.2249, abs=1e-3)

def test_a_station_no_pass_can_place_fails_the_build():
    with pytest.raises(SystemExit, match='ZZZ'):
        build(codes={'ZZZ': 'Nowhere'}, osm=[])
```

- [ ] **Step 2: Run them to verify they fail**

- [ ] **Step 3: Implement**

The three passes run in order: `railway:ref`, then printed name (normalised with the existing `norm()`), then km post for a code in the distance tables. Name matching is a fallback, never an override of a ref match. Report every ambiguous ref, with how it was resolved, and every station placed by name or km post, so upstream OSM can be improved. Report the final tally by source.

- [ ] **Step 4: Run the tests, then the CLI**

Run: `python -m pytest -q && python scripts/build_stations.py`
Expected: 466 stations, none unplaced; the tally printed.

- [ ] **Step 5: Commit**

---

### Task 8: Segment library

**Files:**
- Modify: `scripts/build_shapes.py`
- Test: `tests/test_shapes.py`

**Interfaces:**
- Consumes: `route_between` from Task 7, `data/gapeka/timetables.json`, `data/stations.csv`, `data/osm/java/rail.geojson`.
- Produces:
  - `segment_key(a: str, b: str) -> str` — `"A>B"`, direction-sensitive.
  - `rdp_tolerance(length_km: float) -> float` — 8 m under 20 km, rising to 60 m above 300 km.
  - `gtfs/segments.txt` (`segment_id,pt_lat,pt_lon,pt_sequence,dist_traveled`) and each run's ordered segment keys.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_segment_is_stored_once_however_many_runs_use_it():
    lib = build_segments([['A', 'B', 'C'], ['A', 'B', 'D']])
    assert sorted(lib) == ['A>B', 'B>C', 'B>D']

def test_the_reverse_direction_is_its_own_segment():
    assert segment_key('A', 'B') != segment_key('B', 'A')

def test_a_run_that_calls_twice_at_a_station_reuses_its_segments():
    keys = run_segments(['SB', 'WO', 'SGU', 'WO', 'SB'])
    assert keys == ['SB>WO', 'WO>SGU', 'SGU>WO', 'WO>SB']

def test_rdp_tolerance_grows_with_length():
    assert rdp_tolerance(10) == 8.0 and rdp_tolerance(400) == 60.0

def test_station_nodes_survive_simplification():
    assert PTS[3] in rdp(PTS, 60.0, LAT0, pinned={PTS[3]})

def test_an_unroutable_pair_is_reported_not_silently_straightened(capsys):
    route_segment_reporting(G_DISCONNECTED, 'A', 'Z')
    assert 'A>Z' in capsys.readouterr().out
```

- [ ] **Step 2: Run them to verify they fail**

- [ ] **Step 3: Implement**

The island graph is built by the existing `build_graph`, with its stitching and hole bridging. Segments route consecutive printed stations — passes included, since a pass is still a point the train runs through. The existing detour guard stays and reports per segment. Every straightened pair is listed with its gap.

- [ ] **Step 4: Run the tests, then the build**

Run: `python -m pytest -q && python scripts/build_shapes.py`
Expected: the segment count and every straightened pair printed.

- [ ] **Step 5: Commit**

---

### Task 9: GTFS from the timetables

**Files:**
- Modify: `scripts/build_gtfs.py`, `scripts/validate.py`
- Test: `tests/test_gtfs.py`

**Interfaces:**
- Produces: `route_id` of `KA_<CATEGORY>_<SERVICE>`; `stop_times.txt` with every row of every run — a pass gets `pickup_type=1` and `drop_off_type=1`, an estimated time `timepoint=0`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_pass_cannot_be_boarded_or_left():
    row = stop_time_for(PASS_ROW)
    assert (row['pickup_type'], row['drop_off_type']) == ('1', '1')

def test_an_estimated_time_is_not_a_timepoint():
    assert stop_time_for(UNTIMED_STOP)['timepoint'] == '0'

def test_a_time_past_midnight_is_written_past_24_00():
    assert stop_time_for(AFTER_MIDNIGHT)['arrival_time'].startswith('24:')

def test_national_route_ids_are_distinct_per_service():
    assert route_id('Argo', 'ARGO SEMERU') != route_id('Argo', 'BIMA')

def test_validate_accepts_coordinates_across_the_island():
    assert validate_coords([('MER', -5.93, 106.0), ('KTG', -8.14, 114.40)]) == []
```

- [ ] **Step 2: Run them to verify they fail**

- [ ] **Step 3: Implement**

`validate.py`'s coordinate check widens from East Java to the island bbox in `data/regions.json`; its speed check now runs over printed times between consecutive timed rows, which is a much sharper test than revision 1's end-to-end averages.

- [ ] **Step 4: Run the tests, then the build**

Run: `python -m pytest -q && python scripts/build_gtfs.py && python scripts/validate.py`
Expected: 48,685 `stop_times` rows; validate clean.

- [ ] **Step 5: Commit**

---

### Task 10: Bundle

**Files:**
- Modify: `scripts/make_bundle.py`
- Test: `tests/test_bundle.py`

**Interfaces:**
- Produces, in `data/bundle.json`:
  - `segments: {key: {c, d}}`.
  - per trip: `g` (segment keys), `c` (category), `o` (operator), `f` (true when FAKULTATIF), `x` (true when any segment was straightened), and `k`, keyframes `[arr, dep, km, code, flags]`. `flags` is a bit field: `1` = pass, `2` = estimated time.
  - `regions` holding only the three published regions; the `java` pseudo-region never reaches the bundle.

- [ ] **Step 1: Write the failing tests**

```python
def test_every_printed_time_reaches_the_bundle_unchanged():
    for run in RUNS:
        printed = [(r.arr, r.dep) for r in run.rows if r.kind in PRINTED]
        frames = [(k[0], k[1]) for k in trip(run.no)['k'] if not k[4] & 2]
        assert frames == printed

def test_a_pass_is_flagged_as_one():
    assert trip('1')['k'][1][4] & 1

# Review Focus 3
def test_keyframe_distances_never_decrease_even_through_a_repeated_station():
    for t in BUNDLE['trips']:
        ds = [k[2] for k in t['k']]
        assert ds == sorted(ds)

def test_the_island_pseudo_region_does_not_reach_the_picker():
    assert [r['id'] for r in BUNDLE['regions']] == ['surabaya', 'bandung', 'yogyakarta']

def test_the_bundle_gzips_under_the_target():
    assert len(gzip.compress(BUNDLE_BYTES)) < 1_500_000
```

- [ ] **Step 2: Run them to verify they fail**

- [ ] **Step 3: Implement**

Keyframe distances come from projecting each station onto its trip's assembled shape, using the existing `proj()` and its first-pass rule — the comment at `make_bundle.py` explains why that rule makes repeated visits work. **Measure the gzipped size before optimising anything.** If it is over the target, drop untimed passes first: they carry no time, and the geometry comes from the segments.

- [ ] **Step 4: Run the tests, then the build**

Run: `python -m pytest -q && python scripts/make_bundle.py`
Expected: about 2,089 trips; raw and gzipped sizes printed.

- [ ] **Step 5: Commit**

---

### Task 11: The national distance check

**Files:**
- Create: `scripts/verify_distances.py`
- Modify: `scripts/check-geometry.mjs`, `package.json`, `.github/workflows/deploy.yml`
- Test: `tests/test_verify.py`

**Interfaces:**
- Consumes: `build_topology` and `route_relasi` from Task 3, the junction split and the erratum.
- Produces: `run_distance(graph, run) -> float` — the table distance along a run's printed sequence, computed as `route_relasi(graph, first, last, via=<every interior station the tables know>)`, where `first` and `last` are the **first and last stations the tables know**, which is not always the run's own ends. Pangrango (KA 265-272) now ends at Bogor Paledang, `BOP`, which no distance table includes; 76 timetable codes are absent from the tables altogether. Where a run's own end is unknown to the tables, measure from the nearest known station, report the unmeasured stretch by name, and compare against the register's km with that stretch in mind — never fail the gate on a station the tables simply do not print, and never silently drop the run from the check.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_run_s_table_distance_follows_its_printed_stations():
    assert run_distance(GRAPH, ANGGREK_KA_1) == pytest.approx(720.109, rel=0.03)   # register km

def test_a_station_the_tables_skip_is_passed_over_not_failed_on():
    assert run_distance(GRAPH, RUN_THROUGH_GADOBANGKONG) > 0

def test_the_gate_fails_on_any_run_more_than_ten_percent_out():
    assert gate([0.01, 0.02, 0.11]) is False

def test_the_gate_has_no_exceptions_list():
    assert not hasattr(verify_distances, 'EXCEPTIONS')
```

- [ ] **Step 2: Run them to verify they fail**

- [ ] **Step 3: Implement**

`npm run verify:gapeka` now runs `verify_distances.py`, which fails the build on any run more than 10% from its register km and reports every run over 3%. It also checks every printed time against the bundle and every segment's routed length against the table distance where one exists. `check-geometry.mjs` walks `segments`. The deploy workflow's two verification steps keep their names.

- [ ] **Step 4: Run both checks**

Run: `npm run verify:geometry && npm run verify:gapeka`
Expected: both pass; the national report printed.

- [ ] **Step 5: Commit**

---

### Task 12: Runtime — stops, passes and easing

**Files:**
- Create: `vitest.config.ts`, `src/data/__tests__/bundle.test.ts`, `src/sim/__tests__/trains.test.ts`
- Modify: `src/data/bundle.ts`, `src/sim/trains.ts`, `package.json` (`vitest`, `"test": "vitest run"`)

**Interfaces:**
- Produces:
  - `Keyframe = [arr, dep, km, code, flags]`; `isPass(k)`, `isEstimated(k)`.
  - `assembleShape(bundle, trip) -> BundleShape`, sharing segment arrays by reference.
  - `EASE_KM = 2` in `trains.ts`, applied only where a leg starts or ends at a stop.

- [ ] **Step 1: Write the failing tests**

```ts
// Review Focus 4
it('keeps passes off the departures board', () => {
  expect(buildNetwork(BUNDLE).callsByStop.get('TES')).toBeUndefined();   // KA 1 runs through Tandes
});

it('does not brake at a pass', () => {
  const v1 = speedAt(ANGGREK, 'before TES'), v2 = speedAt(ANGGREK, 'at TES');
  expect(Math.abs(v1 - v2) / v1).toBeLessThan(0.02);
});

it('still brakes into a stop', () => {
  expect(speedAt(KA_2107, 'arriving BPR')).toBeLessThan(speedAt(KA_2107, 'between stops'));
});

it('hits every keyframe time exactly', () => {
  for (const [arr, , km] of TRIP.k) expect(trainAt(TRIP, SHAPE, arr)!.distance).toBeCloseTo(km, 3);
});

it('shares segment coordinates between trips rather than copying', () => {
  expect(assembleShape(BUNDLE, TRIP_1).c[0]).toBe(assembleShape(BUNDLE, TRIP_2).c[0]);
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npx vitest run`

- [ ] **Step 3: Implement**

`callsByStop` indexes stop kinds only. Easing accelerates away from a stop and brakes into one over `min(EASE_KM, legLength / 2)`, at constant speed otherwise, so every keyframe's time is still hit exactly. `activeTrains()` gains a `[firstDeparture, lastArrival]` index.

- [ ] **Step 4: Run the tests**

Run: `npx vitest run && npm run check`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

---

### Task 13: Map layers

**Files:**
- Create: `src/map/__tests__/trackLayer.test.ts`, `src/map/__tests__/stationLayer.test.ts`
- Modify: `src/map/trackLayer.ts`, `src/map/stationLayer.ts`

**Interfaces:**
- Produces: `CATEGORY_PRIORITY`, `segmentColor(categories, routes)` (freight-only segments `#8a9099`), `visibleSegments(bundle, visible)`, `stationRank(code, corridors)`.

- [ ] **Step 1: Write the failing tests**

```ts
it('gives a shared segment the highest-priority category colour', () => {
  expect(segmentColor(new Set(['Barang', 'Commuter Line']), ROUTES)).toBe(COMMUTER_COLOR);
});
it('draws freight-only track in neutral grey', () => {
  expect(segmentColor(new Set(['Barang']), ROUTES)).toBe('#8a9099');
});
it('hides a segment only when no visible run uses it', () => {
  expect(visibleSegments(BUNDLE, new Set())).toHaveLength(0);
});
it('ranks a station by how many corridors touch it', () => {
  expect(stationRank('SMT', CORRIDORS)).toBe('junction');
});
```

- [ ] **Step 2: Run them to verify they fail**

- [ ] **Step 3: Implement**

One feature per segment, carrying the categories of the visible runs on it. A selected single region or line keeps its own colour on its segments, so today's regional views look exactly as they do now. The island view draws only termini and junctions below `minzoom: 9`.

- [ ] **Step 4: Run the tests**

Run: `npx vitest run && npm run check`

- [ ] **Step 5: Commit**

---

### Task 14: Panels and wiring

**Files:**
- Modify: `src/ui/linePanel.ts`, `src/ui/trainPanel.ts`, `src/main.ts`, `src/styles.css`

- [ ] **Step 1: Write the failing tests**

```ts
it('leaves fakultatif runs out of the default visible set', () => {
  expect(defaultVisible(NET).has(FAKULTATIF_ROUTE)).toBe(false);
});
it('lists only stops in the route diagram', () => {
  expect(renderTrainPanel(NET, ANGGREK_STATE, 0, false)).not.toContain('Tandes');
});
it('marks an estimated time as estimated', () => {
  expect(renderTrainPanel(NET, KRL_STATE, 0, false)).toContain('≈');
});
```

- [ ] **Step 2: Run them to verify they fail**

- [ ] **Step 3: Implement**

`initLinePanel` groups by category — Commuter, Intercity, Local, Airport, Freight — each collapsible, keeping the dot-name-count chip and `--chip`. The region picker keeps **All Java** plus the three regions. `trainPanel.ts` replaces the hard-coded `Commuter` badge with the run's category, draws an estimated time as `≈ 20:09` in the muted style, and explains the mark once. No new colours, radii or type styles.

- [ ] **Step 4: Run the tests**

Run: `npx vitest run && npm run check`

- [ ] **Step 5: Commit**

---

### Task 15: Documentation and live verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Rebuild from scratch**

```bash
python scripts/parse_gapeka.py && python scripts/build_stations.py && python scripts/build_shapes.py && python scripts/build_gtfs.py && python scripts/validate.py && python scripts/make_bundle.py
```

Expected: 2,089 trips, 466 stations, no straightened segment unreported.

- [ ] **Step 2: Run every check**

Run: `python -m pytest -q && npx vitest run && npm run check && npm run verify:geometry && npm run verify:gapeka`

- [ ] **Step 3: Verify in the browser**

Start the `jtv-dev` preview and screenshot: the All Java view with trains across the island; an Argo selected, showing only its stops and running straight through the stations it passes; a Commuter Line train with an estimated time marked `≈`; the freight toggle; a regional view unchanged from today. Check the console and the bundle's transfer size.

- [ ] **Step 4: Rewrite the README**

The opening claim and region table become every train on Java from GAPEKA 2026, valid from 1 December 2026. The data-source table names the 2026 PDF, where it came from, and the committed text cache. Record as known gaps: the inferred readings of `Ls` and `Berh Sb`; estimated times and how they are marked; the four empty-stock moves not drawn; the Wates/Kedundang erratum, with its evidence. Remove the three regional PDFs and the 2025 register from the data-source table, saying they were superseded.

- [ ] **Step 5: Commit**

---

## Self-Review

**Spec coverage.** Source and cache → 5; runs, kinds, times and estimates → 5; register, categories, banners, distance tables → 6; stations → 7; segments → 8; GTFS → 9; bundle and the pseudo-region → 10; distance verification and the no-exceptions gate → 11; stops, passes and easing → 12; track and station layers → 13; panels, FAKULTATIF, the `≈` mark → 14; README → 15. Retiring the 2025 outputs is Task 6's last step; retiring the build steps is Task 11's.

**Ordering.** Task 7 owns `route_between`, which Task 8 reuses, so stations can be placed by km post without waiting on the segment library.

**Review Focus coverage.** Contents lists, midnight, repeated stations and estimate bounds in Task 5; repeated stations again in 10; passes and easing in 12.

**Open items carried forward, not waived.** The banner reconciliation (Task 6) and the bundle's real size (Task 10) are both measured before anything is assumed.
