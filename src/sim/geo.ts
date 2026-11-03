/**
 * Geometry helpers for walking a trip along its shape.
 * Ported from the 2D prototype (viz/index.html pointAtDist/bear) and typed.
 */
import type { BundleShape } from '../data/bundle';

export interface ShapePoint {
  lon: number;
  lat: number;
  /** Index of the shape segment the point sits on (point i -> i+1). */
  seg: number;
}

/** Point at `km` along the shape's cumulative distance array, clamped at both ends. */
export function pointAtDist(shape: BundleShape, km: number): ShapePoint {
  const { c, d } = shape;
  const last = d.length - 1;
  if (km <= d[0]) return { lon: c[0][0], lat: c[0][1], seg: 0 };
  if (km >= d[last]) return { lon: c[last][0], lat: c[last][1], seg: Math.max(0, last - 1) };

  let lo = 0;
  let hi = last;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (d[mid] <= km) lo = mid;
    else hi = mid;
  }
  const span = d[hi] - d[lo];
  const f = span > 1e-9 ? (km - d[lo]) / span : 0;
  return {
    lon: c[lo][0] + (c[hi][0] - c[lo][0]) * f,
    lat: c[lo][1] + (c[hi][1] - c[lo][1]) * f,
    seg: lo,
  };
}

/**
 * Geographic bearing of shape segment `seg`, in radians clockwise from north.
 * Uses an equirectangular approximation, which is ample at commuter-line scale.
 */
export function segmentBearing(shape: BundleShape, seg: number): number {
  const { c } = shape;
  const a = c[Math.max(0, Math.min(seg, c.length - 2))];
  const b = c[Math.max(1, Math.min(seg + 1, c.length - 1))];
  const dLat = b[1] - a[1];
  const dLon = (b[0] - a[0]) * Math.cos(((a[1] + b[1]) / 2) * (Math.PI / 180));
  return Math.atan2(dLon, dLat);
}

/** Great-circle distance in metres. */
export function haversine(aLon: number, aLat: number, bLon: number, bLat: number): number {
  const p = Math.PI / 180;
  const h =
    Math.sin(((bLat - aLat) * p) / 2) ** 2 +
    Math.cos(aLat * p) * Math.cos(bLat * p) * Math.sin(((bLon - aLon) * p) / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(h));
}
