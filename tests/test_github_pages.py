"""Deployment-only URL adaptation; upstream builds keep their original contract."""
import sys
import re
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_github_pages import javascript, mount, profile, transform

BASE = '/Awesome-REA'
URL = 'https://ahnhc.github.io' + BASE


class GitHubPagesTests(unittest.TestCase):
    def test_inherited_workflow_jobs_are_upstream_only(self):
        folder = Path(__file__).resolve().parents[1] / '.github/workflows'
        for path in folder.glob('*.yml'):
            if path.name == 'deploy-pages.yml':
                continue
            jobs = path.read_text().split('\njobs:\n', 1)[1]
            for job in re.split(r'(?m)^  [a-zA-Z][\w-]*:\n', jobs)[1:]:
                self.assertRegex(job, r"(?m)^    if:.*github.repository == 'reacher-z/Awesome-REA'")

    def test_profile_requires_pages_project(self):
        self.assertEqual(profile(URL + '/'), (URL, BASE))
        for value in ['https://awesomerea.org', 'http://ahnhc.github.io/x', 'https://ahnhc.github.io', URL + '?x=1', URL + '/other']:
            with self.assertRaises(ValueError):
                profile(value)

    def test_mount_preserves_external_and_mounted_urls(self):
        for value in ['https://example.com/x', '//example.com/x', BASE, BASE + '/zh/', '#section']:
            self.assertEqual(mount(value, BASE), value)
        self.assertEqual(mount('/papers/', BASE), BASE + '/papers/')

    def test_html_links_and_canonical(self):
        text = '<a href="/zh/">中文</a><img src="/social-card.png"><link rel="canonical" href="https://awesomerea.org/resources/">'
        adapted = transform(text, '.html', URL, BASE)
        self.assertIn('href="/Awesome-REA/zh/"', adapted)
        self.assertIn('src="/Awesome-REA/social-card.png"', adapted)
        self.assertIn('href="' + URL + '/resources/"', adapted)

    def test_javascript_routes_not_slash_operations(self):
        text = '''const P = zh ? '/zh' : ''; fetch(`/search-index${zh ? '.zh' : ''}.json`); value.split('/').join('/'); event.key === '/';'''
        adapted = javascript(text, BASE)
        self.assertIn("const P = zh ? '/Awesome-REA/zh' : '/Awesome-REA';", adapted)
        self.assertIn('fetch(`/Awesome-REA/search-index', adapted)
        self.assertIn("value.split('/').join('/'); event.key === '/';", adapted)

    def test_language_and_data_routes(self):
        text = 'next.pathname = (language === "zh" ? "/zh" : "") + next.pathname.replace(/^\\/zh(?=\\/)/, ""); new URL("/" + filename, location.origin);'
        adapted = javascript(text, BASE)
        self.assertIn('? "/Awesome-REA/zh" : "/Awesome-REA"', adapted)
        self.assertIn('next.pathname.slice(12).replace', adapted)
        self.assertIn('new URL("/Awesome-REA/" + filename', adapted)

    def test_json_routes_not_source_paths(self):
        text = '{"href_en":"/resources/test/", "path":"/api/v1/resources.json", "description":"/usr/bin/test"}'
        adapted = transform(text, '.json', URL, BASE)
        self.assertIn('"href_en":"/Awesome-REA/resources/test/"', adapted)
        self.assertIn('"description":"/usr/bin/test"', adapted)


if __name__ == '__main__':
    unittest.main()
