# Every train on Java

Design for extending the Indonesian Railway Visualizer from three KAI Commuter
networks to the whole of the Java railway network.

Status: **revision 2, awaiting approval.** Revision 1 was built on the GAPEKA
2025 register, which gives each train's departure and arrival but nothing in
between. Revision 2 switches the source to **GAPEKA 2026**, which prints a
station-by-station timetable for every train. The user chose the switch on
2026-11-25. What revision 1 decided, and what overturned each decision, is under
"History" at the end.

## Intent

The app today animates 137 trips on 12 lines through 120 stations, across three
KAI Commuter networks (Surabaya, Bandung, Yogyakarta). The request is to animate
**every train running on Java island**.

The UI is finished and liked. This is a data-layer project: the shell, the map,
the panels, the clock and the colour system all stay. What changes is how much
railway they are pointed at, and how much of it the map can state as fact.

### The source

`KP DJKA 116 TAHUN 2026 GAPEKA JAWA.pdf` is the 2026 *Grafik Perjalanan Kereta
Api* for Java: decree KP-DJKA 116/2026 of the Directorate General of Railways.
Its timetables are headed `Berlaku Mulai Tanggal 01 Desember 2026` — **valid
from 1 December 2026**, so it is the edition that will actually run, and it
supersedes the 2025 register.

It is 1,887 pages and 61 MB. The first five pages are a scanned covering letter;
everything after has a real text layer, and a full text extraction takes about
eighteen minutes. Its sections:

| Pages (0-based) | Content | Used |
| --- | --- | --- |
| 6-51 | The train-path graphs themselves, one per corridor and time window | No |
| 52-668 | **Timetables, intercity**: one block per train, headed `KA 1 (Anggrek) Relasi SBI - GMR` | Yes |
| 669-1671 | **Timetables, commuter, local, airport and freight**, headed `KA 2107 (Commuter Line Tangerang) Lintas Pelayanan TNG - DU` | Yes |
| 1672-1827 | Rolling stock and train formations | No |
| ~1828-1874 | **The register**: every train's number, class, service, relasi, operator, distance and times, under `KELAS KERETA API` section banners | Yes |
| 1875-1886 | **Distance tables** (`JARAK ANTAR STASIUN`), the same format as 2025 | Yes |

Each timetable section opens with a contents list that repeats every train's
header line with no rows beneath it. Those entries are not timetables and must
not be counted as trains.

### What the timetables give

A timetable is one row per station, in the order the train runs:

```
KA 1 (Anggrek) Relasi SBI - GMR
No. Stasiun dan Perhentian  Kecepatan Maksimum  Datang  Berangkat  Keterangan
1   Surabaya Pasarturi (SBI)  115   -          08:15:00
2   Tandes (TES)              115   Ls         08:21:00
...
```

Measured over the whole document:

- **2,089 timetabled runs, 48,554 station rows.**
- They cover **1,805 of the register's 1,809 trains.** The four without a
  timetable are `R951`-`R954`, empty-stock service movements (*Barang Dinas*),
  which no passenger rides and no shipper books.
- **464 station codes, every one printed with its full name.** That includes the
  minor halts the distance tables skip, such as Gadobangkong.
- A paired register number is **two consecutive legs**, each with its own
  timetable: register row `32-33` is KA 32 Gambir→Yogyakarta and KA 33 onward
  from Yogyakarta. The unit the map animates is therefore the timetabled run.

Each row is one of six kinds, distinguished by what fills the arrival,
departure and remarks columns:

| Kind | Printed as | Rows | Meaning |
| --- | --- | --- | --- |
| Origin | `- T` | 2,064 | Departs, no arrival |
| Destination | `T -` | 1,929 | Arrives, no departure |
| Timed stop | `T T` | 13,108 | Arrives and departs at printed times |
| Timed pass | `Ls T` | 18,227 | Runs through without stopping, at one printed time |
| Untimed pass | `Ls -` | 3,412 | Runs through, no time printed |
| Untimed stop | `Berh Sb` | 9,674 | No time printed; read as a stop (below) |

