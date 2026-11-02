"""Run isolated OpenCode and call its official local session API with free models."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'out/cloud-qa/opencode-api'
SANDBOX = WORK / 'workspace'
VERSION = '1.19.5'
BINARY = ROOT / 'out/cloud-qa/opencode/node_modules/opencode-windows-x64/bin/opencode.exe'
BASE = 'http://127.0.0.1:18090'
MODELS = ('flint-40b-free', 'nemotron-3.5-lightning-free', 'glm-5.3-flash-free')
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def request(path, body=None, timeout=5, method=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'}, method=method or ('GET' if body is None else 'POST'))
    with OPENER.open(req, timeout=timeout) as response:
        raw = response.read(8_000_001)
        if len(raw) > 8_000_000:
            raise ValueError('Local API response exceeded 8 MB')
        return json.loads(raw) if raw.strip() else None


def health():
    try:
        result = request('/global/health', timeout=2)
        return result if isinstance(result, dict) and result.get('healthy') is True else None
    except (OSError, ValueError):
        return None


def configuration():
    return {'$schema': 'https://opencode.ai/config.json', 'model': 'opencode/' + MODELS[0],
            'small_model': 'opencode/' + MODELS[0], 'enabled_providers': ['opencode'],
            'provider': {'opencode': {'whitelist': list(MODELS)}}, 'share': 'disabled', 'autoupdate': False,
            'permission': {'*': 'deny', 'read': 'allow', 'glob': 'allow', 'grep': 'allow', 'skill': 'allow'},
            'agent': {'qa': {'mode': 'primary', 'description': 'Synthetic ICD QA, read and skill tools only; no shell or file edits.', 'steps': 4}}}


def isolated_environment():
    env = os.environ.copy()
    for name in list(env):
        if re.search(r'(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|SECRET|PASSWORD)$', name, re.I) or name.startswith(('ANTHROPIC_', 'OPENAI_', 'OPENCODE_')):
            env.pop(name, None)
    for kind in ('CONFIG', 'DATA', 'CACHE', 'STATE'):
        env['XDG_' + kind + '_HOME'] = str(WORK / 'home' / kind.lower())
    env['OPENCODE_CONFIG_CONTENT'] = json.dumps(configuration())
    env['OPENCODE_DISABLE_AUTOUPDATE'] = '1'
    env['OPENCODE_DISABLE_SHARE'] = '1'
    return env


def setup():
    if sys.platform != 'win32':
        raise ValueError('Installer currently supports Windows x64')
    if not BINARY.is_file():
        npm = shutil.which('npm.cmd')
        if not npm:
            raise ValueError('Node.js/npm required for the isolated installation')
        subprocess.run([npm, 'install', '--prefix', str(ROOT / 'out/cloud-qa/opencode'), '--ignore-scripts', '--no-audit', '--no-fund', f'opencode-ai@{VERSION}'], check=True)
    version = subprocess.check_output([str(BINARY), '--version'], text=True).strip()
    if version != VERSION:
        raise ValueError('Installed OpenCode version differs from pinned version')
    save(WORK / 'config-reference.json', configuration())
    prepare_workspace()
    print('OPENCODE_INSTALLED ' + version)


def prepare_workspace():
    SANDBOX.mkdir(parents=True, exist_ok=True)
    if not (SANDBOX / '.git').is_dir():
        # An independent worktree boundary prevents discovery of the bank's answer keys.
        subprocess.run(['git', 'init', '--quiet', str(SANDBOX)], check=True, stdout=subprocess.DEVNULL)
    fixtures = SANDBOX / 'fixtures'
    fixtures.mkdir(exist_ok=True)
    for name in ('ping.h', 'ambiguous.h', 'document-excerpt.txt'):
        shutil.copy2(ROOT / 'tests/fixtures/udpsim-model' / name, fixtures / name)
    shutil.copytree(ROOT / 'skills/udpsim-icd-authoring', SANDBOX / 'skills/udpsim-icd-authoring', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'model-qa.md'))
    stale_evaluator = SANDBOX / 'skills/udpsim-icd-authoring/references/model-qa.md'
    if stale_evaluator.is_file() and stale_evaluator.resolve().is_relative_to(SANDBOX.resolve()):
        stale_evaluator.unlink()
    entry = SANDBOX / '.claude/skills/udpsim-icd-authoring'
    entry.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / '.claude/skills/udpsim-icd-authoring/SKILL.md', entry / 'SKILL.md')
    (SANDBOX / 'AGENTS.md').write_text('Synthetic ICD QA workspace. Read only the source requested by the user and necessary skill references. Do not search for evaluator answer keys. Missing specification facts stay unresolved. Do not claim XML validation unless the parent supplied actual validator evidence.\n', encoding='utf-8')


def start():
    current = health()
    if current:
        raise ValueError('A service already owns the API port; inspect status instead of replacing it')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 18090))
    if not BINARY.is_file():
        raise ValueError('Run setup first')
    prepare_workspace()
    WORK.mkdir(parents=True, exist_ok=True)
    with open(WORK / 'server.stdout.txt', 'ab') as out, open(WORK / 'server.stderr.txt', 'ab') as err:
        child = subprocess.Popen([str(BINARY), 'serve', '--hostname', '127.0.0.1', '--port', '18090', '--log-level', 'WARN', '--pure'],
                                 cwd=SANDBOX, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                 env=isolated_environment(), creationflags=subprocess.CREATE_NO_WINDOW)
    save(WORK / 'process.json', {'pid': child.pid, 'executable': str(BINARY), 'version': VERSION, 'port': 18090, 'workspace': str(SANDBOX)})
    for _ in range(60):
        if health():
            print('OPENCODE_API_READY ' + BASE)
            return
        if child.poll() is not None:
            raise ValueError('OpenCode exited; inspect server.stderr.txt')
        time.sleep(.5)
    child.terminate()
    raise ValueError('OpenCode startup timed out')


def stop():
    path = WORK / 'process.json'
    if not path.is_file():
        print('NO_OWNED_SERVER')
        return
    state = json.loads(path.read_text(encoding='utf-8'))
    script = f'Get-CimInstance Win32_Process -Filter "ProcessId = {int(state["pid"])}" | Select-Object ExecutablePath,CommandLine | ConvertTo-Json -Compress'
    raw = subprocess.check_output(['powershell.exe', '-NoProfile', '-Command', script], text=True, encoding='utf-8', errors='replace').strip()
    process = json.loads(raw) if raw else None
    if process:
        if Path(process.get('ExecutablePath') or '').resolve() != BINARY.resolve() or '--port 18090' not in (process.get('CommandLine') or ''):
            raise ValueError('PID identity changed; refusing to stop an unrelated process')
        subprocess.run(['taskkill', '/PID', str(state['pid']), '/T', '/F'], check=True, stdout=subprocess.DEVNULL)
    path.unlink()
    print('OPENCODE_API_STOPPED')


def models():
    data = request('/config/providers')
    rows = []
    for provider in data.get('providers', []):
        if provider.get('id') != 'opencode':
            continue
        for name, model in provider.get('models', {}).items():
            if name in MODELS:
                cost = model.get('cost', {})
                if cost.get('input') != 0 or cost.get('output') != 0:
                    raise ValueError('Selected model is no longer listed as free: ' + name)
                rows.append({'id': name, 'cost': cost, 'limit': model.get('limit'), 'capabilities': model.get('capabilities')})
    return rows


def result_of(messages, session_id, model):
    if not isinstance(messages, list) or any(not isinstance(m, dict) or not isinstance(m.get('info'), dict) for m in messages):
        raise ValueError('Invalid OpenCode message-list envelope')
    latest = next((m for m in reversed(messages) if m.get('info', {}).get('role') == 'assistant'), None)
    if latest is None:
        return None
    info = latest['info']
    if not isinstance(info.get('time'), dict) or not isinstance(latest.get('parts'), list) or any(not isinstance(p, dict) for p in latest['parts']):
        raise ValueError('Invalid OpenCode assistant envelope')
    base = {'session_id': session_id, 'model': model, 'skill_qa': 'NOT_RUN'}
    if info.get('error'):
        return {**base, 'status': 'MODEL_ERROR', 'error': info['error']}
    if not info.get('time', {}).get('completed') or info.get('finish') == 'tool-calls':
        return None
    if info.get('providerID') != 'opencode' or info.get('modelID') != model:
        return {**base, 'status': 'MODEL_ID_MISMATCH', 'model_returned': info.get('modelID'), 'provider_returned': info.get('providerID')}
    if info.get('finish') != 'stop':
        return {**base, 'status': 'MODEL_INCOMPLETE', 'finish': info.get('finish')}
    fragments = [p.get('text') for p in latest['parts'] if p.get('type') == 'text']
    if any(not isinstance(text, str) for text in fragments):
        raise ValueError('OpenCode text part must contain a string')
    text = '\n'.join(fragments).strip()
    return {**base, 'status': 'OPENCODE_RESPONSE' if text else 'MODEL_EMPTY_RESPONSE', 'text': text,
            'model_returned': info['modelID'], 'provider_returned': info['providerID'],
            'assistant_steps': sum(m['info'].get('role') == 'assistant' for m in messages),
            'tokens': info.get('tokens'), 'cost_reported': info.get('cost')}


def ask(model, prompt, timeout):
    if model not in MODELS:
        raise ValueError('Only the three explicitly selected free OpenCode models are allowed')
    if not 1 <= timeout <= 180:
        raise ValueError('Timeout must be 1..180 seconds')
    if not prompt.strip() or len(prompt) > 100_000:
        raise ValueError('Prompt must be nonempty and at most 100000 characters')
    available = {m['id'] for m in models()}
    if model not in available:
        raise ValueError('Free model not exposed by the running OpenCode instance')
    session = request('/session', {'title': 'Synthetic QA ' + uuid.uuid4().hex[:8]})
    sid = session['id']
    run = WORK / 'runs' / sid
    save(run / 'request.json', {'model': model, 'prompt': prompt, 'qualification': 'CONNECTION_SMOKE'})
    result = None
    try:
        request(f'/session/{sid}/prompt_async', {'model': {'providerID': 'opencode', 'modelID': model}, 'agent': 'qa',
                                              'tools': {'bash': False, 'edit': False, 'write': False},
                                              'parts': [{'type': 'text', 'text': prompt}]})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            messages = request(f'/session/{sid}/message', timeout=min(5, max(.1, deadline - time.monotonic())))
            result = result_of(messages, sid, model)
            if result:
                break
            states = request('/session/status')
            if not isinstance(states, dict):
                raise ValueError('Invalid OpenCode session-status envelope')
            state = states.get(sid, {})
            if not isinstance(state, dict):
                raise ValueError('Invalid OpenCode owned-session status')
            action = state.get('action') or {}
            if isinstance(action, dict) and action.get('reason') == 'free_tier_limit':
                save(run / 'session-status.json', state)
                result = {'status': 'MODEL_FREE_LIMIT', 'session_id': sid, 'model': model,
                          'retry_reason': 'free_tier_limit', 'skill_qa': 'NOT_RUN'}
                break
            time.sleep(min(1, max(0, deadline - time.monotonic())))
        if result is None:
            result = {'status': 'MODEL_TIMEOUT', 'session_id': sid, 'model': model, 'seconds': timeout, 'skill_qa': 'NOT_RUN'}
    except (OSError, ValueError, TypeError) as error:
        result = {'status': 'MODEL_API_ERROR', 'session_id': sid, 'model': model, 'error': str(error), 'skill_qa': 'NOT_RUN'}
    finally:
        if result is None or result.get('status') not in ('OPENCODE_RESPONSE', 'MODEL_ERROR'):
            try:
                request(f'/session/{sid}/abort', {}, timeout=5)
            except (OSError, ValueError):
                if result is not None:
                    result['abort_status'] = 'FAILED; inspect server status'
    save(run / 'result.json', result)
    print(json.dumps(result, ensure_ascii=False))
    if result['status'] == 'OPENCODE_RESPONSE':
        return 0
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['setup', 'start', 'status', 'stop', 'models', 'ask'])
    parser.add_argument('--model', default=MODELS[0])
    parser.add_argument('--prompt')
    parser.add_argument('--prompt-file')
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    try:
        if args.action == 'setup': setup()
        elif args.action == 'start': start()
        elif args.action == 'stop': stop()
        elif args.action == 'status': print(json.dumps({'url': BASE, 'health': health()}))
        elif args.action == 'models': print(json.dumps(models(), ensure_ascii=False))
        else:
            if bool(args.prompt) == bool(args.prompt_file):
                raise ValueError('Choose exactly one of --prompt or --prompt-file')
            prompt = Path(args.prompt_file).read_text(encoding='utf-8-sig') if args.prompt_file else args.prompt
            return ask(args.model, prompt, args.timeout)
        return 0
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'OPENCODE_API_ERROR', 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
