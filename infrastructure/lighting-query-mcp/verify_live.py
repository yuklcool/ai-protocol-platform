"""GitHub self-hosted acceptance. No production data is uploaded to Actions."""

from datetime import datetime, UTC
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
import uuid

ROOT = Path('/opt/ai-protocol-platform')
record = json.loads((ROOT/'lighting-a2ui-deployment.json').read_text())
if os.environ.get('GITHUB_SHA') != record['commit'] or os.environ.get('GITHUB_ACTIONS') != 'true':
    raise RuntimeError('真实数据验收只在GitHub执行,且必须对应已部署提交')
backup = Path(record['backup'])
env = dict(s.split('=',1) for s in json.loads(subprocess.check_output(['docker','inspect','ai-protocol-platform-backend-1']))[0]['Config']['Env'] if '=' in s)
token = None
BASE = 'http://127.0.0.1:3456/api/proxy'


def response(path, method='GET', data=None, extra=None):
    return urllib.request.urlopen(urllib.request.Request(BASE+path, method=method,
        data=None if data is None else json.dumps(data,ensure_ascii=False).encode(),
        headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {}),**(extra or {})}),timeout=180)


def api(path, method='GET', data=None, extra=None):
    with response(path,method,data,extra) as res:
        raw = res.read().decode()
        if 'text/event-stream' in res.headers.get('Content-Type',''):
            return json.loads(next(line[6:] for line in raw.splitlines() if line.startswith('data: ')))
        return json.loads(raw)


try:
    api('/mcp/lighting-query','POST',{'jsonrpc':'2.0','id':1,'method':'tools/list'})
    raise RuntimeError('未登录调用被意外接受')
except urllib.error.HTTPError as exc:
    assert exc.code == 401

token = api('/api/auth/login','POST',{'email':env['SELFHOST_ADMIN_EMAIL'],'password':env['SELFHOST_ADMIN_PASSWORD']})['access_token']
config = api('/api/admin/platform-config')
assert config['agent']['interaction']['allowActionTriggeredRuns']
for skill in record['skills']:
    access = api('/api/skills/'+skill['skillId']+'/effective-access')
    assert access['gates']['skillAccess'] and access['gates']['rootBinding']
    assert 'lighting-query' in access['capabilities']['effectiveMcpServers']
restricted = api('/api/admin/mcp-servers/lighting-query')
assert len(restricted['allowedUserIds']) == 1


def rpc(method, params):
    value = api('/mcp/lighting-query','POST',{'jsonrpc':'2.0','id':uuid.uuid4().hex,'method':method,'params':params},
                {'Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-03-26'})
    assert 'error' not in value, 'MCP protocol error'
    return value['result']


rpc('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'lighting-github-acceptance','version':'1'}})
assert [tool['name'] for tool in rpc('tools/list',{})['tools']] == ['query_lighting']
checks = []
for scene, view in [('night',None),('lamp_alarms',None),('rtu',None),('rtu_alarms',None),('reconcile',None),('energy','night'),('energy','week'),('energy','volatility'),('energy','saving')]:
    request = {'scene':scene,'limit':3}
    if view:
        request['energy_view'] = view
    result = rpc('tools/call',{'name':'query_lighting','arguments':{'request':request}})
    assert not result.get('isError'), f'query failed: {scene}/{view}'
    data = result.get('structuredContent')
    if data is None:
        data = json.loads(result['content'][0]['text'])
    assert data['schema_version'] == 'lighting-query/v1'
    assert data['scene'] == scene and data['status'] != 'error'
    assert data['row_count'] >= len(data['rows'])
    assert data['query']['missing'], 'Production evidence gaps must remain visible'
    if scene == 'night':
        assert len(data['report']) == 9
    if scene == 'rtu':
        assert len(data['report']) == 7
    check = {'scene':scene,'energy_view':view,'status':data['status'],'rows_returned':len(data['rows']),'population':data['row_count'],'contract':True}
    checks.append(check)
    print(json.dumps(check),flush=True)


def agent_check(prompt, expected_scene):
    session = 'lighting-acceptance-'+uuid.uuid4().hex
    try:
        api('/api/sessions/'+session+'/bootstrap','POST',{'skill_id':'root-agent','document_ids':[]})
        events = []
        with response('/api/agent/stream','POST',{
            'threadId':session,'runId':uuid.uuid4().hex,'state':{},
            'messages':[{'id':uuid.uuid4().hex,'role':'user','content':prompt}],
            'forwardedProps':{'document_ids':[]},
        }) as stream:
            for line in stream:
                if line.startswith(b'data: '):
                    events.append(json.loads(line[6:]))
        used = [event.get('toolCallName') for event in events if event.get('type') == 'TOOL_CALL_START']
        assert not any(event.get('type') == 'RUN_ERROR' for event in events), 'Agent run error'
        assert any(event.get('type') == 'RUN_FINISHED' for event in events), 'Agent run incomplete'
        assert {'load_skill','query_lighting'} <= set(used), 'Agent did not load the business Skill and query real data'
        assert not {'write','edit','remember','forget','sql_query_readonly'} & set(used), 'Unexpected independent query/write'
        surfaces = [event for event in events if event.get('name') == 'A2UI_SURFACE']
        assert surfaces, 'No A2UI result from real MCP'
        assert any(expected_scene in json.dumps(event,ensure_ascii=False) for event in surfaces)
        # Full answers, surfaces and real device data stay on the server only.
        private = backup/('agent-'+expected_scene+'.json')
        private.write_text(json.dumps(events,ensure_ascii=False))
        private.chmod(0o600)
        outcome = {'scene':expected_scene,'skill_loaded':True,'real_query':True,'a2ui_emitted':True,'run_finished':True,'tools':used}
        print(json.dumps(outcome),flush=True)
        return outcome
    finally:
        with response('/api/sessions/'+session,'DELETE') as res:
            assert res.status == 204


agent_checks = [agent_check('查一下昨晚全系统RTU运行情况，重点看有没有历史上报和三相电参。请按已绑定的原型技能展示结果；这次只读，不写案例、记忆，不做设备控制。','rtu'),
                agent_check('查看全系统最近7个完整自然日节能率和指标一致性，按已绑定技能给出可交互的结果及简短结论。这次只读，不写案例或记忆。','energy')]
outcome = {'checked_at':datetime.now(UTC).isoformat(),'commit':record['commit'],'status':'passed','queries':checks,'agent':agent_checks}
evidence = backup/'github-live-acceptance.json'
evidence.write_text(json.dumps(outcome,ensure_ascii=False,indent=2))
evidence.chmod(0o600)
record.update(status='complete',acceptance=str(evidence))
(ROOT/'lighting-a2ui-deployment.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
print('GitHub live acceptance passed. No production rows or credentials uploaded.',flush=True)
