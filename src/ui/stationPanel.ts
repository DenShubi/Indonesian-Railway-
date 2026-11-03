/**
 * Departures board for one station, read straight off the timetable.
 */
import { stopName, type Network, type StopCode } from '../data/bundle';
import { formatClock } from '../sim/clock';

const LIMIT = 10;

export function renderStationPanel(net: Network, code: StopCode, time: number): string {
  const { bundle } = net;
  const calls = net.callsByStop.get(code) ?? [];
  const upcoming = calls.filter((call) => call.departure >= time).slice(0, LIMIT);
  const shown = upcoming.length > 0 ? upcoming : calls.slice(0, LIMIT);

  const rows = shown
    .map((call) => {
      const route = bundle.routes[call.trip.r];
      const terminus = call.trip.k[call.trip.k.length - 1][3];
      const isLast = call.idx === call.trip.k.length - 1;
      return (
        `<tr data-action="select-train" data-trip="${call.trip.id}">` +
        `<td class="time">${formatClock(call.departure, false)}</td>` +
        `<td class="route"><span class="chip-dot" style="--chip:${route.color}"></span>${route.name}</td>` +
        `<td class="dest">${isLast ? `terminates (${stopName(bundle, terminus)})` : `for ${call.trip.h}`}</td>` +
        `<td class="num">${call.trip.n}</td>` +
        `</tr>`
      );
    })
    .join('');

  const header = upcoming.length > 0 ? 'Next departures' : 'No more departures today &mdash; first of the day';

  return `
    <div class="panel-head">
      <span>${stopName(bundle, code)} <span class="muted">${code}</span></span>
      <button class="x" type="button" data-action="close" aria-label="Close">&times;</button>
    </div>
    <div class="detail-body">
      <p class="status">${header}</p>
      <table class="calls">
        <tbody>${rows || '<tr><td>no scheduled calls</td></tr>'}</tbody>
      </table>
      <p class="muted small">${calls.length} scheduled calls per day</p>
    </div>`;
}
