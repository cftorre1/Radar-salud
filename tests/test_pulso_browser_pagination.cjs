'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {publicResponseURL, projectFeed} = require('../scripts/capture_pulso_browser_pagination.cjs');

test('captures observed public feed query without unknown credentials or foreign endpoints', () => {
  const query = encodeURIComponent(JSON.stringify({feedOffset: 24, feedSize: 12, tagSlug: 'salud', credential: 'secret'}));
  const result = publicResponseURL(`https://www.latercera.com/pf/api/v3/content/fetch/story-feed-tag-fetch?query=${query}&_website=la-tercera&token=secret`);
  assert.deepEqual(JSON.parse(new URL(result.url).searchParams.get('query')), {feedOffset: 24, feedSize: 12, tagSlug: 'salud'});
  assert.deepEqual(result.omitted_parameter_names, ['token']);
  assert.ok(!JSON.stringify(result).includes('secret'));
  assert.equal(publicResponseURL('https://www.latercera.com/pf/api/v3/private/account?token=secret'), null);
  assert.equal(publicResponseURL('https://evil.test/story-feed-tag-fetch?query={}'), null);
});

test('preserves all publisher story text and dates without image auth or author email', () => {
  const feed = projectFeed({count: 500, next: 36, content_elements: [{
    _id: 'ARTICLE', websites: {'la-tercera': {website_url: '/politica/noticia/presupuesto/'}},
    headlines: {basic: 'Presupuesto nacional'}, publish_date: '2026-07-20T12:00:00Z',
    taxonomy: {primary_section: {name: 'Política', path: '/politica'}, tags: [{slug: 'salud', text: 'Salud'}]},
    credits: {by: [{name: 'Periodista', email: 'private@example.test'}]},
    content_elements: [{type: 'text', content: 'Incluye hospitales.'}, {type: 'list', items: [{type: 'text', content: 'Financiamiento.'}]},
      {type: 'image', auth: {1: 'private-image-signature'}}],
  }]});
  assert.equal(feed.next, 36);
  assert.equal(feed.articles.length, 1);
  assert.deepEqual(feed.articles[0].content_elements, [{type: 'text', content: 'Incluye hospitales.'}, {type: 'text', content: 'Financiamiento.'}]);
  assert.equal(feed.articles[0].publish_date, '2026-07-20T12:00:00Z');
  assert.equal(feed.articles[0].url, 'https://www.latercera.com/politica/noticia/presupuesto/');
  assert.ok(!JSON.stringify(feed).includes('private'));
});
