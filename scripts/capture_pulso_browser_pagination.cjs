/* Observe only requests made by the publisher's public "Ver más" UI.
 * No direct API calls, login, credentials, publishing, or model requests.
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const ORIGIN = 'https://www.latercera.com';
const SURFACES = ['/etiqueta/salud/', '/canal/pulso/', '/canal/nacional/'];
const FEEDS = new Set(['story-feed-tag-fetch', 'story-feed-sections-fetch']);
const QUERY_FIELDS = new Set(['feedOffset', 'feedSize', 'fromComponent', 'tagSlug', 'includeSections', 'arc-site']);
const sha256 = value => crypto.createHash('sha256').update(value).digest('hex');

function publicQuery(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).filter(([key, item]) =>
    QUERY_FIELDS.has(key) && ['string', 'number', 'boolean'].includes(typeof item)));
}

function publicResponseURL(value) {
  let url;
  try { url = new URL(value); } catch { return null; }
  if (url.origin !== ORIGIN || url.username || url.password) return null;
  const source = url.pathname.split('/').at(-1);
  if (!FEEDS.has(source)) return null;
  const safe = new URL(url.origin + url.pathname);
  const omitted = [];
  for (const [key, item] of url.searchParams) {
    if (key === 'query') {
      try { safe.searchParams.append(key, JSON.stringify(publicQuery(JSON.parse(item)))); }
      catch { omitted.push(key); }
    } else if (key === '_website' && item === 'la-tercera') safe.searchParams.append(key, item);
    else if (key === 'd' && /^[a-f\d]+$/i.test(item)) safe.searchParams.append(key, item);
    else omitted.push(key);
  }
  return {url: safe.href, source, omitted_parameter_names: [...new Set(omitted)]};
}

function publicArticleURL(value) {
  if (typeof value !== 'string') return null;
  let url;
  try { url = new URL(value, ORIGIN); } catch { return null; }
  if (url.origin !== ORIGIN || url.username || url.password || !url.pathname.includes('/noticia/')) return null;
  return url.origin + url.pathname;
}

function textElements(elements) {
  if (!Array.isArray(elements)) return [];
  return elements.flatMap(element => {
    if (!element || typeof element !== 'object') return [];
    const result = [];
    if (typeof element.content === 'string') result.push({type: element.type || 'text', content: element.content});
    if (Array.isArray(element.content_elements)) result.push(...textElements(element.content_elements));
    if (Array.isArray(element.items)) result.push(...textElements(element.items));
    if (element.type === 'table' && typeof element.content !== 'string') {
      const rows = Array.isArray(element.rows) ? element.rows : [];
      for (const row of rows) {
        const cells = Array.isArray(row) ? row : row.cells;
        if (Array.isArray(cells)) {
          const content = cells.map(cell => typeof cell === 'string' ? cell : cell.content || '').join(' | ');
          if (content) result.push({type: 'table_row', content});
        }
      }
    }
    return result;
  });
}

function projectArticle(article) {
  if (!article || typeof article !== 'object') return null;
  const url = publicArticleURL(article.websites?.['la-tercera']?.website_url || article.website_url);
  if (!url) return null;
  const taxonomy = article.taxonomy || {};
  const section = item => item && typeof item === 'object' ?
    {path: item.path || null, name: item.name || null, _id: item._id || null} : null;
  return {
    _id: article._id || null, type: article.type || null, url,
    headline: article.headlines?.basic || null,
    subheadline: article.subheadlines?.basic || null,
    description: article.description?.basic || null,
    publish_date: article.publish_date || null,
    display_date: article.display_date || null,
    first_publish_date: article.first_publish_date || null,
    last_updated_date: article.last_updated_date || null,
    primary_section: section(taxonomy.primary_section),
    sections: (taxonomy.sections || []).map(section).filter(Boolean),
    tags: (taxonomy.tags || []).map(item => ({slug: item.slug || null, text: item.text || null})),
    bylines: (article.credits?.by || []).map(item => item.name).filter(item => typeof item === 'string'),
    content_elements: textElements(article.content_elements),
  };
}

function projectFeed(payload) {
  const data = payload?.data && typeof payload.data === 'object' ? payload.data : payload;
  if (!data || !Array.isArray(data.content_elements)) return null;
  return {
    type: data.type || null, count: data.count ?? null, next: data.next ?? null,
    articles: data.content_elements.map(projectArticle).filter(Boolean),
  };
}

function writeJSON(filename, value) {
  fs.mkdirSync(path.dirname(filename), {recursive: true});
  fs.writeFileSync(filename, JSON.stringify(value, null, 2) + '\n');
}

async function run({clicks = 5, output = 'data/audits/pulso_browser_pagination'} = {}) {
  const {chromium} = require('@playwright/test');
  const manifest = {
    schema_version: 1, captured_at: new Date().toISOString(),
    method: 'normal_public_browser_navigation_and_visible_Ver_mas_button',
    scope: 'prototype_pagination_probe_not_a_30_or_90_day_acceptance_claim',
    retention: 'Public article ANS projection, full text, metadata and raw response SHA256; no headers, cookies, credentials, image auth signatures, or private user state.',
    head_sha: process.env.GITHUB_SHA || null,
    surfaces: [], errors: [],
  };
  const browser = await chromium.launch(process.env.PULSO_CHROMIUM_EXECUTABLE ?
    {executablePath: process.env.PULSO_CHROMIUM_EXECUTABLE} : {});
  try {
    for (const surface of SURFACES) {
      const record = {url: ORIGIN + surface, started_at: new Date().toISOString(), initial_cache: [], responses: [], observations: [], errors: []};
      manifest.surfaces.push(record);
      const context = await browser.newContext({viewport: {width: 1280, height: 960}});
      const page = await context.newPage();
      const captures = new Set();
      const pending = new Set();
      let action = 'initial_navigation';
      page.on('response', response => {
        const request = response.request();
        const observed = publicResponseURL(response.url());
        if (!observed || request.method() !== 'GET' || !['xhr', 'fetch'].includes(request.resourceType())) return;
        const observedAction = action;
        const task = (async () => {
          const raw = await response.body();
          const digest = sha256(raw);
          const signature = observed.url + '|' + digest;
          if (captures.has(signature)) return;
          captures.add(signature);
          let feed = null;
          try { feed = projectFeed(JSON.parse(raw.toString('utf8'))); } catch { /* Non-JSON response is an observed failure. */ }
          const index = record.responses.length;
          const relative = `responses/${surface.split('/').filter(Boolean).join('_')}_${index}.json`;
          const evidence = {...observed, action: observedAction, captured_at: new Date().toISOString(),
            status: response.status(), raw_sha256: digest, raw_bytes: raw.length,
            projected_json_file: relative, feed};
          writeJSON(path.join(output, relative), evidence);
          record.responses.push({...evidence, feed: feed ? {count: feed.count, next: feed.next, article_count: feed.articles.length,
            articles: feed.articles.map(({content_elements, ...article}) => ({...article, content_element_count: content_elements.length}))} : null});
        })().catch(error => record.errors.push({action: observedAction, reason: 'response_capture_failed', error: error.message}));
        pending.add(task);
        task.finally(() => pending.delete(task));
      });
      const domURLs = () => page.locator('a[href*="/noticia/"]').evaluateAll(nodes => [...new Set(nodes.map(node => node.href))]);
      try {
        await page.goto(record.url, {waitUntil: 'domcontentloaded', timeout: 60000});
        record.final_url = page.url().split('?')[0];
        await page.waitForTimeout(1500);
        const consent = page.getByRole('button', {name: /^(Aceptar|Aceptar todas|Acepto)$/i});
        if (await consent.count() === 1 && await consent.isVisible()) {
          await consent.click({timeout: 5000});
          record.consent_dismissed_with_visible_public_button = true;
        }
        const initial = await page.evaluate(() => {
          const cache = globalThis.Fusion?.contentCache || {};
          return Object.entries(cache).filter(([source]) => ['story-feed-tag-fetch', 'story-feed-sections-fetch'].includes(source))
            .flatMap(([source, entries]) => Object.entries(entries || {}).map(([query, item]) => ({source, query, data: item.data})));
        });
        for (const entry of initial) {
          let query = {};
          try { query = publicQuery(JSON.parse(entry.query)); } catch { /* Explicit invalid query below. */ }
          const feed = projectFeed(entry.data);
          if (!feed) continue;
          const relative = `initial/${surface.split('/').filter(Boolean).join('_')}_${record.initial_cache.length}.json`;
          writeJSON(path.join(output, relative), {source: entry.source, query, feed, captured_at: new Date().toISOString(), origin: record.url});
          record.initial_cache.push({source: entry.source, query, projected_json_file: relative, count: feed.count, next: feed.next,
            article_count: feed.articles.length, dates: feed.articles.map(article => article.publish_date)});
        }
        const initialURLs = (await domURLs()).map(publicArticleURL).filter(Boolean);
        const unique = new Set(initialURLs);
        record.observations.push({action: 'initial_navigation', unique_article_urls: unique.size, article_urls: initialURLs});
        for (let index = 1; index <= clicks; index++) {
          action = `visible_Ver_mas_click_${index}`;
          const button = page.locator('button.result-list__see-more').filter({hasText: /^Ver más$/});
          if (await button.count() !== 1 || !await button.isVisible()) {
            record.errors.push({action, reason: 'visible_public_pagination_button_missing_or_ambiguous'});
            break;
          }
          const before = unique.size;
          const beforeResponses = record.responses.length;
          await button.click({timeout: 20000});
          try {
            await page.waitForFunction(prior => new Set([...document.querySelectorAll('a[href*="/noticia/"]')].map(node => node.href)).size > prior, before,
              {timeout: 20000});
          } catch {
            record.errors.push({action, reason: 'no_observed_DOM_inventory_growth_within_20_seconds'});
          }
          await page.waitForTimeout(1000);
          await Promise.all([...pending]);
          const urls = (await domURLs()).map(publicArticleURL).filter(Boolean);
          const added = urls.filter(url => !unique.has(url));
          urls.forEach(url => unique.add(url));
          record.observations.push({action, unique_article_urls: unique.size, added_article_urls: [...new Set(added)],
            new_captured_responses: record.responses.length - beforeResponses});
          if (unique.size === before) break;
        }
        record.unique_article_urls = [...unique];
      } catch (error) {
        record.errors.push({action, reason: 'normal_browser_action_failed', error: error.message});
      } finally {
        await Promise.all([...pending]);
        record.completed_at = new Date().toISOString();
        await context.close();
        writeJSON(path.join(output, 'manifest.json'), manifest);
      }
    }
  } finally {
    await browser.close();
    manifest.completed_at = new Date().toISOString();
    manifest.response_count = manifest.surfaces.reduce((sum, surface) => sum + surface.responses.length, 0);
    manifest.inventory_growth_surfaces = manifest.surfaces.filter(surface => surface.observations.some(item => item.added_article_urls?.length)).length;
    writeJSON(path.join(output, 'manifest.json'), manifest);
  }
  console.log(JSON.stringify({response_count: manifest.response_count, inventory_growth_surfaces: manifest.inventory_growth_surfaces,
    surfaces: manifest.surfaces.map(surface => ({url: surface.url, responses: surface.responses.length, observations: surface.observations.map(item => ({action: item.action, unique_article_urls: item.unique_article_urls})), errors: surface.errors}))}, null, 2));
  return manifest;
}

module.exports = {publicQuery, publicResponseURL, publicArticleURL, textElements, projectArticle, projectFeed, run};
if (require.main === module) {
  const args = process.argv.slice(2);
  const clicksAt = args.indexOf('--clicks');
  const outputAt = args.indexOf('--output');
  const clicks = clicksAt >= 0 ? Number(args[clicksAt + 1]) : 5;
  if (!Number.isInteger(clicks) || clicks < 1 || clicks > 200) throw new Error('clicks must be an integer from 1 to 200');
  run({clicks, output: outputAt >= 0 ? args[outputAt + 1] : undefined}).catch(error => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
