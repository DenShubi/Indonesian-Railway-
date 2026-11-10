/**
 * Indonesian Railway Visualizer - KAI Commuter Wilayah 8 (Surabaya).
 *
 * Positions are derived from the published timetable, not from a live feed: no
 * public realtime source exists for this network. activeTrains() is the single
 * seam a future live adapter would replace.
 */
import 'maplibre-gl/dist/maplibre-gl.css';
import './styles.css';

import type { Map as MapLibreMap, PointLike } from 'maplibre-gl';
import {
  buildNetwork,
  loadBundle,
  regionBounds,
  type Network,
  type RegionId,
  type RouteId,
  type StopCode,
} from './data/bundle';
import { ServiceClock } from './sim/clock';
import {
  activeTrains,
  secondsToNextDeparture,
  trainAt,
  type TrainState,
} from './sim/trains';
import { createMap, flattenBasemap, tuneBuildings } from './map/basemap';
import { daylightTint } from './map/daylight';
import { addTrackLayers, setVisibleRoutes } from './map/trackLayer';
import {
  addStationLayers,
  enableStationHover,
  setVisibleStationRegions,
  STATION_CIRCLE_LAYER,
} from './map/stationLayer';
import { TrainLayer } from './map/trainLayer';
import { initCab } from './ui/cab';
import { initHud } from './ui/hud';
import { initLinePanel } from './ui/linePanel';
import { renderTrainPanel } from './ui/trainPanel';
import { renderStationPanel } from './ui/stationPanel';
import { initTooltip } from './ui/tooltip';

// Guard the join as well as normalising `base` in vite.config.ts: a base without
// a trailing slash silently produces a URL one directory too high.
const BASE_URL = import.meta.env.BASE_URL.endsWith('/')
  ? import.meta.env.BASE_URL
  : `${import.meta.env.BASE_URL}/`;
const BUNDLE_URL = `${BASE_URL}data/bundle.json`;

type Selection = { kind: 'train'; tripId: string } | { kind: 'station'; code: StopCode } | null;

/** Degrees of bearing per second while the camera circles a followed train. */
const ORBIT_RATE = 1.5;

