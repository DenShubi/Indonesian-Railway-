/**
 * The basemap: MapLibre GL JS (BSD-3) on OpenFreeMap's keyless vector tiles.
 * No access token, no registration, no usage cap - attribution is carried by the
 * style itself (OpenStreetMap contributors, ODbL).
 */
import { Map as MapLibreMap, NavigationControl, ScaleControl, setWorkerUrl } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
import type { Bbox } from '../data/bundle';

// MapLibre derives its worker URL from its own module location, which neither
// Vite's dep pre-bundling nor the production chunking preserves - the worker file
// is simply never emitted. Pointing at it explicitly makes `?url` emit the asset
// and keeps dev and build on the same path.
setWorkerUrl(workerUrl);

export const STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty';

/** Layer id in the Liberty style that extruded buildings are drawn in. */
export const BUILDING_LAYER = 'building-3d';

export function createMap(container: HTMLElement, bbox: Bbox): MapLibreMap {
  const map = new MapLibreMap({
    container,
    style: STYLE_URL,
    bounds: [
      [bbox.west, bbox.south],
      [bbox.east, bbox.north],
    ],
    fitBoundsOptions: { padding: 60 },
    pitch: 55,
    bearing: -18,
    maxPitch: 80,
    canvasContextAttributes: { antialias: true, powerPreference: 'high-performance' },
    hash: false,
    attributionControl: { compact: true },
  });

  map.addControl(new NavigationControl({ visualizePitch: true }), 'bottom-right');
  map.addControl(new ScaleControl({ unit: 'metric' }), 'bottom-left');

  return map;
}

/**
 * The ground: a near-monochrome base, the way Mini Tokyo 3D desaturates its map so
 * the only saturated colour on screen belongs to the railway.
 */
const GROUND = {
  land: '#e8e9eb',
  landAlt: '#e3e4e7',
  water: '#c4d1db',
  green: '#dde2da',
  sand: '#e8e3d8',
  ice: '#eef1f4',
  building: '#dcdcdf',
  roadFill: '#fafafa',
  roadCasing: '#dddee2',
  rail: '#cfd0d4',
  boundary: '#c6c7cb',
  label: '#4f545b',
  halo: '#ffffff',
} as const;

/** Clutter that competes with the trains: shields, pins, house numbers. */
const HIDE = /poi|housenumber|shield|ferry|aerodrome-label|airport-label/i;

function fillColour(id: string): string {
  if (/water|ocean|sea|lake|river|bay|dock|swimming/i.test(id)) return GROUND.water;
  if (/building/i.test(id)) return GROUND.building;
  if (/wood|forest|park|grass|green|scrub|golf|pitch|cemetery|farm|orchard|vineyard|garden|zoo|allotment/i.test(id)) {
    return GROUND.green;
  }
  if (/sand|beach|desert/i.test(id)) return GROUND.sand;
  if (/glacier|ice|snow/i.test(id)) return GROUND.ice;
  return GROUND.landAlt;
}

function lineColour(id: string): string {
  if (/boundary|admin/i.test(id)) return GROUND.boundary;
  if (/water|river|stream|canal|waterway|dock/i.test(id)) return GROUND.water;
  if (/rail|transit|tram|funicular|subway/i.test(id)) return GROUND.rail;
  if (/casing|outline|bg$/i.test(id)) return GROUND.roadCasing;
  return GROUND.roadFill;
}

/**
 * Flattens the vector style down to the greys above and drops the point-of-interest
 * clutter. Every property is set defensively: the hosted style is not ours, its
 * layer list changes without notice, and a layer that has no such paint property is
 * not worth failing the whole map over.
 */
export function flattenBasemap(map: MapLibreMap): void {
  const layers = map.getStyle()?.layers ?? [];

  for (const layer of layers) {
    const id = layer.id;
    const set = (prop: string, value: unknown): void => {
      try {
        map.setPaintProperty(id, prop as never, value as never);
      } catch {
        // The layer does not carry this property; nothing to flatten.
      }
    };

    try {
      if (HIDE.test(id)) {
        map.setLayoutProperty(id, 'visibility', 'none');
        continue;
      }
    } catch {
      // Layer vanished between reading the style and here.
    }

    switch (layer.type) {
      case 'background':
        set('background-color', GROUND.land);
        set('background-pattern', undefined);
        break;

      case 'fill': {
        const colour = fillColour(id);
        set('fill-color', colour);
        set('fill-outline-color', colour);
        set('fill-pattern', undefined);
        break;
      }

      case 'line':
        set('line-color', lineColour(id));
        set('line-pattern', undefined);
        break;

      case 'symbol':
        set('text-color', GROUND.label);
        set('text-halo-color', GROUND.halo);
        set('text-halo-width', 1.3);
        set('icon-opacity', 0);
        break;

      case 'fill-extrusion':
        set('fill-extrusion-color', GROUND.building);
        set('fill-extrusion-opacity', 0.55);
        break;

      default:
        break;
    }
  }
}

/**
 * Softens the Liberty building extrusions so trains and track stay readable through
 * dense blocks around Surabaya Gubeng and Pasar Turi.
 */
export function tuneBuildings(map: MapLibreMap): void {
  if (!map.getLayer(BUILDING_LAYER)) return;
  map.setPaintProperty(BUILDING_LAYER, 'fill-extrusion-color', GROUND.building);
  map.setPaintProperty(BUILDING_LAYER, 'fill-extrusion-opacity', 0.55);
}
