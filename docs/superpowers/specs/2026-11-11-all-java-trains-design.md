# Every train on Java

Design for extending the Indonesian Railway Visualizer from three KAI Commuter
networks to the whole of the Java railway network.

Status: design, awaiting approval. Revised once after a builder check; the
decisions that check forced are collected under "Decisions settled after
review".

## Intent

The app today animates 137 trips on 12 lines through 120 stations, across three
KAI Commuter networks (Surabaya, Bandung, Yogyakarta). The request is to animate
**every train running on Java island**: 1,775 trains on 142 services.

The UI is finished and liked. This is a data-layer project: the shell, the map,
the panels, the clock and the colour system all stay. What changes is how much
railway they are pointed at.

### Why it is possible now

`Train Timetables/GAPEKA Jadwal Kereta.pdf` — Lampiran II of DJKA decree
KP-DJKA 224/2024 — is already in the repository, used only by
`scripts/validate_gapeka.py` as a cross-check. It is in fact the complete
national register, and it parses:

- **1,775 trains** on **142 services**, each with number, service name,
  REGULER/FAKULTATIF class, relasi, operator, distance, departure and arrival.
  By operator: 1,293 PT. KCI, 432 PT. KAI, 50 PT. Railink.
- **316 distinct relasi**, of which 78 name an intermediate point
  (`GMR - SBI - JR`, `KTG - SBI - SMT - PSE`), using 87 distinct origin and
  destination codes, or 89 counting via points.
- A back section, `JARAK ANTAR STASIUN`, which parses into **37 corridor chains
  covering 396 stations with official km posts** — 391 in the matrices and 5 more
  reached only by
  the short branches printed as inline pairs (`CTA-NMO 13,267`), overlapping by
  six. All 37 self-validate on the head-distance and monotonic-km checks; 35 on
  row sequence, the two exceptions being chains with documented holes where the
  page prints part of a matrix as vertical text.

That last section is the find. It gives authoritative topology *and* official
distances for the entire island — better data than the three current regions
have, which derive distance from OSM-routed geometry alone.

### The limit, stated plainly

The register carries **end-to-end times only**: departure from origin, arrival at
destination. It has no intermediate station times.

So for the ~1,640 trains that have no published per-station timetable in the
repo, a train can be placed on the correct track, at the correct km post, leaving
and arriving at the correct minute — but its intermediate stops are *interpolated
from distance*, not published. The user chose this knowingly and wants all 1,775
trains on that basis.

This project's README is careful about what the map claims, and that care has to
extend here: every trip carries its timing provenance, and the UI says which it
is.

## Goals

1. Every train in the GAPEKA 2025 register animated on the map — 1,764 of the
   1,775, freight included. The missing 11 are the register's Yogyakarta rows,
   suppressed as duplicates of better data; see decision 2.
2. Every train follows real OpenStreetMap rail alignment, as today. No
   straight-line cheating between distant stations.
3. Distances agree with the register's official km, within the existing tolerance.
4. The existing three regions keep their published calling times, unchanged and
   still passing `verify:gapeka`.
5. The bundle stays small enough to ship to a browser — target under 1.5 MB
   **over the wire** (gzipped, as GitHub Pages serves it). See decision 4.
6. Every trip states where its timing came from, visibly.

## Non-goals

- Realtime positions. No feed exists; this stays scheduled data.
- Per-station times for intercity trains. Not in the register, and not invented
  from another source in this project.
- Sumatra, Madura or any network off Java.
- A UI redesign. The shell, colour system and typography are done.

## Anti-goals

Things that would make this a failure even if it technically ran:

- **A map that implies precision it does not have.** An interpolated stop
  presented as a published one is worse than no stop at all.
- **Trains cutting across country.** If the island-wide graph cannot route a
  leg, that must be reported loudly, not quietly straightened.
- **Losing the three good regions.** Their published times are the best data
  in the repo and must not be flattened into register-grade timing.
- **A bundle so large the page takes ten seconds to start.**

## Constraints

