# Indonesian Railway Visualizer

A 3D map of Indonesian commuter trains, animated from the published timetables —
inspired by [Mini Tokyo 3D](https://minitokyo3d.com/), built on a stack that needs
no API keys and costs nothing to run.

Three KAI Commuter networks, switchable in the app: **137 daily trips on 12 lines
through 120 stations**, running over real OpenStreetMap rail alignments and checked
against the official GAPEKA 2025 register.

| Region | Lines | Trips |
| --- | --- | --- |
| **Surabaya** (Wilayah 8) | Dhoho, Penataran, Supas, Arjonegoro, Jenggala, Blorasura | 47 |
| **Bandung** (Wilayah 2) | Bandung Raya, Garut, Walahar, Jatiluhur | 58 |
| **Yogyakarta** (Wilayah 6) | Yogyakarta, Prameks | 32 |

> **Scheduled positions, not live GPS.** No public realtime feed exists for these
> networks, so trains are placed from the published timetable. Where a train is drawn
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
npm run verify:gapeka    # cross-check the feed against GAPEKA 2025
```

`npm run dev` and `npm run build` both copy `data/bundle.json` into `public/data/`
first, so the Python pipeline's output stays the single source of truth.

## How it works

| Piece | What it does |
| --- | --- |
| `src/data/bundle.ts` | Loads `bundle.json`, indexes trips by route and calls by station, and snaps every station onto the track |
| `src/sim/clock.ts` | Time-of-day cursor in Asia/Jakarta: play/pause, 1x–300x, scrub, back to live |
| `src/sim/trains.ts` | Which trains are running and where, with eased acceleration between stops |
| `src/map/basemap.ts` | MapLibre GL JS on OpenFreeMap's keyless vector tiles, flattened to greys so the railway is the only colour |
| `src/map/trackLayer.ts` | Trip shapes as coloured lines, below the building extrusions |
| `src/map/trainLayer.ts` | A three.js custom layer: the whole fleet as one `InstancedMesh`, one draw call |
| `src/map/daylight.ts` | Time of day as a single wash over the view: blue at night, warm at either end of the day |
| `src/ui/cab.ts` | The two headlights: one shows the lines panel, one folds the cab away so the map has the window |
| `src/ui/linePanel.ts` | Region switcher and the per-line chips for the chosen network |
| `src/ui/tooltip.ts` | The hover card over a train: line, service, last stop and next |
| `src/ui/` | Header clock, train detail card, station departures board |

### The shell is a train front

The page is drawn as the front of a commuter train: a destination board across the
top with the line name centred on it like a headboard, a windscreen that holds the
map, and an apron below carrying the controls between two headlights. The left
headlight shows and hides the lines panel; the right one folds the cab away so the
map has the whole window, with a small button in the corner to bring it back. It
does not ask the browser for fullscreen: the point is to get the chrome out of the
way, and a real fullscreen request can be refused, can hang behind a prompt, or -
inside an embedded frame - never settle at all.

The body is a carriage red, `oklch(50.5% 0.18 27)` (`#b52323`), against a warm
off-white face.
Colour is declared in OKLCH so the lightness steps read evenly, and every neutral is
tinted a few thousandths toward that same hue so the greys sit with the red rather
than beside it. Every surface is one flat colour: no gradients, no glows, no blur,
no drop shadows. Depth is a step in lightness and separation is a hairline, which is
what keeps the panels sitting on the map rather than hovering over it.

Type is Rubik throughout, whose rounded corners and open counters read soft without
turning cute, with JetBrains Mono for times and distances, where columns have to
line up. Four radii (6, 10, 18, pill) cover every corner in the app.

The map follows Mini Tokyo 3D: a near-monochrome basemap so the only saturated
colour on screen belongs to the railway, line colours carried from the track to the
trains to the panel headers, a hover card over each train, and a selected train's
whole run drawn as a route diagram rather than a table. Time of day washes over the
whole view - deep blue through the night, a little warmth at dawn and dusk, nothing
at midday - so a 03:00 run reads differently from a midday one. Following a train
eases the camera onto it and then circles it at about one turn every four minutes;
both the ease and the circling are dropped under `prefers-reduced-motion`.

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

## Deploying

The site builds and publishes itself from `.github/workflows/deploy.yml` on every
push to `main`: install, run both data verifications, build, upload, deploy.

**One setting has to be made by hand, once** - GitHub will not let a workflow turn
Pages on for its own repository:

> **Settings → Pages → Build and deployment → Source → GitHub Actions**

Two symptoms say the source is wrong. If Pages is off entirely,
`actions/deploy-pages` fails with
`Failed to create deployment (status: 404) ... Ensure GitHub Pages has been enabled`.
If it is set to **Deploy from a branch** instead, something subtler happens: GitHub
also runs its own "pages build and deployment" workflow, which publishes the
*repository root* rather than `dist/`. The two deployments then race on every push,
and the branch one serves the repo's `index.html` - the Vite entry point, which asks
the browser for `/src/main.ts` and gets a 404. A site that works one minute and is
blank the next is this, not a bug in the app.

`actions/configure-pages` does have an `enablement` input that would set this from
CI, but it needs a personal access token rather than the workflow's own
`GITHUB_TOKEN`, and a long-lived admin token is a worse thing to keep in a
repository than one click. Once the source is right, re-run the latest workflow and
the site is live at `https://<user>.github.io/<repo>/`.

The build takes its base path from `actions/configure-pages`, falling back to the
value in [vite.config.ts](vite.config.ts), so renaming the repository does not
break the published asset URLs.

While you are in Settings, the repository has no description, website or topics.
Suggested: *"3D map of Indonesian commuter trains, animated from the published
timetables"*, the Pages URL as the website, and topics `openstreetmap`, `maplibre`,
`threejs`, `gtfs`, `indonesia`, `transit`, `dataviz`.

## Data

| Source | Used for | Licence |
| --- | --- | --- |
| KAI Commuter published timetable (`Train Timetables/*.pdf`) | Trips, times, calling patterns | Factual timetable data, republished for public information |
| OpenStreetMap | Rail alignments and station positions | ODbL - (c) OpenStreetMap contributors |

This project is **not affiliated with KAI, KAI Commuter or any operator**. Do not
use it to catch a train.

### Rebuilding the feed

Every region is described in `data/regions.json` - its PDF, bounding box, page
layouts, hub stations and line colours - and every script works from that list,
so adding a fourth network is a data change plus whatever new page layout its PDF
turns out to use.

```bash
pip install -r requirements.txt
python scripts/fetch_osm.py          # rail + stations per region, cached in data/osm/<region>/
python scripts/parse_timetable.py    # PDFs -> data/trips_parsed.json
python scripts/build_stations.py     # OSM coordinates -> data/stations.csv
python scripts/build_gtfs.py         # -> gtfs/*.txt (one feed, routes tagged by region)
python scripts/build_shapes.py       # routes every trip over its region's rail graph
python scripts/validate.py           # structural + speed checks on the feed
python scripts/make_bundle.py        # -> data/bundle.json, what the app loads
npm run verify:geometry              # stations must sit on their routed track
npm run verify:gapeka                # feed vs the official GAPEKA 2025 register
```

`fetch_osm.py` caches per region and only refetches with `--force`; Overpass is a
donated service.

`verify:gapeka` is the strongest check in the repo. `Train Timetables/GAPEKA
Jadwal Kereta.pdf` is Lampiran II of DJKA decree KP-DJKA 224/2024: every train in
Java with its number, relasi, distance and end-to-end times. Cross-checking
against it says independently that we parsed every train and that each
OSM-routed shape is the right length. All 47 trips currently agree, the largest
disagreement being 1.9 km on a 350 km circular run.

Four things in that pipeline are worth knowing about, because each one produced a
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
- **Every PDF glues its words differently.** The timetables are read from
  geometrically rebuilt words rather than extracted text, and even then one page
  prints `PADALARANG(PDL)`, another `(GRM) GARUM`, a third `CommuterLineGarut` as a
  single token, and one heading arrives as `NO.NOMOR KA NAMA KA RELASI`. Trip rows
  are therefore read by content - re-split on lowercase-to-uppercase joins - rather
  than by measuring column edges. Yogyakarta is plain text with a fourth shape
  again, so it has its own reader.
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

1. **The Yogyakarta PDF predates GAPEKA 2025.** It numbers its trains 661-684 and
   551-558; the register numbers the same services 701-733 and 501-512, and lists
   43 trains where the PDF has 32. The routes match - our longest Yogyakarta run
   measures 65.8 km against the register's 65.5, and Prameks 63.7 against 63.6 -
   but the times are from the earlier edition. That caveat is recorded here
   rather than on screen, and `verify:gapeka` checks that region by route length
   instead of by train number.
2. **Paired train numbers are one trip.** The timetable presents runs like
   `462-463` as a single through service, and the feed follows that, so a trip id
   can carry two train numbers. The register sometimes splits the same run into
   its two legs (Arjonegoro `444` + `445`), which `verify:gapeka` accounts for.
3. **The timetables are snapshots.** `calendar.txt` claims daily service with no
   exceptions; real operations have engineering works and holiday extras.
4. **Some track is not fully mapped in OpenStreetMap** - Lamongan-Duduk-Cerme and
   Kandangan-Indro near Surabaya, and a few shorter holes in each region - so
   shapes cross those gaps in a straight line. `build_shapes.py` reports every
   bridge it makes and how wide it was.

## Roadmap

- A current Yogyakarta timetable, to replace the pre-2025 edition
- KRL Jabodetabek, the biggest network of all, then intercity services
- A live adapter behind `activeTrains()` if a realtime feed ever becomes available

`viz/index.html` is the earlier 2D canvas prototype, kept for reference.

## Licence

MIT for the code. Map data © OpenStreetMap contributors (ODbL).
