#!/usr/bin/env python3
"""Adapt a validated upstream build for a GitHub Pages project (no custom domain).

Run build_production.py first. This deployment-only step leaves catalog sources,
upstream generators, attribution and their original validation contracts intact.
"""
from __future__ import annotations

import argparse
import hashlib
from html import escape
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import shutil
from urllib.parse import unquote, urlsplit
import zipfile

from build_manifest import write_build_manifest, read_build_manifest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = 'https://awesomerea.org'
DEFAULT_URL = 'https://ahnhc.github.io/Awesome-REA'
TEXT = {'.html', '.css', '.js', '.json', '.jsonl', '.xml', '.txt', '.md', '.csv', '.svg', '.bib'}
HASHED = re.compile(r'^(.*)\.[a-f0-9]{16}(\.(?:css|js|json))$')


def profile(site_url):
    url = urlsplit(site_url.rstrip('/'))
    if url.scheme != 'https' or not url.hostname or not url.hostname.endswith('.github.io') or url.query or url.fragment:
        raise ValueError('Use an HTTPS github.io project URL, without query or fragment')
    if not re.fullmatch(r'/[A-Za-z0-9_.-]+', url.path) or url.path in {'/.', '/..'}:
        raise ValueError('Use a single GitHub repository path')
    return site_url.rstrip('/'), url.path


def mount(path, base):
    return base + path if path.startswith('/') and not path.startswith(('//', base + '/', base + '?', base + '#')) and path != base else path


def javascript(text, base):
    # Language prefixes have an empty English branch; both branches need the mount.
    text = text.replace('? "/zh" : ""', f'? "{base}/zh" : "{base}"')
    text = text.replace("const P = zh ? '/zh' : '';", f"const P = zh ? '{base}/zh' : '{base}';")
    # Remove the project mount before replacing the language segment on current URLs.
    text = text.replace('next.pathname.replace(/^\\/zh(?=\\/)/, "")',
                        f'next.pathname.slice({len(base)}).replace(/^\\/zh(?=\\/)/, "")')
    text = text.replace('new URL("/" + filename, location.origin)',
                        f'new URL("{base}/" + filename, location.origin)')
    text = text.replace('(zh ? "/zh/" : "/")', f'(zh ? "{base}/zh/" : "{base}/")')
    # Explicit root-relative route literals, including fetch template strings.
    # Bare slash strings (split, join, keyboard shortcuts) and regexes stay intact.
    text = re.sub(r'''(["'`])(/(?=[A-Za-z]|\$\{)[^"'`\s]*)''',
                  lambda m: m[1] + mount(m[2], base), text)
    # HTML snippets embedded in JS use escaped quotes.
    text = re.sub(r'(href=\\")(/[^\\"]*)', lambda m: m[1] + mount(m[2], base), text)
    return text


def transform(text, suffix, site_url, base):
    text = text.replace(UPSTREAM, site_url)
    if suffix == '.js':
        text = javascript(text, base)
    if suffix == '.html':
        text = re.sub(r'''((?:href|src|action|data-[\w-]+)=["'])(/[^"']*)''',
                      lambda m: m[1] + mount(m[2], base), text)
        # Generated inline code has the same URL conventions as the static scripts.
        text = re.sub(r'(<script\b[^>]*>)(.*?)(</script>)',
                      lambda m: m[1] + (m[2] if 'ld+json' in m[1] else javascript(m[2], base)) + m[3], text, flags=re.S)
    if suffix in {'.css', '.html', '.svg'}:
        text = re.sub(r'''(url\(["']?)(/[^)"']*)''', lambda m: m[1] + mount(m[2], base), text)
    if suffix in {'.json', '.jsonl'}:
        # Published route fields, never arbitrary paths retained in source evidence.
        text = re.sub(r'("(?:href_en|href_zh|path)"\s*:\s*")(/(?:zh/)?(?:api|resources|papers|browse)/[^"\n]*)',
                      lambda m: m[1] + mount(m[2], base), text)
    if suffix in {'.md', '.txt'}:
        text = re.sub(r'(\]\()(/[^)\s]*)', lambda m: m[1] + mount(m[2], base), text)
    return text


