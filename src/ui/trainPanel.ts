/**
 * Detail card for one selected train: where it is now and its whole call list.
 */
import { stopName, type Network } from '../data/bundle';
import { formatClock } from '../sim/clock';
import type { TrainState } from '../sim/trains';

function relative(seconds: number): string {
  const mins = Math.round(seconds / 60);
  if (mins <= 0) return 'now';
  if (mins === 1) return 'in 1 min';
  if (mins < 60) return `in ${mins} min`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m ? `in ${h} h ${m} min` : `in ${h} h`;
}

export function renderTrainPanel(net: Network, state: TrainState, time: number, follow: boolean): string {
  const { bundle } = net;
  const route = bundle.routes[state.trip.r];
  const frames = state.trip.k;
  const last = frames[frames.length - 1];
  const progress = last[2] > 0 ? (state.distance / last[2]) * 100 : 0;

  const status = state.dwelling
    ? `At <strong>${stopName(bundle, state.toStop)}</strong>`
    : `Next stop <strong>${stopName(bundle, state.toStop)}</strong> ` +
      `<span class="muted">${formatClock(state.toArrival, false)} &middot; ${relative(state.toArrival - time)}</span>`;

  const rows = frames
    .map((frame, index) => {
      const [arrival, departure, distance, code] = frame;
      const done = index < state.nextIndex || (index === state.nextIndex && state.dwelling);
      const current = index === state.nextIndex;
      const times =
        arrival === departure
          ? formatClock(arrival, false)
          : `${formatClock(arrival, false)} &ndash; ${formatClock(departure, false)}`;
      return (
        `<tr class="${done ? 'is-done' : ''}${current ? ' is-current' : ''}">` +
        `<td class="stop">${stopName(bundle, code)}</td>` +
        `<td class="time">${times}</td>` +
        `<td class="km">${distance.toFixed(1)}</td>` +
        `</tr>`
      );
    })
    .join('');

  return `
    <div class="panel-head" style="--chip:${route.color}">
      <span class="chip-dot"></span>
      <span>${route.name} &middot; Train ${state.trip.n}</span>
      <button class="x" type="button" data-action="close" aria-label="Close">&times;</button>
    </div>
    <div class="detail-body">
      <p class="headsign">for ${state.trip.h}</p>
      <p class="status">${status}</p>
      <div class="progress"><span style="width:${progress.toFixed(1)}%;background:${route.color}"></span></div>
      <p class="muted small">${state.distance.toFixed(1)} of ${last[2].toFixed(1)} km &middot;
        ${formatClock(frames[0][1], false)} &rarr; ${formatClock(last[0], false)}</p>
      <button class="btn btn-wide${follow ? ' is-active' : ''}" type="button" data-action="follow">
        ${follow ? 'Stop following' : 'Follow this train'}
      </button>
      <table class="calls">
        <thead><tr><th>Stop</th><th>Time</th><th>km</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}
