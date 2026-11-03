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
 * Softens the Liberty building extrusions so trains and track stay readable through
 * dense blocks around Surabaya Gubeng and Pasar Turi.
 */
export function tuneBuildings(map: MapLibreMap): void {
  if (!map.getLayer(BUILDING_LAYER)) return;
  map.setPaintProperty(BUILDING_LAYER, 'fill-extrusion-color', '#d8d3cb');
  map.setPaintProperty(BUILDING_LAYER, 'fill-extrusion-opacity', 0.72);
}
