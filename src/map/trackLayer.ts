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
        // A white casing rather than a dark one: over the flattened basemap the
        // lines read as a transit map's ribbons, which is how Mini Tokyo 3D draws
        // its railways. A dark halo only muddies the colour.
        'line-color': '#ffffff',
        // Faded out at region scale: there the casing is wider than the line it
        // wraps, and a whole network of them washes the colours out.
        'line-opacity': ['interpolate', ['linear'], ['zoom'], 8, 0, 11, 0.9],
        'line-width': ['interpolate', ['linear'], ['zoom'], 7, 3.2, 11, 6, 15, 11],
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
        'line-width': ['interpolate', ['linear'], ['zoom'], 7, 1.6, 11, 3.2, 15, 6],
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
