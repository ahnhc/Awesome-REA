/* Smoke the already adapted Pages artifact at its real project mount. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const puppeteer = require('puppeteer-core');
const root = path.resolve(__dirname, '../..');
const dist = path.resolve(root, process.env.PAGES_DIST || 'dist');
const base = '/Awesome-REA';
const chrome = process.env.CHROME_PATH || ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium'].find(p => fs.existsSync(p));
assert(chrome, 'Chrome is required for Pages deployment verification');
const types = {'.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.svg':'image/svg+xml', '.woff2':'font/woff2', '.png':'image/png'};
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const route = decodeURIComponent(url.pathname);
  if (!route.startsWith(base + '/')) { res.writeHead(404); res.end('Outside project mount'); return; }
  let file = path.resolve(dist, '.' + route.slice(base.length));
  if (!file.startsWith(dist + path.sep) && file !== dist) { res.writeHead(403); res.end(); return; }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
  if (!fs.existsSync(file)) { res.writeHead(404); res.end('Missing file'); return; }
  res.writeHead(200, {'Content-Type': types[path.extname(file)] || 'application/octet-stream'});
  res.end(fs.readFileSync(file));
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await puppeteer.launch({executablePath: chrome, headless: true, args:['--no-sandbox', '--disable-dev-shm-usage']});
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage();
      await page.setViewport({width, height: 900});
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      page.on('response', response => { if (response.url().startsWith(origin) && response.status() >= 400) errors.push(`${response.status()} ${response.url()}`); });
      await page.setRequestInterception(true);
      page.on('request', req => req.url().startsWith(origin) || req.url().startsWith('data:') ? req.continue() : req.abort());
      for (const locale of ['', '/zh']) {
        await page.goto(origin + base + locale + '/', {waitUntil:'networkidle0'});
        assert.equal(await page.$eval('link[rel="canonical"]', n => n.href), 'https://ahnhc.github.io' + base + locale + '/');
        await page.type('[data-search-input]', 'ghidra');
        await page.waitForSelector('[data-cards] > .card');
        assert((await page.$eval('[data-cards] a.stretch', a => a.getAttribute('href'))).startsWith(base + locale + '/resources/'));
        await page.goto(origin + base + locale + '/explore/?q=ghidra#catalog', {waitUntil:'networkidle0'});
        await page.waitForSelector('#resource-grid .resource-card');
        assert((await page.$eval('.resource-entry-link', a => a.getAttribute('href'))).startsWith(base + locale + '/resources/'));
        const other = locale ? 'en' : 'zh';
        const languageURL = await page.$eval(`[data-language-link="${other}"]`, a => a.href);
        assert.equal(new URL(languageURL).searchParams.get('q'), 'ghidra');
        assert.equal(new URL(languageURL).hash, '#catalog');
        assert(new URL(languageURL).pathname === base + (locale ? '' : '/zh') + '/explore/');
        await page.goto(languageURL, {waitUntil:'networkidle0'});
        await page.waitForSelector('#resource-grid .resource-card');
        await page.goBack({waitUntil:'networkidle0'});
        await page.waitForSelector('#resource-grid .resource-card');
        await page.click('#mode-sources');
        await page.waitForSelector('#source-results .source-card');
        const related = await page.$$eval('#source-results .source-card a[href*="/resources/"], #source-results .source-card a[href*="/papers/"]', links => links.map(a => a.getAttribute('href')));
        assert(related.length > 0, 'Related entry links render');
        assert(related.every(href => href.startsWith(base + '/')), 'Related entries stay on the project mount');
        await page.goto(origin + base + locale + '/papers/', {waitUntil:'networkidle0'});
        await page.type('#paper-query', 'reverse');
        await page.waitForSelector('.paper-card:not([hidden])');
        await page.click('.paper-card:not([hidden]) .save-toggle');
        assert.equal(await page.$eval('.papers-shortlist', a => a.getAttribute('href')), base + locale + '/#shortlist');
        await page.goto(origin + base + locale + '/resources/ghidra/', {waitUntil:'networkidle0'});
        assert(await page.$('h1'));
      }
      assert.deepEqual(errors, [], `No client errors or missing local assets at ${width}px`);
      await page.close();
    }
    console.log('Pages browser checks passed: English/Chinese, desktop/mobile, home search, explorer, language switch, Back, repository data, papers and detail pages.');
  } finally { await browser.close(); server.close(); }
})().catch(error => { console.error(error); server.close(); process.exitCode = 1; });
