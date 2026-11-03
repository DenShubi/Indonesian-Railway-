/**
 * Types and loader for data/bundle.json — the compact animation bundle produced by
 * scripts/make_bundle.py out of the GTFS feed in gtfs/.
 *
 * The on-disk field names are short on purpose (the bundle is shipped to the browser):
 *   stops  { n: name, y: lat, x: lon }
 *   shapes { c: [[lon, lat], ...], d: [cumulative_km, ...] }   (c and d are parallel)
 *   trips  { id, n: train number, r: route_id, h: headsign, s: shape_id, k: keyframes }
 *   keyframe [arrival_s, departure_s, distance_km, stop_code]  (seconds from midnight)
 */

import { haversine, pointAtDist } from '../sim/geo';

export type RouteId = string;
export type StopCode = string;
export type ShapeId = string;

export interface BundleRoute {
  name: string;
  color: string;
  /** Representative shape id, used for the line's own overview geometry. */
  rep: ShapeId;
}

export interface BundleStop {
  n: string;
  y: number;
  x: number;
}

export interface BundleShape {
  c: [number, number][];
  d: number[];
}

/** [arrival_s, departure_s, distance_km, stop_code] */
export type Keyframe = [number, number, number, StopCode];

export interface BundleTrip {
  id: string;
  n: string;
  r: RouteId;
  h: string;
  s: ShapeId;
  k: Keyframe[];
}

export interface Bundle {
  routes: Record<RouteId, BundleRoute>;
  stops: Record<StopCode, BundleStop>;
  shapes: Record<ShapeId, BundleShape>;
  trips: BundleTrip[];
}

/** One scheduled call at a station, used by the station departures board. */
export interface StopCall {
  trip: BundleTrip;
  /** Index into trip.k */
  idx: number;
  arrival: number;
  departure: number;
}

export interface Bbox {
  west: number;
  south: number;
  east: number;
  north: number;
}

/** The bundle plus the indexes the app needs at runtime. */
export interface Network {
  bundle: Bundle;
  routeIds: RouteId[];
  /** First departure and last arrival across all trips, in seconds from midnight. */
  serviceStart: number;
  serviceEnd: number;
  bbox: Bbox;
  tripsByRoute: Map<RouteId, BundleTrip[]>;
  /** Calls at each station, sorted by departure time. */
  callsByStop: Map<StopCode, StopCall[]>;
  /** Where each station is drawn: on the track, where trains actually stop. */
  stationPositions: Map<StopCode, StationPosition>;
}

/**
 * Stations are drawn at the point on the routed track where their trains stop,
 * not at the raw coordinate in the bundle. Several of the bundle's coordinates
 * came from fuzzy name matching and sit a few hundred metres - occasionally
 * kilometres - off the rail alignment; snapping keeps platforms and trains
 * together. `offsetM` is how far the raw coordinate was from the track, which is
 * the list of stations worth re-sourcing from OpenStreetMap later.
 */
export interface StationPosition {
  lon: number;
  lat: number;
  rawLon: number;
  rawLat: number;
  offsetM: number;
}

export async function loadBundle(url: string): Promise<Bundle> {
  const res = await fetch(url, { cache: 'no-cache' });
  if (!res.ok) throw new Error(`could not load ${url}: HTTP ${res.status}`);
  const bundle = (await res.json()) as Bundle;
  validate(bundle);
  return bundle;
}

function validate(b: Bundle): void {
  for (const key of ['routes', 'stops', 'shapes', 'trips'] as const) {
    if (!b[key]) throw new Error(`bundle is missing "${key}"`);
  }
  if (!Array.isArray(b.trips) || b.trips.length === 0) throw new Error('bundle has no trips');
  for (const trip of b.trips) {
    if (!b.shapes[trip.s]) throw new Error(`trip ${trip.id} references unknown shape ${trip.s}`);
    if (!b.routes[trip.r]) throw new Error(`trip ${trip.id} references unknown route ${trip.r}`);
    if (trip.k.length < 2) throw new Error(`trip ${trip.id} has fewer than 2 keyframes`);
  }
  for (const [id, shape] of Object.entries(b.shapes)) {
    if (shape.c.length !== shape.d.length) throw new Error(`shape ${id}: c/d length mismatch`);
  }
}

export function buildNetwork(bundle: Bundle): Network {
  let serviceStart = Infinity;
  let serviceEnd = -Infinity;
  const tripsByRoute = new Map<RouteId, BundleTrip[]>();
  const callsByStop = new Map<StopCode, StopCall[]>();

  for (const trip of bundle.trips) {
    const first = trip.k[0];
    const last = trip.k[trip.k.length - 1];
    serviceStart = Math.min(serviceStart, first[0]);
    serviceEnd = Math.max(serviceEnd, last[1]);

    const list = tripsByRoute.get(trip.r);
    if (list) list.push(trip);
    else tripsByRoute.set(trip.r, [trip]);

    trip.k.forEach((frame, idx) => {
      const call: StopCall = { trip, idx, arrival: frame[0], departure: frame[1] };
      const calls = callsByStop.get(frame[3]);
      if (calls) calls.push(call);
      else callsByStop.set(frame[3], [call]);
    });
  }

  for (const calls of callsByStop.values()) {
    calls.sort((a, b) => a.departure - b.departure);
  }

  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const shape of Object.values(bundle.shapes)) {
    for (const [lon, lat] of shape.c) {
      if (lon < west) west = lon;
      if (lon > east) east = lon;
      if (lat < south) south = lat;
      if (lat > north) north = lat;
    }
  }

  return {
    bundle,
    stationPositions: snapStations(bundle),
    routeIds: Object.keys(bundle.routes),
    serviceStart: Math.floor(serviceStart / 300) * 300,
    serviceEnd: Math.ceil(serviceEnd / 300) * 300,
    bbox: { west, south, east, north },
    tripsByRoute,
    callsByStop,
  };
}

/**
 * For every stop, averages the on-track points where its trains are scheduled to
 * stand. Stops that no trip calls at keep their raw coordinate.
 */
function snapStations(bundle: Bundle): Map<StopCode, StationPosition> {
  const sums = new Map<StopCode, { lon: number; lat: number; n: number }>();

  for (const trip of bundle.trips) {
    const shape = bundle.shapes[trip.s];
    for (const frame of trip.k) {
      const at = pointAtDist(shape, frame[2]);
      const acc = sums.get(frame[3]);
      if (acc) {
        acc.lon += at.lon;
        acc.lat += at.lat;
        acc.n += 1;
      } else {
        sums.set(frame[3], { lon: at.lon, lat: at.lat, n: 1 });
      }
    }
  }

  const out = new Map<StopCode, StationPosition>();
  for (const [code, stop] of Object.entries(bundle.stops)) {
    const acc = sums.get(code);
    if (!acc) {
      out.set(code, { lon: stop.x, lat: stop.y, rawLon: stop.x, rawLat: stop.y, offsetM: 0 });
      continue;
    }
    const lon = acc.lon / acc.n;
    const lat = acc.lat / acc.n;
    out.set(code, {
      lon,
      lat,
      rawLon: stop.x,
      rawLat: stop.y,
      offsetM: haversine(stop.x, stop.y, lon, lat),
    });
  }
  return out;
}

export function stopName(bundle: Bundle, code: StopCode): string {
  return bundle.stops[code]?.n ?? code;
}
