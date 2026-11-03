/**
 * Track geometry: every trip shape in the bundle, drawn once per route colour.
 * The shapes come from scripts/build_shapes.py, which routes each trip over the
 * real OpenStreetMap rail network, so these are actual alignments, not straight hops.
 */
import type { Map as MapLibreMap } from 'maplibre-gl';
import type { FeatureCollection, LineString } from 'geojson';
import type { Bundle, RouteId } from '../data/bundle';
import { BUILDING_LAYER } from './basemap';

export const TRACK_SOURCE = 'jtv-tracks';
export const TRACK_CASING_LAYER = 'jtv-track-casing';
export const TRACK_LINE_LAYER = 'jtv-track-line';

interface TrackProps {
  shape: string;
  route: RouteId;
  color: string;
}

function toGeoJSON(bundle: Bundle): FeatureCollection<LineString, TrackProps> {
  // A shape can be shared by several trips, but all of them belong to one route.
  const routeOfShape = new Map<string, RouteId>();
  for (const trip of bundle.trips) routeOfShape.set(trip.s, trip.r);

  return {
    type: 'FeatureCollection',
    features: Object.entries(bundle.shapes).map(([shapeId, shape]) => {
      const route = routeOfShape.get(shapeId) ?? '';
      return {
        type: 'Feature' as const,
        geometry: { type: 'LineString' as const, coordinates: shape.c },
        properties: {
          shape: shapeId,
          route,
          color: bundle.routes[route]?.color ?? '#888888',
        },
      };
    }),
  };
}

export function addTrackLayers(map: MapLibreMap, bundle: Bundle): void {
  map.addSource(TRACK_SOURCE, { type: 'geojson', data: toGeoJSON(bundle) });

  // Beneath the building extrusions, so the city sits on top of the ground plane.
  const before = map.getLayer(BUILDING_LAYER) ? BUILDING_LAYER : undefined;

  map.addLayer(
    {
      id: TRACK_CASING_LAYER,
      type: 'line',
      source: TRACK_SOURCE,
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: {
        'line-color': '#1b2024',
        'line-opacity': 0.55,
        'line-width': ['interpolate', ['linear'], ['zoom'], 7, 3.5, 11, 7, 15, 13],
      },
    },
    before,
  );

  map.addLayer(
    {
      id: TRACK_LINE_LAYER,
      type: 'line',
      source: TRACK_SOURCE,
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: {
        'line-color': ['get', 'color'],
        'line-width': ['interpolate', ['linear'], ['zoom'], 7, 1.6, 11, 3.4, 15, 6.5],
      },
    },
    before,
  );
}

export function setVisibleRoutes(map: MapLibreMap, visible: Set<RouteId>): void {
  const filter = ['in', ['get', 'route'], ['literal', [...visible]]];
  for (const id of [TRACK_CASING_LAYER, TRACK_LINE_LAYER]) {
    if (map.getLayer(id)) map.setFilter(id, filter as never);
  }
}
