/**
 * Turns the timetable into positions: for a given time of day, which trains are
 * running and where each one is along its shape.
 *
 * Between two stations the position is eased rather than linear, so a train pulls
 * away from a platform and brakes into the next one while still hitting every
 * published arrival and departure time exactly.
 */
import type { BundleShape, BundleTrip, Network, StopCode } from '../data/bundle';
import { pointAtDist, segmentBearing } from './geo';

/** 0 = constant speed between stops, 1 = full stop-to-stop easing. */
const EASE_STRENGTH = 0.8;

const DAY = 86400;

export interface TrainState {
  trip: BundleTrip;
  lon: number;
  lat: number;
  /** Geographic bearing in radians, clockwise from north. */
  bearing: number;
  /** Distance travelled along the shape, in km. */
  distance: number;
  /** True while standing at a platform. */
  dwelling: boolean;
  /** Stop the train last called at (or is standing at). */
  fromStop: StopCode;
  /** Stop it is heading for (equals fromStop while dwelling at the terminus). */
  toStop: StopCode;
  /** Scheduled arrival at toStop, seconds from midnight. */
  toArrival: number;
  /** Index into trip.k of toStop. */
  nextIndex: number;
}

function smoothstep(f: number): number {
  const eased = f * f * (3 - 2 * f);
  return f + (eased - f) * EASE_STRENGTH;
}

/**
 * Position of one trip at time `t` (seconds from midnight), or null when the trip
 * is not running. `t` may exceed 86400 for a trip that runs past midnight, which
 * is how the feed records those times (Bandung Raya 367 arrives at "24:35").
 */
export function trainAt(trip: BundleTrip, shape: BundleShape, t: number): TrainState | null {
  const k = trip.k;
  const n = k.length;
  if (t < k[0][0] || t > k[n - 1][1]) return null;

  let distance = k[n - 1][2];
  let dwelling = true;
  let nextIndex = n - 1;

  for (let i = 0; i < n; i++) {
    if (t > k[i][1]) continue;
    nextIndex = i;
    if (t >= k[i][0]) {
      // standing at stop i
      distance = k[i][2];
      dwelling = true;
    } else {
      const prev = k[i - 1];
      if (!prev) {
        distance = k[i][2];
        dwelling = true;
      } else {
        const span = k[i][0] - prev[1];
        const f = span > 0 ? (t - prev[1]) / span : 1;
        distance = prev[2] + (k[i][2] - prev[2]) * smoothstep(Math.max(0, Math.min(1, f)));
        dwelling = false;
      }
    }
    break;
  }

  const at = pointAtDist(shape, distance);
  const forward = k[nextIndex][2] >= (k[Math.max(0, nextIndex - 1)][2] ?? 0);
  const bearing = segmentBearing(shape, at.seg) + (forward ? 0 : Math.PI);

  return {
    trip,
    lon: at.lon,
    lat: at.lat,
    bearing,
    distance,
    dwelling,
    fromStop: k[Math.max(0, nextIndex - (dwelling ? 0 : 1))][3],
    toStop: k[nextIndex][3],
    toArrival: k[nextIndex][0],
    nextIndex,
  };
}

/**
 * Every train running at time of day `t`, filtered to the visible routes.
 *
 * Each trip is tried twice: at `t`, and at `t + 24 h` for yesterday's late runners.
 * A service that leaves at 22:35 and arrives at "24:01" is still out there at 00:10
 * today, and the clock - a time of day in [0, 86400) - can only meet it in the
 * second day.
 */
export function activeTrains(net: Network, t: number, visibleRoutes: Set<string>): TrainState[] {
  const out: TrainState[] = [];
  for (const trip of net.bundle.trips) {
    if (!visibleRoutes.has(trip.r)) continue;
    const shape = net.bundle.shapes[trip.s];
    const state = trainAt(trip, shape, t);
    if (state) {
      out.push(state);
      continue;
    }
    const overnight = trainAt(trip, shape, t + DAY);
    if (overnight) {
      // Report the arrival as a time of day, so "next stop in 5 min" does not
      // come out as "in 24 h 5 min" once the trip's own clock has passed 24:00.
      out.push({ ...overnight, toArrival: overnight.toArrival - DAY });
    }
  }
  return out;
}

/**
 * Seconds until the next departure at or after `t`, across the visible routes, for
 * telling the viewer when service resumes. Returns null if nothing runs at all.
 */
export function secondsToNextDeparture(
  net: Network,
  t: number,
  visibleRoutes: Set<string>,
): { at: number; wait: number } | null {
  let best: number | null = null;
  for (const trip of net.bundle.trips) {
    if (!visibleRoutes.has(trip.r)) continue;
    const departure = trip.k[0][1];
    // Wrap into "time from now", so late evening rolls around to the small hours.
    const wait = (((departure - t) % DAY) + DAY) % DAY;
    if (best === null || wait < best) best = wait;
  }
  return best === null ? null : { at: (t + best) % DAY, wait: best };
}
