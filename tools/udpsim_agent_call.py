"""One restricted stdio MCP call for a tool-driven Codex QA actor. Never reads evaluator oracles."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from validate_udpsim_priority import Client


def main():
    # The CLI is a JSON boundary too; Windows' console code page must not corrupt Korean Skill text.
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--tool', choices=('read', 'source', 'save', 'validate', 'convert', 'validate_xml', 'block'), required=True)
    parser.add_argument('--arguments', default='{}', help='JSON object; use arguments-file to avoid shell quoting')
    parser.add_argument('--arguments-file', type=Path)
    args = parser.parse_args()
    work = args.workspace.resolve()
    if not work.is_relative_to((ROOT / 'out').resolve()):
        parser.error('Use an ignored QA workspace under out/')
    if args.arguments_file:
        path = args.arguments_file.resolve()
        if not path.is_relative_to(work):
            parser.error('Arguments file must stay within the assigned workspace')
        arguments = json.loads(path.read_text(encoding='utf-8-sig'))
    else:
        arguments = json.loads(args.arguments)
    client = Client(work)
    try:
        result = client.request('tools/call', {'name': args.tool, 'arguments': arguments})
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result.get('isError') else 0
    finally:
        client.close()


if __name__ == '__main__':
    sys.exit(main())
