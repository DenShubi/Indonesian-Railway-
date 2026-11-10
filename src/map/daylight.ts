/**
 * Time of day over the map.
 *
 * Mini Tokyo 3D swaps to a whole dark basemap after dark; this is the cheap half
 * of that idea - one flat wash over the view, deep blue through the night and a
 * little warmth at either end of the day - so a 03:00 run reads differently from
 * a midday one without a second style sheet or a second tile fetch.
 *
 * Jakarta sits near the equator, so sunrise and sunset barely move across the
 * year: about 05:40 and 17:45 all twelve months. These keyframes are fixed to
 * that rather than computed from a solar position nobody would be able to tell
 * apart on screen.
 */

/** [hour, red, green, blue, alpha] - linearly interpolated between keyframes. */
type Key = readonly [number, number, number, number, number];

const NIGHT = [18, 26, 58] as const;
const GOLD = [232, 146, 72] as const;

const KEYS: readonly Key[] = [
  [0, ...NIGHT, 0.3],
  [4.6, ...NIGHT, 0.3],
  [5.7, ...GOLD, 0.13],
  [7, ...GOLD, 0],
  [16.2, ...GOLD, 0],
  [17.4, ...GOLD, 0.13],
  [18.6, ...NIGHT, 0.22],
  [19.8, ...NIGHT, 0.3],
  [24, ...NIGHT, 0.3],
];

/**
 * The wash for a time of day, as a CSS colour. `seconds` is seconds from
 * midnight and may run past 24 h, which is how the feed records trips that cross
 * it; the curve wraps.
 */
export function daylightTint(seconds: number): string {
  const hour = (((seconds / 3600) % 24) + 24) % 24;

  let i = 0;
  while (i < KEYS.length - 2 && KEYS[i + 1][0] <= hour) i++;
  const from = KEYS[i];
  const to = KEYS[i + 1];
  const span = to[0] - from[0];
  const f = span > 0 ? (hour - from[0]) / span : 0;

  const at = (n: 1 | 2 | 3 | 4): number => from[n] + (to[n] - from[n]) * f;
  // Quantised to a hundredth: the frame loop asks for this sixty times a second,
  // and a value that changes every frame would both thrash the style attribute and
  // smear the CSS transition that smooths it.
  const alpha = Math.round(at(4) * 100) / 100;
  if (alpha <= 0) return 'transparent';

  return `rgba(${Math.round(at(1))}, ${Math.round(at(2))}, ${Math.round(at(3))}, ${alpha})`;
}
