import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { Window } from 'happy-dom';

test('mobile app renders dishes, blocks uncertain days and navigates dates', async () => {
  const html = await readFile(new URL('../site/index.html', import.meta.url), 'utf8');
  // UI fixture is independent of the live PDF; tests must still pass after the
  // real 2026 plan expires and the published JSON is intentionally emptied.
  const url = 'https://burgschule-nieder-olm.de/wp-content/uploads/plan.pdf';
  const data = {
    schema: 1, checked_at: new Date().toISOString(), sources: {
      [url]: { url, start: '2026-08-10', end: '2026-10-02' },
    },
    days: {
      '2026-08-12': { status: 'uncertain', source: url },
      '2026-09-21': { status: 'ok', source: url, menu_i: 'Suppe', menu_ii: 'Suppe', dessert: 'Birne' },
      '2026-09-29': { status: 'ok', source: url, menu_i: 'Gyros aus der Hühnerbrust', menu_ii: 'Vegetarisches Gyros', dessert: 'Tafeltrauben' },
    },
  };
  const window = new Window({ url: 'https://example.org/?tag=2026-09-29', settings: { disableJavaScriptEvaluation: true } });
  window.document.write(html);
  const oldInterval = globalThis.setInterval;
  try {
    Object.defineProperties(globalThis, {
      document: { configurable: true, value: window.document },
      window: { configurable: true, value: window },
      location: { configurable: true, value: window.location },
      navigator: { configurable: true, value: window.navigator },
      fetch: { configurable: true, value: async () => new Response(JSON.stringify(data), { status: 200 }) },
      setInterval: { configurable: true, value: () => 0 },
    });
    await import('../site/app.mjs');
    assert.match(window.document.querySelector('#menu').textContent, /Gyros aus der Hühnerbrust/);
    assert.match(window.document.querySelector('#menu').textContent, /Vegetarisches Gyros/);
    assert.match(window.document.querySelector('#menu').textContent, /Tafeltrauben/);
    assert.equal(window.document.querySelector('#screen-week').hidden, true);
    assert.equal(window.document.querySelector('#screen-info').hidden, true);
    assert.equal(window.document.querySelector('.tab[data-screen="day"]').getAttribute('aria-current'), 'page');
    assert.match(window.document.querySelector('#provenance a').href, /^https:\/\/burgschule-nieder-olm.de\//);

    window.document.querySelectorAll('.day')[6].click();
    assert.equal(new URL(window.location.href).searchParams.get('tag'), '2026-10-04');
    assert.match(window.document.querySelector('#menu').textContent, /Wochenende/);
    window.document.querySelector('#open-week').click();
    assert.equal(window.document.querySelector('#screen-day').hidden, true);
    assert.equal(window.document.querySelector('#screen-week').hidden, false);
    assert.equal(window.document.querySelector('#week-select').value, '2026-09-28');
    window.document.querySelector('#previous-week').click();
    assert.equal(window.document.querySelector('#week-select').value, '2026-09-21');
    assert.equal(new URL(window.location.href).searchParams.get('tag'), '2026-10-04');
    window.document.querySelector('#week-days .week-day').click();
    assert.equal(new URL(window.location.href).searchParams.get('tag'), '2026-09-21');
    assert.equal(window.document.querySelector('#screen-day').hidden, false);
    assert.match(window.document.querySelector('#menu').textContent, /Suppe/);

    window.document.querySelector('.tab[data-screen="week"]').click();
    window.document.querySelector('#week-select').value = '2026-08-10';
    window.document.querySelector('#week-select').dispatchEvent(new window.Event('change'));
    const blocked = [...window.document.querySelectorAll('#week-days .week-day')].find((day) => day.textContent.includes('12. August'));
    blocked.click();
    assert.equal(new URL(window.location.href).searchParams.get('tag'), '2026-08-12');
    assert.match(window.document.querySelector('#menu').textContent, /kein verlässlich ausgelesener Plan/);
    assert.ok(!window.document.querySelector('#menu').textContent.includes('Putenmedaillon'));

    window.document.querySelector('.tab[data-screen="info"]').click();
    assert.equal(window.document.querySelector('#screen-info').hidden, false);
    assert.ok(window.document.querySelector('#screen-day').hidden);
    assert.ok(window.document.querySelector('.tab[data-screen="info"]').hasAttribute('aria-current'));
    assert.ok(window.document.querySelector('a[href="./impressum.html"]'));
    window.document.querySelector('.tab[data-screen="day"]').click();
    assert.equal(window.document.querySelector('#screen-day').hidden, false);
    assert.equal(new URL(window.location.href).searchParams.has('tag'), false);
  } finally {
    globalThis.setInterval = oldInterval;
    window.close();
  }
});