- No API keys, no paid services, no accounts. Everything stays free.
- Overpass is a donated service: the island-wide fetch is cached under
  `data/osm/`, refetched only with `--force`.
- The Python pipeline stays the single source of truth; the app loads one
  `bundle.json`.
- The trip model in `src/sim/trains.ts` is keyframes of
  `[arrival, departure, km, stop]` eased with smoothstep. Its *shape* is kept;
  its easing rule changes once, for the reason in decision 1.
- `dist/` and `public/data/bundle.json` are generated, not committed.

## Approaches considered

### A. Register-first, one national network — chosen

Promote the register to primary source. Parse trains and corridor tables into a
national topology. Build one Java-wide OSM rail graph, resolve all 396 station
codes via `railway:ref`, route each of the 316 relasi over it. Derive each
train's station chain from the register's corridor graph, with its official km
posts. The three commuter PDFs override register timing for their 137 trips.

**The register's km is the route selector, not merely a check.** The first draft
of this design assumed the 78 via-point relasi would disambiguate competing
routes — north coast versus south — for free. They do not. `SGU - PSE` and
`SGU - GMR` print no via point at all, yet the register's distance says they take
the southern line, 96 km longer than the shortest path. Measured over the
finished topology, plain shortest-path routing puts only 256 of 316 relasi
within the repo's existing tolerance, with 30 over 10%: a clear failure of the
verification budget.

So a relasi is routed by enumerating simple paths in increasing length and
taking the one whose total best matches the km the register prints for trains on
that relasi. The register states the distance, and the path through the national
graph with that length is the route the train takes. It recovers the southern
`SGU - PSE` at exactly the printed 819.682 km — as the **90th** simple path, and
`SGU - GMR` at 821.079 as the 125th — which is why shortest-path alone could
never have found them. (An earlier draft of this paragraph said 824.9 km against
"~825" as the 58th path. Those figures came from a probe run against a target
distance that was guessed rather than read from the register.)

**Length-matching only works on an unbiased graph.** It picks whichever path is
closest to the printed km, so any systematic error in an edge weight is
something it will route around: the selector finds a detour whose extra length
happens to cancel the error. The first build kept the *minimum* where two
corridors disagreed on an edge, and Brumbung is printed 0.880 km apart on the
north-coast and Gundih lines. That left every Jakarta–Surabaya route on the
graph 0.88 km short, and 16 relasi duly took a needless loop through the
Surabaya Pasarturi triangle to make up the difference. They were within
tolerance — and wrong. A junction printed at different km on different lines is
therefore modelled as one node per line, joined by the offset the register
prints, rather than collapsed to a single number. The register's distances then
need no correction for the selector to choose routes rather than numbers.

Trades off: a substantial pipeline addition, one large OSM fetch, and path
enumeration rather than a single Dijkstra per relasi.

Gains: official distances, correct topology, cross-region trains work naturally,
and the register's own km both selects and then verifies every routed shape.

### B. Region-by-region extension

Keep the current per-region architecture; add Jakarta, Semarang, Cirebon and
Malang as new regions with their own bboxes, OSM caches and graphs.

Rejected. `build_shapes.py` builds one graph per region deliberately, so that
component-bridging cannot connect networks hundreds of kilometres apart. Every
intercity train crosses regions, belongs to none, and would need its shape
stitched across graphs that exist in order to stay separate. The architecture's
central assumption is exactly what the new trains violate.

### C. Schematic interpolation

Skip OSM routing for new trains; draw each one along its register chain by
interpolating between station coordinates.

Rejected. Cheap and fast, but it discards the project's defining property —
trains following the real curve of the line — and would look visibly wrong
against the three existing regions on the same map.

## Design

### Data pipeline

Two new scripts, three extended.

**`scripts/parse_gapeka.py`** (new) — reads the register once, writes:

- `data/gapeka/trains.json` — 1,775 records:
  `{no, service, class, category, relasi, via[], operator, km, dep, arr}`.
  Category from the register's own section order (Argo, Eksekutif, Eksekutif
  Campuran, Ekonomi Jarak Jauh, Ekonomi Lokal, Bandara, Commuter Line, Barang).
