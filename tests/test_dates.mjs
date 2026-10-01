import test from 'node:test';
import assert from 'node:assert/strict';
import { addDays, berlinToday, formatDate, isISODate, weekStart } from '../site/date-utils.mjs';

test('calendar validates real dates and week navigation across months', () => {
  assert.equal(isISODate('2026-02-29'), false);
  assert.equal(isISODate('2028-02-29'), true);
  assert.equal(isISODate('2026-09-29'), true);
  assert.equal(isISODate('2026-9-29'), false);
  assert.equal(weekStart('2026-10-04'), '2026-09-28');
  assert.equal(addDays('2026-09-28', 7), '2026-10-05');
  assert.match(formatDate('2026-09-29'), /29\. September 2026/);
});

test('today follows school timezone around midnight and daylight savings', () => {
  assert.equal(berlinToday(new Date('2026-09-29T21:30:00Z')), '2026-09-29');
  assert.equal(berlinToday(new Date('2026-09-29T22:30:00Z')), '2026-09-30');
  assert.equal(berlinToday(new Date('2026-01-01T22:30:00Z')), '2026-01-01');
  assert.equal(berlinToday(new Date('2026-01-01T23:30:00Z')), '2026-01-02');
});
