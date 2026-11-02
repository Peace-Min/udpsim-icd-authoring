"""Standalone discovery, metadata and local links; no model calls."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StandaloneLayout(unittest.TestCase):
    def test_one_skill_and_one_plugin(self):
        self.assertEqual([p.name for p in (ROOT / 'skills').iterdir() if p.is_dir()], ['udpsim-icd-authoring'])
        market = json.loads((ROOT / '.claude-plugin/marketplace.json').read_text(encoding='utf-8'))
        self.assertEqual(len(market['plugins']), 1)
        self.assertEqual(market['plugins'][0]['source'], './')

    def test_metadata_matches(self):
        plugin = json.loads((ROOT / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))
        market = json.loads((ROOT / '.claude-plugin/marketplace.json').read_text(encoding='utf-8'))
        self.assertEqual(plugin['name'], 'udpsim-icd-authoring')
        self.assertEqual(plugin['name'], market['name'])
        self.assertEqual(plugin['version'], market['plugins'][0]['version'])
        self.assertEqual(plugin['repository'], 'https://github.com/Peace-Min/udpsim-icd-authoring')

    def test_both_entrypoints_resolve_canonical_skill(self):
        target = ROOT / 'skills/udpsim-icd-authoring/SKILL.md'
        self.assertTrue(target.is_file())
        entry = (ROOT / '.claude/skills/udpsim-icd-authoring/SKILL.md').read_text(encoding='utf-8')
        command = (ROOT / 'commands/udpsim-icd-authoring.md').read_text(encoding='utf-8')
        self.assertIn('skills/udpsim-icd-authoring/SKILL.md', entry)
        self.assertIn('${CLAUDE_PLUGIN_ROOT}/skills/udpsim-icd-authoring/SKILL.md', command)
        self.assertNotIn('/peace-skillbank:', command)

    def test_local_document_links(self):
        files = [ROOT / 'README.md', ROOT / 'PROVENANCE.md', *list((ROOT / 'docs').rglob('*.md')),
                 *list((ROOT / 'skills').rglob('*.md'))]
        bad = []
        for path in files:
            for link in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8-sig')):
                if link.startswith(('http:', 'https:', '#')):
                    continue
                if not (path.parent / link.split('#')[0]).exists():
                    bad.append(str(path.relative_to(ROOT)) + ': ' + link)
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main()
