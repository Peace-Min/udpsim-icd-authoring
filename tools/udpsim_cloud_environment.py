"""Isolated Windows Bifrost + Claude Code setup; cloud keys stay in process memory."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'out/cloud-qa'
BIFROST_VERSION = 'v2.4.0'
CLAUDE_VERSION = '2.1.312'
BINARY = WORK / 'bifrost/bin/bifrost-http.exe'
CLAUDE = WORK / 'claude/node_modules/@anthropic-ai/claude-code-win32-x64/claude.exe'
URL = f'https://downloads.getmaxim.ai/bifrost/{BIFROST_VERSION}/windows/amd64/bifrost-http.exe'
UPSTREAM = 'https://dashscope.aliyuncs.com/apps/anthropic'
PORTS = {'mock': 18080, 'cloud': 18081}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    temp.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def health(port):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{port}/health', timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


def free_port(port):
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', port))
        except OSError:
            raise ValueError(f'Port {port} is occupied; will not replace an existing service') from None


def setup():
    if sys.platform != 'win32' or sys.maxsize < 2**32:
        raise ValueError('This environment installer targets Windows x64')
    WORK.mkdir(parents=True, exist_ok=True)
    if not BINARY.is_file():
        BINARY.parent.mkdir(parents=True, exist_ok=True)
        temp = BINARY.with_suffix('.download')
        urllib.request.urlretrieve(URL, temp)
        temp.replace(BINARY)
    if not CLAUDE.is_file():
        npm = shutil.which('npm.cmd')
        if not npm:
            raise ValueError('Node.js/npm is missing; install it before setup')
        result = subprocess.run([npm, 'install', '--prefix', str(WORK / 'claude'), '--ignore-scripts', '--no-audit', '--no-fund', f'@anthropic-ai/claude-code@{CLAUDE_VERSION}'], check=False)
        if result.returncode:
            raise ValueError('Isolated Claude Code installation failed')
    version = subprocess.check_output([str(CLAUDE), '--version'], text=True).strip()
    if not version.startswith(CLAUDE_VERSION + ' '):
        raise ValueError('Installed Claude version does not match target')
    write_json(WORK / 'versions.json', {'bifrost_version': BIFROST_VERSION, 'bifrost_source': URL, 'bifrost_sha256': sha(BINARY), 'claude_version': version, 'claude_sha256': sha(CLAUDE)})
    for profile in PORTS:
        write_json(WORK / profile / 'app/config.json', configuration(profile))
    print('SETUP_READY Bifrost ' + BIFROST_VERSION + '; ' + version)


def configuration(profile):
    model = 'udpsim-mock' if profile == 'mock' else 'qwen3.6-27b'
    return {'$schema': 'https://www.getbifrost.ai/schema', 'config_store': {'enabled': False}, 'logs_store': {'enabled': False},
            'client': {'enable_logging': False},
            'providers': {'anthropic': {'keys': [{'name': 'qa-only', 'value': 'env.UDPSIM_CLOUD_API_KEY', 'models': [model], 'weight': 1}],
                                      'network_config': {'base_url': 'http://127.0.0.1:18082' if profile == 'mock' else UPSTREAM, 'default_request_timeout_in_seconds': 120, 'max_retries': 0}}}}


def spawn(command, folder, name, env):
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / (name + '.stdout.txt'), 'ab') as stdout, open(folder / (name + '.stderr.txt'), 'ab') as stderr:
        return subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, env=env,
                                creationflags=subprocess.CREATE_NO_WINDOW)


def start(profile, confirmed=False):
    if not BINARY.is_file() or not CLAUDE.is_file():
        raise ValueError('Run setup first')
    port = PORTS[profile]
    state_path = WORK / profile / 'processes.json'
    if health(port):
        raise ValueError(f'Port {port} is already healthy; use status to inspect it')
    free_port(port)
    env = os.environ.copy()
    if profile == 'cloud':
        if not confirmed:
            raise ValueError('Confirm Beijing qwen3.6-27b remaining free quota and Free Quota Only in the console, then pass --free-quota-confirmed')
        key = env.get('UDPSIM_CLOUD_API_KEY') or getpass.getpass('Alibaba Beijing API key (hidden, not saved): ')
        if not key.strip():
            raise ValueError('An API key is required; nothing started')
        env['UDPSIM_CLOUD_API_KEY'] = key
    else:
        env['UDPSIM_CLOUD_API_KEY'] = 'synthetic-local-only'
        free_port(18082)
    # Exclude unrelated provider credentials from this isolated gateway process.
    for name in ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN'):
        env.pop(name, None)
    app = WORK / profile / 'app'
    write_json(app / 'config.json', configuration(profile))
    children = []
    try:
        if profile == 'mock':
            child = spawn([sys.executable, str(ROOT / 'tools/udpsim_mock_provider.py')], app.parent, 'upstream', env)
            children.append({'pid': child.pid, 'kind': 'upstream', 'executable': sys.executable})
        child = spawn([str(BINARY), '-host', '127.0.0.1', '-port', str(port), '-app-dir', str(app), '-log-level', 'warn'], app.parent, 'bifrost', env)
        children.append({'pid': child.pid, 'kind': 'bifrost', 'executable': str(BINARY)})
        write_json(state_path, {'profile': profile, 'port': port, 'processes': children, 'cloud_model_calls': 'NOT_RUN'})
        for _ in range(60):
            if health(port):
                print(f'GATEWAY_READY http://127.0.0.1:{port}/anthropic profile={profile}')
                return
            if child.poll() is not None:
                raise ValueError('Bifrost exited during startup; inspect the profile stderr/stdout logs')
            time.sleep(.5)
        raise ValueError('Gateway startup timed out; use status and inspect profile logs')
    except Exception:
        # Only the exact children started by this invocation can be terminated here.
        for item in children:
            subprocess.run(['taskkill', '/PID', str(item['pid']), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raise


def status():
    data = {'installed': {'bifrost': BINARY.is_file(), 'claude_target': CLAUDE.is_file()},
            'profiles': {name: {'port': port, 'healthy': health(port)} for name, port in PORTS.items()},
            'cloud_model_qa': 'NOT_RUN'}
    print(json.dumps(data, indent=2))


def stop(profile):
    path = WORK / profile / 'processes.json'
    if not path.is_file():
        print('NO_OWNED_PROCESSES')
        return
    state = json.loads(path.read_text())
    # Match the recorded executable and command line before touching a saved PID.
    for item in state['processes']:
        script = f'Get-CimInstance Win32_Process -Filter "ProcessId = {int(item["pid"])}" | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress'
        raw = subprocess.check_output(['powershell.exe', '-NoProfile', '-Command', script], text=True, encoding='utf-8', errors='replace').strip()
        process = json.loads(raw) if raw else None
        if not process:
            continue
        if not process.get('ExecutablePath') or Path(process['ExecutablePath']).resolve() != Path(item['executable']).resolve():
            raise ValueError('Saved PID executable changed; refusing to stop unrelated process')
        marker = str(ROOT / 'tools/udpsim_mock_provider.py') if item['kind'] == 'upstream' else str(WORK / profile / 'app')
        if marker.lower() not in (process.get('CommandLine') or '').lower():
            raise ValueError('Saved PID command line changed; refusing to stop unrelated process')
        subprocess.run(['taskkill', '/PID', str(item['pid']), '/T', '/F'], check=True, stdout=subprocess.DEVNULL)
    path.unlink()
    print('OWNED_PROCESSES_STOPPED ' + profile)


def claude(profile, prompt):
    if not health(PORTS[profile]):
        raise ValueError('Start the selected gateway profile first')
    env = os.environ.copy()
    env['CLAUDE_CONFIG_DIR'] = str(WORK / profile / 'claude-home')
    env['ANTHROPIC_BASE_URL'] = f'http://127.0.0.1:{PORTS[profile]}/anthropic'
    env['ANTHROPIC_AUTH_TOKEN'] = 'local-gateway-only'
    model = 'anthropic/udpsim-mock' if profile == 'mock' else 'anthropic/qwen3.6-27b'
    for name in ('OPUS', 'SONNET', 'HAIKU'):
        env['ANTHROPIC_DEFAULT_' + name + '_MODEL'] = model
    for name in ('CLAUDE_CODE_DISABLE_1M_CONTEXT', 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC', 'DISABLE_TELEMETRY', 'DISABLE_AUTOUPDATER'):
        env[name] = '1'
    env['CLAUDE_CODE_ATTRIBUTION_HEADER'] = '0'
    for name in ('ANTHROPIC_API_KEY', 'CLAUDE_CODE_OAUTH_TOKEN', 'CLAUDECODE', 'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY', 'UDPSIM_CLOUD_API_KEY'):
        env.pop(name, None)
    command = [str(CLAUDE), '--model', model]
    if prompt:
        command += ['--print', '--output-format', 'json', '--tools', 'Read', '--allowedTools', 'Read', '--', prompt]
    if prompt:
        return subprocess.call(command, cwd=ROOT, env=env, timeout=120)
    return subprocess.call(command, cwd=ROOT, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['setup', 'start', 'status', 'stop', 'claude'])
    parser.add_argument('--profile', choices=['mock', 'cloud'], default='mock')
    parser.add_argument('--free-quota-confirmed', action='store_true')
    parser.add_argument('--prompt')
    args = parser.parse_args()
    try:
        if args.action == 'setup': setup()
        elif args.action == 'start': start(args.profile, args.free_quota_confirmed)
        elif args.action == 'status': status()
        elif args.action == 'stop': stop(args.profile)
        else: return claude(args.profile, args.prompt)
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print('ENVIRONMENT_BLOCKED ' + str(error))
        return 2


if __name__ == '__main__':
    sys.exit(main())