- `data/gapeka/network.json` — corridors as
  `{name, stations: [{code, km}]}`, including the short branches printed as
  inline pairs, plus a station code index.

Parsing notes that must survive into the code, corrected against the data after
Task 2 was built:

- On narrow pages the header code row arrives interleaved
  (`O/D C 1KP C 2BR PW 3K ...`), so the ordered station list is recovered from
  the **matrix row labels**, not the header. The header is the only line
  `extract_text()` truncates; the matrix rows are complete, every one carrying
  its full *n*−1 values.
- Cumulative km come from the **first numeric value of each row** — row *i*'s
  distance to station 1 — because it is the one anchor every row carries
  regardless of what the header did. Row 1's first value is d(1,2) and
  cross-checks the chain head; that holds exactly on all 37 chains.
- A numeric token **without a comma is rejected**. This is load-bearing, not
  defensive: pages 55 and 58 print a stretch of matrix as vertical text, which
  extracts as wreckage (`LJ BR GL 98 76 25 ,, …`), and without the guard `GL 98
  76` reads as a station at 76 km.
- Side-by-side tables are split on the matrix's **own symmetry** — row *i*'s
  first value is d(i,1), which row 1 also prints — not on a row-index reset,
  which would cut genuine side-by-side tables apart.
- Some cells on page 63 print to one or two decimals where the same distance
  appears elsewhere with three, so symmetry must be compared at the precision
  the register printed, not exactly.

**`scripts/build_java_network.py`** (new) — the national graph:

- Nodes are register station codes, edges consecutive pairs on a corridor with
  the register's km as weight.
- For each of the 316 relasi, shortest path origin to destination, forced through
  any via points, then compared against the register's km for trains on that
  relasi. A path whose length disagrees beyond tolerance is reported, not
  silently accepted — this is how a wrong route (north coast instead of south)
  gets caught.
- Output: station chain plus official km post per relasi.

**`scripts/fetch_osm.py`** (extended) — a `java` pseudo-region covering the
island, bbox `[-9.0, 105.0, -5.8, 114.7]`, fetched as ten two-degree tiles and
merged on OSM way id into one `rail.geojson`. The first draft guessed 15-25 MB
and planned to gitignore it; measured, the island is **3.0 MB, 8,783 ways**, so it
is committed like the three regional caches already are. That also keeps every
build independent of Overpass being up, which during this work it often was not.
Verified complete by matching the regional caches way-for-way (Bandung 2,614
against 2,604, Surabaya 1,764 against 1,745) and by finding track at 27
stations spread across every main line.

**`scripts/build_shapes.py`** (extended) — the key change is the **segment
library**. Instead of one polyline per distinct station chain, route and store
one polyline per *consecutive station pair*, keyed `A>B`. A trip is then an
ordered list of segment keys. Roughly 450 segments serve all 1,775 trains; the
Jakarta-Surabaya north coast corridor is stored once, not once per train on it.

The existing graph machinery (endpoint stitching, hole bridging, station
snapping, pinned RDP) carries over, with two adjustments: `nx.shortest_path`
becomes A* with a haversine heuristic, because a single island graph is far
larger than a regional one; and RDP tolerance scales with segment length, so a
700 km run is not stored at 8 m precision no one can see.

**`scripts/make_bundle.py`** (extended) — assembles segments per trip, computes
keyframes, and adds per-trip fields: `category`, `operator`, `class`
(reguler/fakultatif), and `t` for timing provenance: `"published"` for the 137
trips with real calling times, `"endpoint"` for register-timed trips.

For an `endpoint` trip, keyframes are placed **only where a time is actually
published** — origin, destination, and any via point the relasi names. The
chain's intermediate stations anchor the *geometry* and the official-km check;
they are not keyframes and never become calls. See decision 1.

