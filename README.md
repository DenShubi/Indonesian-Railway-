# Indonesian Railway Visualizer

A 3D map of Indonesian commuter trains, animated from the published timetable —
inspired by [Mini Tokyo 3D](https://minitokyo3d.com/), built on a stack that needs
no API keys and costs nothing to run.

The first network is **KAI Commuter Wilayah 8 (Surabaya)**: the Dhoho, Penataran,
Supas and Arjonegoro lines, 62 stations, 33 daily trips, running over real
OpenStreetMap rail alignments.

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
| OpenStreetMap | Rail alignments and station positions | ODbL — © OpenStreetMap contributors |

The pipeline in `scripts/` (Python) parses the timetable PDF, matches station codes,
routes each trip over the OSM rail network, emits a GTFS feed in `gtfs/`, and
precomputes `data/bundle.json` for the browser.

This project is **not affiliated with KAI, KAI Commuter or any operator**. Do not use
it to catch a train.

### Known data gaps

The Wilayah 8 PDF has five pages and advertises eight lines; the current feed covers
four. Worth fixing next:

1. **Commuter Line Jenggala is missing.** PDF page 4 holds it (Surabaya Pasar Turi–Sidoarjo,
   and Babat–Surabaya Pasar Turi–Mojokerto), but `scripts/parse_wil8.py` reads pages
   1, 2, 3 and 5 only.
2. **Blorasura trips are filed under Arjonegoro.** Page 5 carries both lines; trains
   438/439/440/441 (Cepu ↔ Surabaya Pasarturi) belong to Blorasura.
3. **Tumapel and Sindro are not in this PDF** and need another source.
4. **Nine station coordinates are more than 1 km off the rail**, from fuzzy name
   matching — worst are Ngujang (5.1 km), Sumbergempol (4.3 km) and Peterongan (3.1 km).
   Run `npm run verify:geometry` for the current list. The app hides this by drawing
   each station where its trains stop, but the coordinates should be re-sourced from
   OpenStreetMap.
5. **The Python pipeline is not runnable as-is here**: the scripts hardcode
   `/home/claude/...` paths, `data/osm_stations.csv` and the OSM rail GeoJSON are not
   in the repo, and the scripts need `pdfplumber`, `networkx` and `scipy`.

## Roadmap

- Complete Wilayah 8 (Jenggala, Blorasura, Tumapel, Sindro) and fix the station coordinates
- Port the Python pipeline to repo-relative paths so the feed can be rebuilt here
- Expand to other KAI Commuter regions (Yogyakarta and Bandung timetables are already
  in `Train Timetables/`), then to intercity services
- A live adapter behind `activeTrains()` if a realtime feed ever becomes available

`viz/index.html` is the earlier 2D canvas prototype, kept for reference.

## Licence

MIT for the code. Map data © OpenStreetMap contributors (ODbL).
