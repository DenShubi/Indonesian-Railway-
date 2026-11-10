/**
 * The header: clock, train count, play/pause, speed and the time-of-day scrubber.
 */
import type { BundleRegion } from '../data/bundle';
import { formatClock, SPEEDS, type Speed, type ServiceClock } from '../sim/clock';

export interface Hud {
  /**
   * Called every frame; cheap enough to run at frame rate. `nextDeparture` is the
   * time of day service resumes, used only while nothing is running.
   */
  sync(trainCount: number, nextDeparture: number | null): void;
  /** Retitle the header for the selected network, or null for all of Java. */
  setRegion(region: BundleRegion | null): void;
}

export function initHud(clock: ServiceClock): Hud {
  const clockEl = document.getElementById('clock') as HTMLElement;
  const countEl = document.getElementById('train-count') as HTMLElement;
  const playEl = document.getElementById('play') as HTMLButtonElement;
  const nowEl = document.getElementById('now') as HTMLButtonElement;
  const speedsEl = document.getElementById('speeds') as HTMLElement;
  const scrubEl = document.getElementById('scrub') as HTMLInputElement;
  const titleEl = document.querySelector('.hud-title') as HTMLElement;
  const subEl = document.querySelector('.hud-sub') as HTMLElement;

  // The whole day, not just the service window: trains that run past midnight are
  // out there in the small hours, and the scrubber has to be able to reach them.
  scrubEl.min = '0';
  scrubEl.max = String(24 * 3600);

  for (const speed of SPEEDS) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-speed';
    button.dataset['speed'] = String(speed);
    button.textContent = `${speed}x`;
    button.addEventListener('click', () => clock.setSpeed(speed as Speed));
    speedsEl.append(button);
  }

  playEl.addEventListener('click', () => clock.toggle());
  nowEl.addEventListener('click', () => clock.goLive());

  let scrubbing = false;
  scrubEl.addEventListener('pointerdown', () => {
    scrubbing = true;
  });
  scrubEl.addEventListener('pointerup', () => {
    scrubbing = false;
  });
  scrubEl.addEventListener('input', () => clock.setTime(Number(scrubEl.value)));

  let lastText = '';
  return {
    setRegion(region: BundleRegion | null) {
      titleEl.textContent = region ? `${region.name} Commuter Line` : 'Java Commuter Lines';
      subEl.textContent = region
        ? `${region.subtitle} · scheduled positions, not live GPS`
        : 'All regions · scheduled positions, not live GPS';
    },
    sync(trainCount: number, nextDeparture: number | null) {
      const text = formatClock(clock.time);
      if (text !== lastText) {
        clockEl.textContent = text;
        lastText = text;
      }
      if (trainCount === 0) {
        countEl.textContent = nextDeparture === null
          ? 'no trains running'
          : `no trains running · next at ${formatClock(nextDeparture, false)}`;
      } else {
        countEl.textContent =
          trainCount === 1 ? '1 train running' : `${trainCount} trains running`;
      }
      countEl.classList.toggle('is-live', clock.live && clock.playing);
      playEl.textContent = clock.playing ? 'Pause' : 'Play';
      playEl.setAttribute('aria-label', clock.playing ? 'Pause' : 'Play');
      nowEl.classList.toggle('is-active', clock.live);
      for (const button of speedsEl.children) {
        button.classList.toggle('is-active', button.getAttribute('data-speed') === String(clock.speed));
      }
      if (!scrubbing) scrubEl.value = String(Math.round(clock.time));
    },
  };
}