`Ls` carries one time where a stop carries two, which is what a train passing
straight through has. `Berh Sb` appears at every station on commuter lines,
where every train stops, and `Berh` is almost certainly *berhenti*, "stops". The
document has **no legend** for either. These readings are inferences from
structure, and the pipeline's documentation must say so.

Some rows carry an operational note after the times, such as
`x ka 455 (ka 455 x)` for a crossing or `= ka 4 (ka 4 //)` for an overtake.
They do not affect where a train is, and are ignored.

### The limit, stated plainly

Revision 1 had to interpolate times for most of the island. Revision 2 does
not: **every printed time is a fact**, and 35,328 rows (timed stops, timed
passes, origins and destinations) have one, plus about 140 timed rows carrying
an operational note.

What is still estimated is the 13,086 untimed rows (`Ls -` and `Berh Sb`). Their
times are interpolated by distance between the timed rows on either side. That
is honest only if the map says so, so an estimated time is always marked as one.

## Goals

1. **Every train in GAPEKA 2026 animated**: 2,089 timetabled runs, covering
   1,805 of the register's 1,809 trains, freight included. The four empty-stock
   movements are not drawn.
2. Every train follows real OpenStreetMap rail alignment, as today. No
   straight-line cheating between distant stations.
3. **Every printed time is hit exactly**, at every station that has one.
4. A train **passing** a station is never shown as calling there: not on the
   departures board, not in the route diagram, not by braking.
5. Distances agree with the register's official km, within tolerance.
6. The bundle stays under **1.5 MB over the wire** (gzipped, as GitHub Pages
   serves it).

## Non-goals

- Realtime positions. No feed exists; this stays scheduled data.
- The graph pages (6-51) and the rolling-stock sections. The timetables carry
  everything the map needs.
- Sumatra, Madura or any network off Java.
- A UI redesign. The shell, colour system and typography are done.

## Anti-goals

- **An estimated time presented as a printed one.** A stop with a guessed time
  shown as fact is worse than a stop with no time.
- **A pass presented as a stop.** An express does not call at the stations it
  runs through.
- **Trains cutting across country.** If the island graph cannot route a leg,
  that is reported loudly, not quietly straightened.
- **A bundle so large the page takes ten seconds to start.**

## Constraints

- No API keys, no paid services, no accounts. Everything stays free.
- Overpass is a donated service: the island caches under `data/osm/java/` are
  committed, and refetched only with `--force`.
- The Python pipeline stays the single source of truth; the app loads one
  `bundle.json`.
- **The 61 MB PDF is not committed.** Git keeps every version of a binary
  forever, and 61 MB is past GitHub's warning threshold. What is committed is
  the extracted page text the parser reads, plus the word coordinates of the
  twelve distance-table pages, which the vertical-text recovery needs. Rebuilding
  that cache from the PDF is a documented manual step. (The 2025 PDF, already in
  the repository, stays where it is.)
- `dist/` and `public/data/bundle.json` stay generated, never committed.

## Approaches considered

### A. Timetable-first, on one national network — chosen

Parse every timetable into its station sequence, times and row kinds. **The
printed sequence is the route**: no route has to be inferred. Route each
consecutive pair of stations over one island-wide OSM rail graph, store each
pair's geometry once in a segment library, and place every station by OSM
`railway:ref`, then by its printed name, then by its km post. The distance tables
and the register are kept, not as sources of times, but as independent checks:
the sum of table distances along a run's printed sequence must match the km the
register prints for that train.

### B. Register-first, routes inferred from length — revision 1's approach

Route each relasi by enumerating paths and taking the one whose length matches
the register's km, then interpolate times along it. It was built and it works:
on the corrected graph, 316 of 316 relasi land within tolerance and 290 match to
the metre. But it can only ever say where a train *probably* went, and it took
four rounds of fixes to stop it choosing numbers rather than routes. With the
route printed for every train, inferring it is strictly worse. Its machinery
survives as the distance check in A.

### C. Region-by-region, or schematic

