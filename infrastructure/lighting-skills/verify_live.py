"""GitHub-only production acceptance through the actual conversation path.

Only booleans, scene names and failure categories leave this host.
"""

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import uuid
from zoneinfo import ZoneInfo

ROOT = Path('/opt/ai-protocol-platform')
BASE = 'http://127.0.0.1:3456/api/proxy'
token = None


def response(path, method='GET', data=None):
    return urllib.request.urlopen(urllib.request.Request(
        BASE + path, method=method,
        data=None if data is None else json.dumps(data, ensure_ascii=False).encode(),
        headers={'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + token} if token else {})},
    ), timeout=300)


def api(path, method='GET', data=None):
    with response(path, method, data) as result:
        return None if result.status == 204 else json.load(result)


def stream(path, data):
    events = []
    with response(path, 'POST', data) as result:
        for line in result:
            if line.startswith(b'data: '):
                events.append(json.loads(line[6:]))
    return events


def inspect(events, expected_scene, skills, *, followup=False):
    assert not any(event.get('type') == 'RUN_ERROR' for event in events), 'agent_run_error'
    assert any(event.get('type') == 'RUN_FINISHED' for event in events), 'run_incomplete'
    calls = {}
    for event in events:
        call_id = event.get('toolCallId')
        if event.get('type') == 'TOOL_CALL_START':
            calls.setdefault(call_id, {})['name'] = event.get('toolCallName')
        elif event.get('type') == 'TOOL_CALL_ARGS':
            call = calls.setdefault(call_id, {})
            call['args'] = call.get('args', '') + event.get('delta', '')
    used = {call.get('name') for call in calls.values()}
    assert 'sql_query_readonly' in used, 'no_sql_execution'
    assert not {'query_lighting', 'write', 'edit', 'remember', 'forget'} & used, 'unexpected_write_or_fixed_query'
    if not followup:
        loaded = set()
        for call in calls.values():
            if call.get('name') == 'load_skill':
                loaded.add(json.loads(call.get('args') or '{}').get('skill_ref'))
        for slug in ('sql-safe-query', skills[expected_scene]):
            assert slug in loaded or installed[slug]['skillId'] in loaded, 'required_skill_not_loaded'
        assert {'find', 'sql_retrieve_examples'} & used, 'no_query_basis_retrieval'
    sql_calls = [json.loads(call.get('args') or '{}') for call in calls.values()
                 if call.get('name') == 'sql_query_readonly']
    assert any('lighting-query/v1' in call.get('sql', '') for call in sql_calls), 'no_dynamic_presentation_sql'
    roots = []
    for event in events:
        if event.get('name') == 'A2UI_SURFACE':
            value = event.get('value') or {}
            for message in value.get('messages', []):
                update = message.get('updateDataModel') or {}
                if update.get('path') == '/' and isinstance(update.get('value'), dict):
                    root = update['value']
                    if root.get('kind') == 'lighting':
                        roots.append((value['surfaceId'], root))
    assert roots, 'no_lighting_a2ui'
    surface, root = roots[-1]
    assert root.get('status') in {'success', 'partial', 'empty'}, 'invalid_lighting_result'
    assert root.get('scene') == expected_scene, 'wrong_scene'
    assert root.get('server_id') == 'mcp-sql-http', 'wrong_query_source'
    assert root['row_count'] >= len(root['rows']), 'inconsistent_coverage'
    return surface, root, sql_calls


def private_diagnostics(scene, events):
    directory = Path(__file__).parent / '_diagnostics'
    directory.mkdir(mode=0o700, exist_ok=True)
    target = directory / (scene + '.json')
    target.touch(mode=0o600)
    target.write_text(json.dumps(events, ensure_ascii=False))


def main():
    global token, installed
    record_path = ROOT / 'lighting-a2ui-deployment.json'
    record = json.loads(record_path.read_text())
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'github_only'
    assert os.environ.get('GITHUB_SHA') == record['skills_commit'], 'deployed_skills_commit_mismatch'
    container = json.loads(subprocess.check_output(['docker', 'inspect', 'ai-protocol-platform-backend-1']))[0]
    assert container['Config']['Labels']['org.opencontainers.image.revision'] == record['commit'], 'image_mismatch'
    env = dict(item.split('=', 1) for item in container['Config']['Env'] if '=' in item)
    token = api('/api/auth/login', 'POST', {
        'email': env['SELFHOST_ADMIN_EMAIL'], 'password': env['SELFHOST_ADMIN_PASSWORD'],
    })['access_token']
    config = api('/api/admin/platform-config')
    assert 'lighting-query' not in config['agent']['mcpServers'], 'legacy_query_still_bound'
    assert config['agent']['interaction']['allowActionTriggeredRuns'], 'actions_disabled'
    installed = {skill['slug']: skill for skill in api('/api/skills')}
    skills = {
        'night': 'lighting-night-overview', 'lamp_alarms': 'lighting-lamp-alarms',
        'rtu': 'lighting-rtu-operation', 'rtu_alarms': 'lighting-rtu-alarms',
        'energy': 'lighting-energy-analysis', 'reconcile': 'lighting-energy-reconciliation',
    }
    for slug in ['sql-safe-query', *skills.values()]:
        access = api('/api/skills/' + installed[slug]['skillId'] + '/effective-access')
        assert access['gates']['skillAccess'] and access['gates']['rootBinding'], 'skill_access_denied'
        assert 'mcp-sql-http' in access['capabilities']['effectiveMcpServers'], 'sql_not_authorized'
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    end = now.replace(hour=7, minute=0, second=0, microsecond=0)
    if end > now:
        end -= timedelta(days=1)
    start = (end - timedelta(days=1)).replace(hour=18)
    day_end = end.replace(hour=0)
    checks = []
    night_queries = []
    cases = [
        ('night', '整夜单灯运行与巡测覆盖', start, end),
        ('night', '整夜单灯运行与巡测覆盖', start - timedelta(days=1), end - timedelta(days=1)),
        ('lamp_alarms', '单灯报警与历史恢复证据', start, end),
        ('rtu', 'RTU运行与有效三相电参', start, end),
        ('rtu_alarms', '全部层级RTU报警与历史恢复证据', start, end),
        ('energy', '最近七个完整自然日能耗趋势，energy_view=week，使用D日报', day_end - timedelta(days=7), day_end),
        ('reconcile', '单灯和RTU能耗对账，使用D日报；历史归属未证实就明确留缺口', day_end - timedelta(days=1), day_end),
    ]
    for scene, goal, window_start, window_end in cases:
        session = 'lighting-acceptance-' + uuid.uuid4().hex
        category = 'agent_request_failed'
        events = []
        print(json.dumps({'scene': scene, 'status': 'running'}), flush=True)
        try:
            api('/api/sessions/' + session + '/bootstrap', 'POST', {'skill_id': 'root-agent', 'document_ids': []})
            prompt = (f'查询全系统{goal}，时间严格为{window_start.isoformat()}至{window_end.isoformat()}。'
                      f'加载安全SQL和对应照明业务技能，依据检索资料动态查询；按已绑定原型展示scene={scene}。'
                      '先紧凑汇总，清单最多5条，明细显式LIMIT；未取得证据用缺口说明，不编造。'
                      '本次需要交互原型：按runtime.md让本次SQL返回payload，包含一个全局retry动作。'
                      '只读验收，不写案例、记忆或控制设备；聊天只给简短业务结论。')
            events = stream('/api/agent/stream', {
                'threadId': session, 'runId': uuid.uuid4().hex, 'state': {},
                'messages': [{'id': uuid.uuid4().hex, 'role': 'user', 'content': prompt}],
                'forwardedProps': {'document_ids': []},
            })
            surface, root, sql_calls = inspect(events, scene, skills)
            for key, expected in [('start', window_start), ('end', window_end)]:
                assert datetime.fromisoformat(root['query']['window'][key]) == expected, 'user_window_changed'
            if scene == 'night':
                night_queries.append([call['sql'] for call in sql_calls])
                if len(night_queries) == 1:
                    retry = next((action for action in root['actions'] if action['intent'] == 'retry'), None)
                    assert retry, 'no_followup_action'
                    events = stream(f'/api/skills/root-agent/sessions/{session}/surface-action-run', {
                        'requestId': uuid.uuid4().hex, 'surfaceId': surface,
                        'action': {'name': 'run:lighting.query', 'context': {'actionId': retry['id']}},
                    })
                    _, followup, _ = inspect(events, scene, skills, followup=True)
                    assert followup['query']['window'] == root['query']['window'], 'followup_window_changed'
            checks.append({'scene': scene, 'dynamic_sql': True, 'a2ui': True, 'window_preserved': True})
            print(json.dumps(checks[-1]), flush=True)
        except AssertionError as exc:
            category = str(exc)
            private_diagnostics(scene, events)
            # Assertion messages above are fixed categories, never database errors.
            print(json.dumps({'scene': scene, 'passed': False, 'category': category}), flush=True)
            raise SystemExit(1) from None
        except Exception:
            private_diagnostics(scene, events)
            print(json.dumps({'scene': scene, 'passed': False, 'category': category}), flush=True)
            raise SystemExit(1) from None
        finally:
            api('/api/sessions/' + session, 'DELETE')
    assert night_queries[0] != night_queries[1], 'different_dates_reused_fixed_sql'
    record.update(status='complete', query_mode='sql-safe-query', live_acceptance={
        'status': 'passed', 'checks': checks,
        'url': os.environ['GITHUB_SERVER_URL'] + '/' + os.environ['GITHUB_REPOSITORY'] + '/actions/runs/' + os.environ['GITHUB_RUN_ID'],
    })
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print('Dynamic SQL and A2UI live acceptance passed; no raw data uploaded.', flush=True)


if __name__ == '__main__':
    main()