**Verification** — `verify:gapeka` keeps its current job for the three published
regions and gains a national pass: every routed relasi length against the
register's km, every train accounted for. `verify:geometry` runs over the
segment library.

### Runtime

`src/data/bundle.ts` assembles each trip's distance-indexed polyline from its
segment list at load time, so `BundleShape` keeps its current `{c, d}` shape and
the simulation keeps reading one array per trip. Segment coordinate arrays are
shared by reference between trips, not copied, so the Jakarta–Surabaya trunk
exists once in memory however many trains run on it.

`src/sim/trains.ts` changes in exactly one way: easing becomes
**distance-bounded** rather than a fraction of the leg (decision 1).

`activeTrains()` currently walks all trips twice per frame. At 1,775 trips that
is 3,550 evaluations per frame — survivable, but the trip list gains a cheap
precomputed `[firstDeparture, lastArrival]` bucket index so a frame only
considers trips plausibly running.

The three.js `InstancedMesh` already draws the fleet in one call and needs only
a larger instance budget.

### UI

The smallest change that makes 1,775 trains navigable. No new visual language.

- The region switcher's existing **All Java** entry becomes the default and the
  real view.
- Below it, **category groups** replace the per-region line chips: Commuter
  (KRL Jabodetabek, and the three published regions), Intercity, Local, Airport,
  Freight. Each group collapses, and chips inside it carry the existing colour
  dot and trip count.
- The three published regions keep their own entries in the switcher, so today's
  view of Surabaya or Bandung is still one click away.
- The train detail card gains one line of provenance: published calling times,
  or timed end to end from the register.

Colours: the register's categories get a palette in the existing OKLCH system,
each service within a category taking a step. Freight stays desaturated so it
reads as background traffic.

**The track layer** (`src/map/trackLayer.ts`) today emits one feature per shape,
coloured by the single route using it and filtered on `['in', ['get','route'],
...]`. Neither survives shared segments, so it is rebuilt to draw the **segment
library** itself: one feature per segment, carrying the set of categories whose
visible routes use it. A segment is drawn when that set is non-empty, and takes
the colour of the highest-priority category in it (Commuter, then Intercity,
then Local, then Airport), with freight-only segments in the neutral rail grey.
When a single region or line is selected, its own colour wins on its segments —
which is exactly today's behaviour, preserved for the views that already exist.

**Stations in the All Java view.** `setVisibleStationRegions` filters by region
id and the 396 register stations belong to none. Stations gain a rank
(terminus / junction / other, derived from how many corridors touch them), and
the island view draws only termini and junctions until the camera is close
enough for the rest to be legible. `main.ts` keeps opening on a region, for the
reason already in the code: at Java-wide zoom individual trains are specks.

## Decisions settled after review

A builder check on the first draft of this document found seven gaps. Six are
settled here as the author's calls; the seventh was the user's and their answer
is recorded in decision 2.

1. **An interpolated pass-through is not a call.** The first draft put a
   keyframe at every station on a register train's chain. That cannot stand: the
   simulation eases every keyframe-to-keyframe leg with `smoothstep`, so an Argo
   would brake to walking pace at fifty stations across Java; `buildNetwork()`
   indexes every keyframe into `callsByStop`, so the departures board would
   announce expresses as calling at stations they pass at line speed; and
   `trainPanel.ts` would draw a fifty-row route diagram of stops that do not
   exist. That is this document's own first anti-goal, reached by accident.

   So keyframes exist only where a time is published. For a register train that
   means origin, destination and any named via point. The chain's other stations
   anchor geometry and the km check, nothing more.

   That leaves one eased leg across a 700 km run, which `smoothstep` would turn
   into a ten-hour crawl-sprint-crawl. So easing changes from a fraction of the
   leg to a **bounded distance** — accelerate and brake over roughly 2 km
   regardless of leg length. This is a better model for the existing commuter
   trains too, and it is the only change the simulation needs.

