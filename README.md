# Indonesian Railway Visualizer

A 3D map of Indonesian commuter trains, animated from the published timetable —
inspired by [Mini Tokyo 3D](https://minitokyo3d.com/), built on a stack that needs
no API keys and costs nothing to run.

The first network is **KAI Commuter Wilayah 8 (Surabaya)**: all six of its lines -
Dhoho, Penataran, Supas, Arjonegoro, Jenggala and Blorasura - with 64 stations and
47 daily trips, running over real OpenStreetMap rail alignments and checked against
the official GAPEKA 2025 register.

> **Scheduled positions, not live GPS.** No public realtime feed exists for this
> network, so trains are placed from the published timetable. Where a train is drawn
> is where it is *booked* to be.

## Running it

```bash
npm install
npm run dev
```

Then open the URL Vite prints. Other scripts:

```bash
npm run build            # typecheck + production build into dist/
npm run preview          # serve the production build
npm run verify:geometry  # sanity-check the animation bundle
```

`npm run dev` and `npm run build` both copy `data/bundle.json` into `public/data/`
first, so the Python pipeline's output stays the single source of truth.

## How it works

| Piece | What it does |
| --- | --- |
| `src/data/bundle.ts` | Loads `bundle.json`, indexes trips by route and calls by station, and snaps every station onto the track |
| `src/sim/clock.ts` | Time-of-day cursor in Asia/Jakarta: play/pause, 1x–300x, scrub, back to live |
| `src/sim/trains.ts` | Which trains are running and where, with eased acceleration between stops |
| `src/map/basemap.ts` | MapLibre GL JS on OpenFreeMap's keyless vector tiles, with the style's own 3D buildings |
| `src/map/trackLayer.ts` | Trip shapes as coloured lines, below the building extrusions |
| `src/map/trainLayer.ts` | A three.js custom layer: the whole fleet as one `InstancedMesh`, one draw call |
| `src/ui/` | Header clock, line chips, train detail card, station departures board |

Trains are positioned by distance along a shape, not by interpolating between station
coordinates, so they follow the real curve of the line. Between two stops the distance
is eased (`smoothstep`), so a train pulls away from a platform and brakes into the next
one while still hitting every published time exactly.

### Everything here is free

- **MapLibre GL JS** — BSD-3, no token
- **OpenFreeMap** (`tiles.openfreemap.org/styles/liberty`) — keyless, no registration, no request cap
- **three.js** — MIT
- **GitHub Pages** — free hosting, deployed by `.github/workflows/deploy.yml`

There is no account to create and no key to rotate anywhere in this project.

## Data

| Source | Used for | Licence |
| --- | --- | --- |
| KAI Commuter published timetable (`Train Timetables/*.pdf`) | Trips, times, calling patterns | Factual timetable data, republished for public information |
| OpenStreetMap | Rail alignments and station positions | ODbL - (c) OpenStreetMap contributors |

This project is **not affiliated with KAI, KAI Commuter or any operator**. Do not
use it to catch a train.

### Rebuilding the feed

```bash
pip install -r requirements.txt
python scripts/fetch_osm.py          # rail + stations from Overpass, cached in data/osm/
python scripts/parse_timetable.py    # PDF -> data/trips_parsed.json
python scripts/build_stations.py     # OSM coordinates -> data/stations.csv
python scripts/build_gtfs.py         # -> gtfs/*.txt
python scripts/build_shapes.py       # routes every trip over the rail graph -> shapes.txt
python scripts/validate.py           # structural + speed checks on the feed
python scripts/make_bundle.py        # -> data/bundle.json, what the app loads
npm run verify:geometry              # stations must sit on their routed track
npm run verify:gapeka                # feed vs the official GAPEKA 2025 register
```

`verify:gapeka` is the strongest check in the repo. `Train Timetables/GAPEKA
Jadwal Kereta.pdf` is Lampiran II of DJKA decree KP-DJKA 224/2024: every train in
Java with its number, relasi, distance and end-to-end times. Cross-checking
against it says independently that we parsed every train and that each
OSM-routed shape is the right length. All 47 trips currently agree, the largest
disagreement being 1.9 km on a 350 km circular run.

Three things in that pipeline are worth knowing about, because each one produced a
wrong map before it was handled:

- **The PDF's printed station codes are not trustworthy.** Wonokromo is printed
  `(WR)`, the same code as Waru, and Mojokerto appears as `(SDA)` on the Jenggala
  page. Columns are therefore resolved by station *name* against OpenStreetMap's
  `railway:ref`, and the printed code is only a fallback. `parse_timetable.py`
  reports every disagreement.
- **OpenStreetMap has real holes in this network.** The Lamongan-Duduk-Cerme
  stretch and the Kandangan-Indro branch are mapped in disconnected pieces.
  `build_shapes.py` bridges islands at their closest approach (up to 6 km), so a
  trip follows real track everywhere except the unmapped metres instead of
  degrading to a straight line for the whole leg.
- **Stations are projected onto shape segments, not vertices.** Shapes are
  simplified, so a station in the middle of a long straight (Ngujang, Tulangan,
  Peterongan) has no vertex within kilometres even though the line runs through
  it. `make_bundle.py` projects onto segments, and takes the *first* pass of a
  station - the circular Dhoho and Penataran runs call at Wonokromo and Gubeng
  twice.

### What about Tumapel and Sindro?

They do not exist under GAPEKA 2025. News coverage and older summaries describe
Wilayah 8 as having eight Commuter Line services, but the official register lists
exactly six - Dhoho, Penataran, Supas, Arjonegoro, Jenggala and Blorasura - and
neither Tumapel nor Sindro appears anywhere in it. The Sidoarjo-Indro service
that used to be Sindro is now part of Commuter Line Jenggala, which is why
Jenggala trips in this feed call at Indro. So the network here is complete, not
partial.

### Known data gaps

1. **Paired train numbers are one trip.** The timetable presents runs like
   `462-463` as a single through service, and the feed follows that, so a trip id
   can carry two train numbers. The register sometimes splits the same run into
   its two legs (Arjonegoro `444` + `445`), which `verify:gapeka` accounts for.
2. **The timetable is a snapshot.** `calendar.txt` claims daily service with no
   exceptions; real operations have engineering works and holiday extras.
3. **Two stretches of track are not fully mapped in OpenStreetMap**
   (Lamongan-Duduk-Cerme, Kandangan-Indro), so shapes cross those holes in a
   straight line. See `build_shapes.py`.

## Roadmap

- Expand to other KAI Commuter regions (Yogyakarta and Bandung timetables are already
  in `Train Timetables/`), then to intercity services
- A live adapter behind `activeTrains()` if a realtime feed ever becomes available

`viz/index.html` is the earlier 2D canvas prototype, kept for reference.

## Licence

MIT for the code. Map data © OpenStreetMap contributors (ODbL).
