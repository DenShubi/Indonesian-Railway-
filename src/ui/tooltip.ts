/**
 * The hover card over a train, after Mini Tokyo 3D's: the line's colour down one
 * edge, then the line, the service, where it has just been and where it is going.
 */
import { stopName, type Network } from '../data/bundle';
import { formatClock } from '../sim/clock';
import type { TrainState } from '../sim/trains';

export interface TrainTooltip {
  /** Place the card above (x, y), in pixels within the map canvas. */
  show(state: TrainState, x: number, y: number): void;
  hide(): void;
}

function esc(text: string): string {
  return text.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`);
}

export function initTooltip(net: Network): TrainTooltip {
  const el = document.getElementById('tooltip') as HTMLElement;
  const { bundle } = net;
  let signature = '';

  function markup(state: TrainState): string {
    const route = bundle.routes[state.trip.r];
    const frames = state.trip.k;
    const rows: string[] = [];

    if (state.dwelling) {
      rows.push(
        `<div class="tip-row"><span class="muted">At:</span> ${esc(stopName(bundle, state.toStop))} ` +
          `${formatClock(frames[state.nextIndex][1], false)}</div>`,
      );
      const after = frames[state.nextIndex + 1];
      if (after) {
        rows.push(
          `<div class="tip-row"><span class="muted">Next stop:</span> ${esc(stopName(bundle, after[3]))} ` +
            `${formatClock(after[0], false)}</div>`,
        );
      }
    } else {
      const previous = frames[state.nextIndex - 1];
      if (previous) {
        rows.push(
          `<div class="tip-row"><span class="muted">Previous stop:</span> ${esc(stopName(bundle, previous[3]))} ` +
            `${formatClock(previous[1], false)}</div>`,
        );
      }
      rows.push(
        `<div class="tip-row"><span class="muted">Next stop:</span> ${esc(stopName(bundle, state.toStop))} ` +
          `${formatClock(state.toArrival, false)}</div>`,
      );
    }

    return (
      `<div class="tip-line">${esc(route.name)}</div>` +
      `<div class="tip-row"><span class="badge">Commuter</span> for ${esc(state.trip.h)}</div>` +
      `<div class="tip-row"><span class="muted">Train number:</span> ${esc(state.trip.n)}</div>` +
      rows.join('')
    );
  }

  return {
    show(state, x, y) {
      const route = bundle.routes[state.trip.r];
      // Rebuilt only when the content would actually differ: this runs on every
      // mouse move over the fleet.
      const next = `${state.trip.id}:${state.nextIndex}:${state.dwelling}`;
      if (next !== signature) {
        signature = next;
        el.style.setProperty('--chip', route.color);
        el.innerHTML = markup(state);
      }
      const width = el.parentElement?.clientWidth ?? 0;
      el.style.left = `${Math.min(Math.max(x, 140), Math.max(width - 140, 140))}px`;
      el.style.top = `${y - 16}px`;
      el.hidden = false;
    },
    hide() {
      el.hidden = true;
      signature = '';
    },
  };
}