2. **Yogyakarta: published times win.** Its PDF predates GAPEKA 2025 and
   numbers the same services 661–684 and 551–558 where the register says
   701–733 and 501–512, so the two sources describe the same trains at
   different minutes under different numbers and cannot both ship without
   drawing each service twice. The user chose the published times: the 32
   trips with real per-station calling times stay, and the register's
   Yogyakarta rows are suppressed as duplicates.

   The total therefore lands at **1,764 trains**, not 1,775, and that number
   is what the README should claim. Suppression is keyed on service name plus
   region, not train number, because the numbers are precisely what disagree.
   Surabaya and Bandung are unaffected: their PDFs are GAPEKA-2025-numbered,
   so the register matches them by number and the override is exact.

   The same shape of problem exists in miniature for paired numbers — the
   register splits `444-445` into two rows where the timetable prints one
   through run — and `validate_gapeka.py` already special-cases it. That
   handling is kept and extended to the national pass.

3. **Verification fails on a budget, not on noise.** `validate_gapeka.py` exits
   1 on any single disagreement, and the deploy workflow runs it before the
   build. Across 316 relasi on one island graph with documented OSM holes, some
   length disagreements are certain, and zero tolerance would make this
   unlandable. So: the three published regions keep **zero tolerance**, exactly
   as today. The new national pass reports every disagreement and fails only
   above a budget — 2% of relasi, or any single relasi off by more than 10%.
   A relasi the graph cannot route at all ships with its straight-line leg, is
   counted in the report, and carries a flag in the bundle so the app can mark
   it. Shipping it silently is the anti-goal; shipping it marked is not.

4. **The 1.5 MB target is over the wire.** Today's bundle is 344 KB raw for
   2,015 keyframes and 9,476 shape points. Decision 1 is what makes the target
   reachable: the ~1,640 register trains carry 2–4 keyframes each rather than
   30–60, so trips grow to roughly 8–10k keyframes, not 60k. With the segment
   library in place the raw file should land near 1.5–2.5 MB and gzip to well
   under the target. No per-category lazy loading, and no bundle splitting.

5. **An unmatched station code is placed by its km post, not by hand.** The
   register prints codes with no names, so `build_stations.py`'s name fallback
   does not exist for the new stations, and OSM `railway:ref` coverage in the
   existing caches runs 85–95%. There is no hand-maintained table: a code that
   OSM cannot resolve is placed at **its official km along its corridor's
   routed polyline**, which the register gives exactly. The corridor geometry
   plus one number is a coordinate. Such stations are listed in the build
   report as OSM-unmatched, so they can be improved upstream, and they are
   excluded from the station layer's junction ranking.

6. **The register's trains flow through GTFS.** The feed is a published
   artefact the README advertises, and routing it around GTFS would mean two
   parallel input paths through `build_shapes.py` and `make_bundle.py` and a
   feed that no longer describes the map. `build_gtfs.py` and
   `build_stations.py` are therefore extended too. Decision 1 keeps the cost
   sane: `stop_times.txt` grows to roughly 10k rows, not 100k. `validate.py`
   needs its East Java bbox widened to the island and its `CL_<REGION>_<LINE>`
   route-id scheme generalised for national services.

7. **FAKULTATIF trains are off by default.** 75 of the 1,775 are scheduled
   paths that may not run. They get their own chip, off until asked for, which
   is consistent with how carefully the rest of the project states what it
   knows.

## What is left to the builder

- Exact tiling of the Overpass fetch, if the island in one query fails.
- Whether the segment library keys on code pairs alone or on pair plus corridor,
  should two corridors share a station pair with different alignments.
- Collapsed-by-default state per category group.
- Precise RDP tolerance curve against segment length.
- Whether `data/gapeka/*.json` is committed or generated; committed is suggested,
  as it is parsed from a PDF already in the repo and makes the pipeline
  inspectable without Python.
- The exact bounded-easing distance in decision 1 (2 km is a starting value, to
  be tuned by eye against the existing commuter runs).
- How corridor-touch counts map to the terminus / junction / other station rank.
- The A* heuristic constant, instance capacity, and the precise OKLCH steps per
  category.