def fingerprint(path):
    data = path.read_bytes()
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def repair_checksums(output):
    # These public descriptors bind transformed deployment bytes, not source data.
    browser_path = output / 'source-browser.json'
    browser = json.loads(browser_path.read_text(encoding='utf-8'))
    full_export = browser.get('meta', {}).get('full_export')
    if full_export:
        browser['meta']['full_export_sha256'] = fingerprint(output / full_export)['sha256']
        browser_path.write_text(json.dumps(browser, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    index_path = output / 'api/v1/index.json'
    index = json.loads(index_path.read_text(encoding='utf-8'))
    for item in index['files']:
        item.update(fingerprint(output / 'api/v1' / item['path'].rsplit('/', 1)[1]))
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    folder = output / 'downloads'
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    for name, item in manifest['files'].items():
        item.update(fingerprint(folder / name))
    (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted([*manifest['files'], 'manifest.json']):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (folder / name).read_bytes())
    bundle = folder / 'awesome-rea-data.zip'
    bundle.write_bytes(buffer.getvalue())
    descriptor_path = output / 'data-manifest.json'
    descriptor = json.loads(descriptor_path.read_text(encoding='utf-8'))
    descriptor.update(manifest)
    descriptor['archive'].update(fingerprint(bundle))
    descriptor_path.write_text(json.dumps(descriptor, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def adapt(output, site_url=DEFAULT_URL):
    site_url, base = profile(site_url)
    # Verify input before modifying it; a repeated adaptation is intentionally rejected.
    read_build_manifest(output)
    if not (output / 'CNAME').exists():
        raise ValueError('Start from a fresh upstream production build, not a previously adapted site')
    for path in output.rglob('*'):
        if path.is_file() and path.suffix in TEXT and path.name != 'build-manifest.json':
            path.write_text(transform(path.read_text(encoding='utf-8'), path.suffix, site_url, base), encoding='utf-8')
    # Rehash assets after the URL edits, then replace references everywhere.
    renamed = {}
    for path in (output / 'assets').iterdir():
        match = HASHED.fullmatch(path.name)
        if match:
            name = f'{match[1]}.{fingerprint(path)["sha256"][:16]}{match[2]}'
            if name != path.name:
                renamed[path.name] = name
                path.rename(path.with_name(name))
    if renamed:
        pattern = re.compile('|'.join(map(re.escape, renamed)))
        for path in output.rglob('*'):
            if path.is_file() and path.suffix in TEXT and path.name != 'build-manifest.json':
                text = path.read_text(encoding='utf-8')
                updated = pattern.sub(lambda m: renamed[m[0]], text)
                if updated != text:
                    path.write_text(updated, encoding='utf-8')
    repair_checksums(output)
    # Pages does not honor Cloudflare's control files. Do not claim the original
    # domain or publish upstream ownership-verification tokens on this fork.
    for name in ('CNAME', '_headers', '_redirects', 'indexnow.txt', 'google75a4c81c8b267ad6.html'):
        (output / name).unlink(missing_ok=True)
    shutil.copyfile(ROOT / 'LICENSE', output / 'LICENSE')
    # Static redirects replace the small upstream Cloudflare redirect table.
    for line in (ROOT / 'site/_redirects').read_text(encoding='utf-8').splitlines():
        parts = line.split()
        if len(parts) != 3 or not parts[0].startswith('/') or not parts[1].startswith('/'):
            continue
        source, target, _ = parts
        if not source.endswith('/'):
            continue
        path = output / source.strip('/') / 'index.html'
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        destination = site_url + target
        path.write_text(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={escape(destination)}"><link rel="canonical" href="{escape(destination)}"><title>Moved</title></head><body><a href="{escape(destination)}">Continue</a></body></html>\n', encoding='utf-8')
    write_build_manifest(output)
    validate(output, site_url)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
    def handle_starttag(self, tag, attrs):
        self.urls.extend(value for key, value in attrs if key in {'href', 'src', 'action'} and value)


def validate(output, site_url):
    site_url, base = profile(site_url)
    for name in ('CNAME', 'indexnow.txt', 'google75a4c81c8b267ad6.html'):
        assert not (output / name).exists(), f'Unexpected ownership file: {name}'
    assert (output / '.nojekyll').exists()
    assert (output / 'LICENSE').read_bytes() == (ROOT / 'LICENSE').read_bytes()
    read_build_manifest(output)
    pages = 0
    for path in output.rglob('*.html'):
        parser = Links()
        html = path.read_text(encoding='utf-8')
        assert UPSTREAM not in html, f'Upstream URL remains in generated page: {path.relative_to(output)}'
        parser.feed(html)
        for canonical in re.findall(r'<link rel="canonical" href="([^"]+)"', html):
            assert canonical.startswith(site_url + '/'), f'Incorrect canonical: {canonical}'
        for social in re.findall(r'<meta property="og:url" content="([^"]+)"', html):
            assert social.startswith(site_url + '/'), f'Incorrect Open Graph URL: {social}'
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            json.loads(block)
        for href in parser.urls:
            url = urlsplit(href)
            if url.scheme or url.netloc or not url.path.startswith('/'):
                continue
            assert url.path.startswith(base + '/') or url.path == base, f'Unprefixed URL: {path.relative_to(output)} {href}'
            local = output / unquote(url.path[len(base):]).lstrip('/')
            assert local.is_file() or (local / 'index.html').is_file(), f'Missing target: {path.relative_to(output)} {href}'
        pages += 1
    for path in (output / 'assets').iterdir():
        match = HASHED.fullmatch(path.name)
        if match:
            assert f'.{fingerprint(path)["sha256"][:16]}.' in path.name, f'Stale asset fingerprint: {path.name}'
    for path in output.glob('*sitemap*.xml'):
        assert UPSTREAM not in path.read_text(encoding='utf-8')
    print(f'GitHub Pages checks passed: {pages} HTML pages, mounted links, assets, license and manifest ({site_url}/).')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site-url', default=DEFAULT_URL)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    adapt(args.output, args.site_url)


if __name__ == '__main__':
    main()
