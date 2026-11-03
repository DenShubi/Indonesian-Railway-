/**
 * The service clock: a time-of-day cursor in Asia/Jakarta (WIB), independent of the
 * viewer's own timezone, that can be paused, sped up and scrubbed.
 */

export const SPEEDS = [1, 10, 60, 300] as const;
export type Speed = (typeof SPEEDS)[number];

const DAY = 86400;

const wibParts = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Jakarta',
  hour12: false,
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

/** Current wall-clock time in Jakarta, as seconds from midnight. */
export function jakartaSecondsOfDay(now: Date = new Date()): number {
  let h = 0;
  let m = 0;
  let s = 0;
  for (const part of wibParts.formatToParts(now)) {
    if (part.type === 'hour') h = Number(part.value) % 24;
    else if (part.type === 'minute') m = Number(part.value);
    else if (part.type === 'second') s = Number(part.value);
  }
  return h * 3600 + m * 60 + s;
}

export function formatClock(seconds: number, withSeconds = true): string {
  const t = ((seconds % DAY) + DAY) % DAY;
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = Math.floor(t % 60);
  const hh = String(h).padStart(2, '0');
  const mm = String(m).padStart(2, '0');
  return withSeconds ? `${hh}:${mm}:${String(s).padStart(2, '0')}` : `${hh}:${mm}`;
}

export class ServiceClock {
  /** Seconds from midnight WIB, always in [0, 86400). */
  time: number;
  speed: Speed = 1;
  playing = true;
  /** True while the clock tracks real Jakarta time at 1x. */
  live = true;

  private lastFrame = performance.now();
  private readonly listeners = new Set<() => void>();

  constructor() {
    this.time = jakartaSecondsOfDay();
  }

  onChange(fn: () => void): void {
    this.listeners.add(fn);
  }

  /** Advances the clock by the wall time elapsed since the previous frame. */
  advance(frameTime: number): void {
    const elapsed = Math.max(0, Math.min(frameTime - this.lastFrame, 1000)) / 1000;
    this.lastFrame = frameTime;
    if (!this.playing) return;
    if (this.live && this.speed === 1) {
      this.time = jakartaSecondsOfDay();
    } else {
      this.time = (this.time + elapsed * this.speed) % DAY;
    }
  }

  setTime(seconds: number): void {
    this.time = ((seconds % DAY) + DAY) % DAY;
    this.live = false;
    this.emit();
  }

  goLive(): void {
    this.time = jakartaSecondsOfDay();
    this.speed = 1;
    this.playing = true;
    this.live = true;
    this.emit();
  }

  setSpeed(speed: Speed): void {
    this.speed = speed;
    if (speed !== 1) this.live = false;
    this.emit();
  }

  toggle(): void {
    this.playing = !this.playing;
    if (!this.playing) this.live = false;
    this.emit();
  }

  private emit(): void {
    for (const fn of this.listeners) fn();
  }
}
