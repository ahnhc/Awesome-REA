# GitHub Pages fork

The independent project site is https://ahnhc.github.io/Awesome-REA/.
The original collection and website are maintained at
https://github.com/reacher-z/Awesome-REA and https://awesomerea.org/.
The original MIT license, copyright and source attribution remain unchanged.

## Build and deploy

Set repository **Settings → Pages → Source** to **GitHub Actions**. Leave the
custom domain empty. Enable Actions only after the fork guards in this commit
are on `main`. `Deploy GitHub Pages` runs on pushes to `main` and can also be
started manually. Its deployment job only has `pages: write` and `id-token: write`;
checkout credentials are not persisted. Inherited automation jobs are restricted
to the original repository, including scheduled scans, issue/PR automation,
link checks and search-engine notifications.

To reproduce the deployment:

```sh
python3 scripts/build_production.py
python3 -m unittest tests.test_github_pages -v
python3 scripts/build_github_pages.py
npm ci --prefix tests/browser --ignore-scripts
node tests/browser/github-pages.cjs
```

The upstream production validation runs before adaptation. The separate Pages
step changes generated internal URLs, client routes, asset fingerprints,
canonical URLs, feeds and sitemaps for the project path. It rebuilds download
ZIPs and their checksums, API checksums and the deployment manifest. It checks
every generated HTML page's root-relative links and asset fingerprints.
The browser test serves only `/Awesome-REA/`, so accidental host-root fetches
fail rather than silently passing.

Catalog source files and upstream generators are kept unchanged. Run a fresh
production build before each adaptation. Do not run the upstream domain-specific
site validator against the adapted artifact; the Pages checks cover that artifact.

GitHub Pages does not apply Cloudflare `_headers` or `_redirects`. The adapter
removes those files, the original CNAME and site-verification tokens, and writes
static redirect pages for the original directory aliases. GitHub Pages controls
response headers. A project-level robots.txt cannot control crawling of the
account's host root; sitemaps and page metadata contain the project URLs.
