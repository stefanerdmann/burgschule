export function isISODate(value) {
  if (typeof value !== 'string' || !/^20\d\d-\d\d-\d\d$/.test(value)) return false;
  const date = new Date(`${value}T12:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function addDays(value, count) {
  const date = new Date(`${value}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + count);
  return date.toISOString().slice(0, 10);
}

export function nextWeekday(value) {
  const weekday = new Date(`${value}T12:00:00Z`).getUTCDay();
  return addDays(value, weekday === 6 ? 2 : weekday === 0 ? 1 : 0);
}

export function weekStart(value) {
  const day = new Date(`${value}T12:00:00Z`).getUTCDay();
  return addDays(value, -(day === 0 ? 6 : day - 1));
}

export function berlinToday(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Berlin', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now);
  const get = (type) => parts.find((part) => part.type === type).value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}

export function formatDate(value, options = { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) {
  return new Intl.DateTimeFormat('de-DE', { timeZone: 'UTC', ...options })
    .format(new Date(`${value}T12:00:00Z`));
}