Rejected in revision 1 and still rejected: every intercity train crosses
regions, and straight lines between stations discard the project's defining
property, trains following the real curve of the line.

## Design

### Data pipeline

**`scripts/parse_gapeka.py`** (extended) — reads the committed 2026 page cache
and writes:

- `data/gapeka/timetables.json` — one record per timetabled run:
  `{no, service, relasi, rows: [{code, name, max_kmh, arr, dep, kind}]}`. Both
  header forms (`Relasi` and `Lintas Pelayanan`) are read; contents-list entries
  are excluded by having no rows. Times stay as printed; `kind` is one of the six
  above. Paired legs are linked (`continues_as`, `continues_from`) when one run's
  destination is the next leg's origin under a paired register number.
- `data/gapeka/trains.json` — the register: number, class, category, service,
  relasi, operator, km, departure, arrival, REGULER or FAKULTATIF. Same columns
  as 2025, except that times drop their seconds (`08:15` for `08:15:00`).
  Categories come from the `KELAS KERETA API` banners. **One reconciliation is
  open**: in 2025 the banners tallied the register exactly, but the 2026 banners
  read so far claim 1,274 trains against 1,809 register rows. The commuter
  sections probably word their banners differently. This must be settled, not
  waived.
- `data/gapeka/network.json` — the distance tables, parsed by the existing
  `tables.py` unchanged: 36 corridors, all monotonic from 0. **The 2026 tables
  print the same Wates/Kedundang transposition as 2025**, so the existing named
  erratum applies; 24 trains in the 2026 timetables run Wojo, Kedundang, Wates,
  Sentolo, which confirms it a fourth way.

**Times and keyframes.** Every row becomes a keyframe carrying its kind:

- Timed rows keep their printed times exactly.
- Untimed rows get times interpolated by distance between the nearest timed rows
  either side, and carry an **`estimated`** flag. Distance comes from the trip's
  routed shape.
- A run crossing midnight carries times past 86,400 seconds, as the simulation
  already expects. Each timetable's printed times increase monotonically, so a
  time that goes backwards means the day has turned.

**`scripts/build_stations.py`** (extended) — 464 codes, all named. Three passes,
in order: OSM `railway:ref` from the island station cache (380 of 396
distance-table codes already match this way); then the **printed name** against
OSM names; then, for a station in the distance tables, its km post along its
corridor's routed polyline. A `railway:ref` that OSM puts on two stations is
resolved by proximity to the code's neighbours, never first-match-wins: `TGR` is
both Tegalluar Summarecon near Bandung and Temuguruh near Banyuwangi, 650 km
apart, and the timetables put it between `SGJ` and `KSL`. A station no pass can
place fails the build.

**`scripts/build_shapes.py`** (extended) — the **segment library**: one polyline
per consecutive printed station pair, keyed `A>B`, routed over the island OSM
graph and shared by every run that uses it. The existing machinery carries over
(endpoint stitching, hole bridging, station snapping, pinned RDP), with A* and a
haversine heuristic over the island graph and RDP tolerance that grows with
segment length.

**`scripts/build_gtfs.py`** (extended) — the feed now describes every run.
`stop_times.txt` gets every row: passes with `pickup_type=1` and
`drop_off_type=1` (no boarding or alighting), estimated rows with `timepoint=0`.
That is about 48,500 rows, against 2,015 today.

**`scripts/make_bundle.py`** (extended) — assembles segments per trip, writes
keyframes with their kind and `estimated` flag, and per-trip `category`,
`operator` and `class`. The `java` pseudo-region in `data/regions.json` exists
only for the OSM fetch and must not reach the app's region picker.

**Retired from the build**: the three regional timetable PDFs, `parse_timetable.py`,
and the 2025 register as a source. The 2026 timetables cover Surabaya, Bandung
and Yogyakarta under current numbering, so there is nothing for them to add. The
files stay in the repository; nothing reads them.

**Verification**, all failing the build when they fail:

