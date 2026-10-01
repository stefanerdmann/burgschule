import { addDays, berlinToday, formatDate, isISODate, nextWeekday, weekStart } from './date-utils.mjs';

const $ = (id) => document.getElementById(id);
const menu = $('menu');
const supplied = new URLSearchParams(location.search).get('tag');
const today = berlinToday();
const selected = nextWeekday(isISODate(supplied) ? supplied : today);
const state = {
  data: null, today, homeDay: nextWeekday(today), selected,
  week: weekStart(selected), screen: 'day', offlineCopy: false, loadError: false,
};
// Existing weekend links lead to Monday, never to a weekend meal.
if (isISODate(supplied) && supplied !== selected) {
  const url = new URL(location.href);
  url.searchParams.set('tag', selected);
  window.history.replaceState({}, '', url);
}

function schoolLink(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.hostname === 'burgschule-nieder-olm.de' ? url.href : null;
  } catch { return null; }
}

function weeks() {
  return [...new Set([state.homeDay, state.selected,
    ...Object.keys(state.data?.days || {}).filter((day) => nextWeekday(day) === day)]
    .map(weekStart))].sort();
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function showScreen(screen) {
  state.screen = screen;
  if (screen === 'week') state.week = weekStart(state.selected);
  for (const name of ['day', 'week', 'info']) $(`screen-${name}`).hidden = name !== screen;
  for (const button of document.querySelectorAll('.tab')) {
    const active = button.dataset.screen === screen;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  }
  if (screen === 'week') renderWeek();
  window.scrollTo?.({ top: 0, behavior: 'auto' });
}

function navigate(day, historyMode = 'push') {
  if (!isISODate(day)) return;
  const weekday = nextWeekday(day);
  const fromWeekendLink = weekday !== day;
  if (fromWeekendLink && historyMode === 'none') historyMode = 'replace';
  day = weekday;
  const changed = day !== state.selected;
  state.selected = day;
  state.week = weekStart(day);
  if (historyMode !== 'none' && (changed || historyMode === 'replace')) {
    const url = new URL(location.href);
    if (day === state.homeDay && !fromWeekendLink) url.searchParams.delete('tag');
    else url.searchParams.set('tag', day);
    window.history[historyMode === 'replace' ? 'replaceState' : 'pushState']({}, '', url);
  }
  showScreen('day');
  render();
}

function dayStatus(day) {
  const status = state.data?.days[day]?.status;
  if (status === 'ok') return 'Plan vorhanden';
  if (status === 'uncertain') return 'Eintrag nicht eindeutig';
  return 'Kein Speiseplan';
}

function renderStrip() {
  const current = weekStart(state.selected);
  const list = $('days');
  list.replaceChildren(...Array.from({ length: 5 }, (_, offset) => {
    const day = addDays(current, offset);
    const button = element('button', `day${state.data?.days[day]?.status === 'ok' ? ' available' : ''}${day === state.selected ? ' selected' : ''}${day === state.today ? ' today' : ''}`);
    button.type = 'button';
    button.setAttribute('aria-label', `${formatDate(day)}, ${dayStatus(day)}`);
    if (day === state.selected) button.setAttribute('aria-current', 'date');
    button.append(element('span', 'day-name', formatDate(day, { weekday: 'short' })), element('span', 'day-number', String(Number(day.slice(-2)))));
    button.addEventListener('click', () => navigate(day));
    return button;
  }));
  // Keep the selected day visible on especially narrow screens.
  const selected = list.querySelector('.selected');
  if (selected) list.scrollLeft = Math.max(0, selected.offsetLeft - list.offsetLeft - (list.clientWidth - selected.clientWidth) / 2);
}

function renderWeek() {
  const items = weeks();
  const index = items.indexOf(state.week);
  const range = (week) => `${formatDate(week, { day: 'numeric', month: 'short' })} – ${formatDate(addDays(week, 4), { day: 'numeric', month: 'short', year: 'numeric' })}`;
  $('week-range').textContent = range(state.week);
  $('previous-week').disabled = index <= 0;
  $('next-week').disabled = index >= items.length - 1;
  const select = $('week-select');
  select.replaceChildren(...items.map((week) => {
    const option = element('option', '', range(week));
    option.value = week;
    return option;
  }));
  select.value = state.week;
  $('week-days').replaceChildren(...Array.from({ length: 5 }, (_, offset) => {
    const day = addDays(state.week, offset);
    const row = element('button', `week-day${day === state.today ? ' today' : ''}`);
    row.type = 'button';
    row.setAttribute('aria-label', `${formatDate(day)}, ${dayStatus(day)}, anzeigen`);
    const date = element('span', 'week-day-date');
    date.append(element('strong', '', formatDate(day, { weekday: 'long' })), element('small', '', formatDate(day, { day: 'numeric', month: 'long' })));
    const status = element('span', `week-day-status${state.data?.days[day]?.status === 'ok' ? ' available' : ''}`, dayStatus(day));
    row.append(date, status, element('span', 'chevron', '›'));
    row.addEventListener('click', () => navigate(day));
    return row;
  }));
}

function card(title, dish, variant, note) {
  const article = element('article', `menu-card ${variant}`);
  article.append(element('h2', '', title), element('p', '', dish));
  if (note) article.append(element('p', 'reference', note));
  return article;
}

function empty(title, details) {
  const box = element('div', 'empty-card');
  box.append(element('strong', '', title), element('p', '', details));
  return box;
}

function renderDaily() {
  const home = state.selected === state.homeDay;
  const weekend = state.homeDay !== state.today;
  $('view-title').textContent = home ? (weekend ? 'Nächster Montag' : 'Heute') : formatDate(state.selected, { weekday: 'long' });
  $('day-tab-label').textContent = weekend ? 'Montag' : 'Heute';
  $('today').textContent = weekend ? 'Zum Montag' : 'Heute';
  const selectedDate = $('selected-date');
  selectedDate.textContent = formatDate(state.selected, { day: 'numeric', month: 'long', year: 'numeric' });
  selectedDate.dateTime = state.selected;
  $('today').hidden = home;
  const entry = state.data?.days[state.selected];
  if (entry?.status === 'ok') {
    menu.replaceChildren(
      card('Menü I · Vollkost', entry.menu_i, 'full'),
      card('Menü II · vegetarisch', entry.menu_ii, 'vegetarian', entry.menu_ii_from_i ? 'Im Original: „siehe Menü I“' : ''),
      card('Dessert', entry.dessert, 'dessert'),
    );
  } else if (entry?.status === 'uncertain') {
    menu.replaceChildren(empty('Für diesen Tag kein verlässlich ausgelesener Plan', 'Die Angaben im PDF sind nicht eindeutig zuzuordnen. Bitte das Original-PDF öffnen.'));
  } else if (state.loadError) {
    menu.replaceChildren(empty('Speiseplan gerade nicht verfügbar', 'Bitte später erneut versuchen oder den Speiseplan auf der Schulwebsite öffnen.'));
  } else {
    menu.replaceChildren(empty('Kein Eintrag für diesen Tag', 'Es liegt für dieses Datum kein verlässlich ausgelesener Plan vor. Bitte die Schulwebsite prüfen oder einen anderen Tag auswählen.'));
  }

  const provenance = $('provenance');
  provenance.replaceChildren();
  const sources = state.data?.sources || {};
  const source = entry?.source && sources[entry.source]
    ? sources[entry.source]
    : Object.values(sources).sort((a, b) => b.end.localeCompare(a.end))[0];
  const checked = state.data?.checked_at ? new Date(state.data.checked_at) : null;
  if (checked && !Number.isNaN(checked.getTime())) {
    const label = `Daten zuletzt geprüft: ${new Intl.DateTimeFormat('de-DE', { timeZone: 'Europe/Berlin', dateStyle: 'medium', timeStyle: 'short' }).format(checked)} Uhr.`;
    provenance.append(element('p', '', label));
    $('info-status').textContent = label;
  } else $('info-status').textContent = 'Kein Prüfzeitpunkt verfügbar.';
  if (source) {
    provenance.append(element('p', '', `Originalplan: ${formatDate(source.start, { day: 'numeric', month: 'numeric', year: 'numeric' })} – ${formatDate(source.end, { day: 'numeric', month: 'numeric', year: 'numeric' })}.`));
  }
  const pdf = source?.url || state.data?.fallback_pdf?.url;
  const href = schoolLink(pdf || state.data?.school_url || 'https://burgschule-nieder-olm.de/aktuelles/');
  if (href) {
    const link = element('a', '', pdf ? 'Original-PDF bei der Schule öffnen ↗' : 'Speiseplan auf der Schulwebsite prüfen ↗');
    link.href = href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    provenance.append(link);
  }
}

function renderConnection() {
  const banner = $('connection');
  const checked = state.data?.checked_at ? Date.parse(state.data.checked_at) : NaN;
  const old = !Number.isNaN(checked) && Date.now() - checked > 3 * 86400000;
  banner.hidden = !(state.offlineCopy || !navigator.onLine || old || state.loadError);
  if (!banner.hidden) {
    banner.textContent = state.loadError ? 'Der Plan konnte nicht geladen werden. Bitte das Original auf der Schulwebsite prüfen.'
      : state.offlineCopy || !navigator.onLine ? 'Offline: Es wird der zuletzt geladene Datenstand angezeigt. Änderungen sind möglicherweise noch nicht enthalten.'
        : 'Dieser Datenstand wurde seit mehr als drei Tagen nicht aktualisiert. Bitte das Original-PDF prüfen.';
  }
}

function render() {
  renderConnection();
  renderStrip();
  renderWeek();
  renderDaily();
}

$('previous-week').addEventListener('click', () => {
  const items = weeks();
  state.week = items[items.indexOf(state.week) - 1] || state.week;
  renderWeek();
});
$('next-week').addEventListener('click', () => {
  const items = weeks();
  state.week = items[items.indexOf(state.week) + 1] || state.week;
  renderWeek();
});
$('week-select').addEventListener('change', (event) => {
  if (weeks().includes(event.target.value)) {
    state.week = event.target.value;
    renderWeek();
  }
});
$('open-week').addEventListener('click', () => showScreen('week'));
$('today').addEventListener('click', () => navigate(state.homeDay));
for (const button of document.querySelectorAll('.tab')) {
  button.addEventListener('click', () => button.dataset.screen === 'day' ? navigate(state.homeDay) : showScreen(button.dataset.screen));
}
window.addEventListener('popstate', () => {
  const day = new URLSearchParams(location.search).get('tag');
  navigate(isISODate(day) ? day : state.homeDay, 'none');
});
window.addEventListener('online', renderConnection);
window.addEventListener('offline', renderConnection);
setInterval(() => {
  const current = berlinToday();
  if (current !== state.today) {
    const wasHome = state.selected === state.homeDay;
    state.today = current;
    state.homeDay = nextWeekday(current);
    if (wasHome) navigate(state.homeDay, 'replace');
    else render();
  }
}, 60_000);

try {
  const response = await fetch('./data/menu.json', { cache: 'no-store' });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  state.offlineCopy = response.headers.get('X-Offline-Copy') === 'yes';
  const data = await response.json();
  if (data.schema !== 1 || !data.days || !data.sources) throw new Error('Unbekanntes Datenformat');
  state.data = data;
} catch (error) {
  console.error('Speiseplan konnte nicht geladen werden:', error);
  state.loadError = true;
}
render();
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('./sw.js').catch((error) => console.warn('Offline-Modus nicht verfügbar:', error));
}