async function boot(): Promise<void> {
  const loadingEl = document.getElementById('loading') as HTMLElement;
  const detailEl = document.getElementById('detail') as HTMLElement;
  const nightfallEl = document.getElementById('nightfall') as HTMLElement;
  const stillness = window.matchMedia('(prefers-reduced-motion: reduce)');

  let net: Network;
  try {
    net = buildNetwork(await loadBundle(BUNDLE_URL));
  } catch (error) {
    loadingEl.textContent = `Could not load the timetable: ${(error as Error).message}`;
    loadingEl.classList.add('is-error');
    return;
  }

  const clock = new ServiceClock();
  // Start on the first region rather than the whole island: at Java-wide zoom
  // individual trains are specks.
  const region: { current: RegionId | null } = { current: net.regions[0]?.id ?? null };
  const visible = new Set<RouteId>();
  const colors = Object.fromEntries(
    Object.entries(net.bundle.routes).map(([id, route]) => [id, route.color]),
  );

  let selection: Selection = null;
  let follow = false;
  /** True once the camera has arrived at a followed train and may start to circle. */
  let orbiting = false;
  let states: TrainState[] = [];
  let layersReady = false;

  const bounds = () => {
    const current = net.regions.find((r) => r.id === region.current);
    return current ? regionBounds(current) : net.bbox;
  };

  /**
   * Fit the current region. A tilted camera sees a trapezoid, so the far corners
   * of a very wide fit fall outside the screen - flatten the view when showing
   * the whole island, and tilt back in for a single network.
   */
  function fitRegion(duration: number): void {
    const b = bounds();
    const narrow = map.getCanvas().clientWidth < 760;
    map.fitBounds([[b.west, b.south], [b.east, b.north]], {
      // Keep the fit clear of the header and the side panels, which float over
      // the map rather than sitting beside it.
      padding: narrow
        ? { top: 150, bottom: 220, left: 30, right: 30 }
        : { top: 130, bottom: 50, left: 240, right: 60 },
      duration,
      pitch: region.current ? 55 : 15,
    });
  }

  const map = createMap(document.getElementById('map') as HTMLElement, bounds());
  const trainLayer = new TrainLayer(colors);
  initCab(map);
  const hud = initHud(clock);
  const tooltip = initTooltip(net);

  function regionRoutes(): RouteId[] {
    return region.current ? (net.routeIdsByRegion.get(region.current) ?? []) : net.routeIds;
  }

  function applyRegion(fly: boolean): void {
    visible.clear();
    for (const id of regionRoutes()) visible.add(id);
    panel.refresh();
    if (layersReady) {
      setVisibleRoutes(map, visible);
      setVisibleStationRegions(map, new Set(region.current ? [region.current] : []));
    }
    clearSelection();
    hud.setRegion(net.regions.find((r) => r.id === region.current) ?? null);
    if (fly) fitRegion(900);
  }

  const panel = initLinePanel(
    net,
    visible,
    region,
    (id) => {
      region.current = id;
      applyRegion(true);
    },
    () => {
      if (layersReady) setVisibleRoutes(map, visible);
    },
  );
  for (const id of regionRoutes()) visible.add(id);
  panel.refresh();
  hud.setRegion(net.regions.find((r) => r.id === region.current) ?? null);

  map.on('load', () => {
    flattenBasemap(map);
    tuneBuildings(map);
    addTrackLayers(map, net.bundle);
    addStationLayers(map, net);
    map.addLayer(trainLayer);
    enableStationHover(map);
    setVisibleRoutes(map, visible);
    setVisibleStationRegions(map, new Set(region.current ? [region.current] : []));
    layersReady = true;
    loadingEl.remove();
    // Fit again now the container has its real size: the constructor fit can land
    // while the pane is still being laid out.
    fitRegion(0);
  });

  map.on('error', (event) => {
    console.error('[map]', event.error?.message ?? event);
  });

  /* ---------- selection ---------- */

  const selectedState = (): TrainState | null => {
    if (selection?.kind !== 'train') return null;
    const tripId = selection.tripId;
    return states.find((state) => state.trip.id === tripId) ?? null;
  };

  let detailSignature = '';

  function renderDetail(force = false): void {
    if (!selection) {
      if (detailSignature !== '') {
        detailEl.classList.add('hidden');
        detailEl.innerHTML = '';
        detailSignature = '';
      }
      return;
    }

    if (selection.kind === 'train') {
      const tripId = selection.tripId;
      const state = selectedState();
      if (!state) {
        // The train has finished its run, or its line was switched off.
        const trip = net.bundle.trips.find((candidate) => candidate.id === tripId);
        const signature = `gone:${tripId}`;
        if (signature !== detailSignature || force) {
          detailEl.classList.remove('hidden');
          detailEl.innerHTML =
            `<div class="panel-head"><span>Train ${trip?.n ?? ''}</span>` +
            `<button class="x" type="button" data-action="close" aria-label="Close">&times;</button></div>` +
            `<div class="detail-body"><p class="status">Not running at this time of day.</p></div>`;
          detailSignature = signature;
        }
        return;
      }
      const signature = [
        'train',
        state.trip.id,
        state.nextIndex,
        state.dwelling,
        follow,
        Math.round(state.distance * 2),
      ].join(':');
      if (signature === detailSignature && !force) return;
      detailEl.classList.remove('hidden');
      detailEl.innerHTML = renderTrainPanel(net, state, clock.time, follow);
      detailSignature = signature;
      return;
    }

    const signature = `station:${selection.code}:${Math.floor(clock.time / 30)}`;
    if (signature === detailSignature && !force) return;
    detailEl.classList.remove('hidden');
    detailEl.innerHTML = renderStationPanel(net, selection.code, clock.time);
    detailSignature = signature;
  }

  function selectTrain(tripId: string): void {
    selection = { kind: 'train', tripId };
    renderDetail(true);
  }

  function selectStation(code: StopCode): void {
    selection = { kind: 'station', code };
    follow = false;
    orbiting = false;
    renderDetail(true);
  }

  function clearSelection(): void {
    selection = null;
    follow = false;
    orbiting = false;
    renderDetail(true);
  }

  detailEl.addEventListener('click', (event) => {
    const target = (event.target as HTMLElement).closest('[data-action]') as HTMLElement | null;
    if (!target) return;
    const action = target.dataset['action'];

    if (action === 'close') {
      clearSelection();
      return;
    }

    if (action === 'follow') {
      follow = !follow;
      // The camera is handed over in two stages: a long ease onto the train, then
      // the frame loop takes it. Circling before it has arrived fights the ease.
      orbiting = false;
      const state = selectedState();
      if (follow && state) {
        map.easeTo({
          center: [state.lon, state.lat],
          zoom: Math.max(map.getZoom(), 13.2),
          pitch: 62,
          duration: stillness.matches ? 0 : 1800,
          essential: true,
        });
        map.once('moveend', () => {
          if (follow) orbiting = true;
        });
      }
      renderDetail(true);
      return;
    }

    if (action === 'select-train') {
      const tripId = target.dataset['trip'];
      if (!tripId) return;
      const trip = net.bundle.trips.find((candidate) => candidate.id === tripId);
      if (trip) {
        const state = trainAt(trip, net.bundle.shapes[trip.s], clock.time);
        if (state) map.easeTo({ center: [state.lon, state.lat], zoom: 12.5, duration: 900 });
      }
      selectTrain(tripId);
    }
  });

  map.on('click', (event) => {
    const train = trainLayer.pick(event.point);
    if (train) {
      selectTrain(train.trip.id);
      return;
    }
    // A few pixels of slack: station dots are small at city zoom levels.
    const slack = 7;
    const box: [PointLike, PointLike] = [
      [event.point.x - slack, event.point.y - slack],
      [event.point.x + slack, event.point.y + slack],
    ];
    const station = layersReady
      ? map.queryRenderedFeatures(box, { layers: [STATION_CIRCLE_LAYER] })[0]
      : undefined;
    const code = station?.properties?.['code'];
    if (typeof code === 'string') selectStation(code);
    else clearSelection();
  });

  let hoverCursor = '';
  map.on('mousemove', (event) => {
    const train = trainLayer.pick(event.point);
    if (train) tooltip.show(train, event.point.x, event.point.y);
    else tooltip.hide();

    const wanted = train ? 'pointer' : '';
    if (wanted === hoverCursor) return;
    hoverCursor = wanted;
    const canvas = map.getCanvas();
    // Leave the station layer's own cursor alone.
    if (wanted || canvas.style.cursor === 'pointer') canvas.style.cursor = wanted;
  });

  // The card is pinned to a pixel, and the fleet moves under it: anything that
  // moves the camera, or the pointer leaving the map, takes it away.
  for (const event of ['mouseout', 'dragstart', 'zoomstart', 'rotatestart'] as const) {
    map.on(event, () => tooltip.hide());
  }

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      clearSelection();
      return;
    }
    if (event.code === 'Space' && !(event.target as HTMLElement).matches('input, button')) {
      event.preventDefault();
      clock.toggle();
    }
  });

  /* ---------- frame loop ---------- */

  function frame(frameTime: number): void {
    // Seconds of wall clock since the last frame, for anything that moves at a
    // rate rather than a step. Clamped: a backgrounded tab resumes with a gap.
    const elapsed = lastFrameTime ? Math.min((frameTime - lastFrameTime) / 1000, 0.1) : 0;
    lastFrameTime = frameTime;

    clock.advance(frameTime);
    states = activeTrains(net, clock.time, visible);

    if (layersReady) {
      trainLayer.setTrains(states, selection?.kind === 'train' ? selection.tripId : null);
      map.triggerRepaint();
    }

    if (follow && orbiting) {
      const state = selectedState();
      // Hold the train in the middle and drift the bearing around it - about one
      // turn every four minutes, slow enough to read as the world moving rather
      // than the camera being swung.
      if (state) {
        map.jumpTo({
          center: [state.lon, state.lat],
          bearing: stillness.matches ? map.getBearing() : map.getBearing() + ORBIT_RATE * elapsed,
        });
      }
    }

    const tint = daylightTint(clock.time);
    if (tint !== lastTint) {
      nightfallEl.style.backgroundColor = tint;
      lastTint = tint;
    }

    // Only worth computing when the map is empty and the viewer needs telling why.
    const next = states.length === 0 ? secondsToNextDeparture(net, clock.time, visible) : null;
    hud.sync(states.length, next?.at ?? null);
    renderDetail();
    requestAnimationFrame(frame);
  }

  let lastFrameTime = 0;
  let lastTint = '';

  requestAnimationFrame(frame);
  exposeDebug(map, net, clock, trainLayer);
}

/** Small handle for poking at the running app from the browser console. */
function exposeDebug(
  map: MapLibreMap,
  net: Network,
  clock: ServiceClock,
  trainLayer: TrainLayer,
): void {
  (window as unknown as Record<string, unknown>)['jtv'] = { map, net, clock, trainLayer, activeTrains };
}

void boot();