- Every printed time appears unchanged in the bundle.
- Every run's keyframe times are non-decreasing.
- For every run, the table distance summed along its printed sequence, through
  the stations the tables know, agrees with the register's km for that train.
  The national gate fails on any run over 10% out, with no exceptions list.
- Every segment's routed OSM length agrees with the table distance between its
  ends, where the tables give one.
- `verify:geometry` runs over the segment library.

### Runtime

`src/data/bundle.ts` assembles each trip's distance-indexed polyline from its
segments at load, sharing coordinate arrays by reference, so `BundleShape` keeps
its `{c, d}` form.

Keyframes carry their kind, and the runtime uses it in exactly three places:

- **`callsByStop`** indexes only stop kinds (origin, destination, timed stop,
  untimed stop). Passes never reach the departures board.
- **The route diagram** in `trainPanel.ts` lists stops, and marks an estimated
  time as estimated.
- **Easing** in `trains.ts` happens only at stops: a train accelerates away from
  a stop and brakes into one over a bounded distance (about 2 km), and runs at
  constant speed through passes. Easing on every keyframe would brake an express
  at each of the stations it runs through.

`activeTrains()` gains a precomputed `[firstDeparture, lastArrival]` index so a
frame only evaluates runs that are plausibly out, since there are now about
2,089 of them. The `InstancedMesh` needs only a larger instance budget.

### UI

The smallest change that makes about 2,000 runs navigable. No new visual
language.

- **All Java** becomes the default and the real view. The three regional
  entries stay in the switcher, so today's view of Surabaya or Bandung is still
  one click away.
- **Category groups** replace the per-region chips — Commuter, Intercity,
  Local, Airport, Freight — each collapsible, with the existing colour dot and
  count per chip.
- **FAKULTATIF runs are off by default.** They are scheduled paths that may not
  run, so they get their own toggle.
- An estimated time is drawn with a mark, `≈ 20:09`, in the muted style. The
  detail card says once what the mark means.
- **The track layer** draws the segment library: one feature per segment,
  coloured by the highest-priority category whose visible runs use it (Commuter,
  then Intercity, Local, Airport), with freight-only track in the neutral rail
  grey. When a single region or line is selected, its own colour wins on its
  segments, which keeps today's views exactly as they are.
- **Stations in the All Java view** show only termini and junctions until the
  camera is close enough for the rest to be legible.

## What is left to the builder

- The exact bounded-easing distance (2 km is a starting value, tuned by eye).
- How corridor-touch counts map to the station rank.
- The RDP tolerance curve; the A* heuristic constant; instance capacity; the
  OKLCH steps per category; collapsed-by-default state per group.
- Whether a run's estimated rows are interpolated by distance alone or weighted
  by the printed maximum speeds, which the timetables also carry.

## History

What revision 1 decided, built on the 2025 register, and where each stands now.

- **Route selection by length match** (Tasks 3-4, committed). Replaced as the
  route source by the printed sequences. It survives as the distance check, and
  its corrections — one node per line at the three split junctions (Brumbung,
  Cirebon Prujakan, Kesugihan), and the Wates/Kedundang erratum — still apply,
  because the 2026 tables carry the same data.
- **Keyframes only at origin, destination and via points.** Overturned: every
  row is now a keyframe, and the kind flag does the job that omitting them used
  to.
- **Yogyakarta: published times win, 1,764 trains** (the user's decision).
  Moot: the 2026 timetables carry Yogyakarta under current numbers, with real
  times, so there are no duplicates to choose between.
- **Timing provenance per trip** (`published` or `endpoint`). Replaced by the
  per-row `estimated` flag, since every run is now published.
- **Bundle under 1.5 MB gzipped**: kept, but the budget changed. Revision 1
  expected 8-10k keyframes; revision 2 has about 48,500. That must be measured,
  not assumed. If it is over, untimed passes are the first to go, since they
  carry no time and the geometry comes from the segments anyway.
- **FAKULTATIF off by default**: kept.
- **Verification on a budget, not on noise**: replaced by a stricter gate. With
  routes printed, there is no routing noise left to budget for.
