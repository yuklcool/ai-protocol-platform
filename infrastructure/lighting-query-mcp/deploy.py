"""Install on the explicitly authorized deployment host, never a developer PC."""

import base64
from datetime import datetime, UTC
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = Path('/opt/ai-protocol-platform')
SOURCE = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / 'infrastructure/lighting-query-mcp'
token = None


def api(path, method='GET', data=None):
    req = urllib.request.Request('http://127.0.0.1:1956' + path, method=method,
        data=None if data is None else json.dumps(data, ensure_ascii=False).encode(),
        headers={'Content-Type': 'application/json', **({'Authorization':'Bearer '+token} if token else {})})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    path.chmod(0o600)


def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)


def wait_backend():
    for _ in range(45):
        try:
            with urllib.request.urlopen('http://127.0.0.1:1956/health', timeout=3) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(2)
    raise RuntimeError('部署后端未恢复,请使用备份回滚')


def main(commit):
    global token
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('需要已通过GitHub验证的完整提交')
    assert ROOT.is_dir() and Path('/root/.nanobot/workspace/skills').is_dir()
    env = dict(s.split('=',1) for s in json.loads(subprocess.check_output(['docker','inspect','ai-protocol-platform-backend-1']))[0]['Config']['Env'] if '=' in s)
    token = api('/api/auth/login', 'POST', {'email':env['SELFHOST_ADMIN_EMAIL'], 'password':env['SELFHOST_ADMIN_PASSWORD']})['access_token']
    uid = json.loads(base64.urlsafe_b64decode(token.split('.')[1] + '==='))['sub']
    before, skills = api('/api/admin/platform-config'), api('/api/skills')
    backup = ROOT / 'backups' / ('lighting-a2ui-skills-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(mode=0o700, parents=True)
    save(backup / 'platform-config-before.json', before)
    save(backup / 'skills-before.json', skills)
    for old in ('docker-compose.lighting-skills.yml', 'lighting-a2ui-deployment.json'):
        if (ROOT / old).exists():
            shutil.copy2(ROOT / old, backup / old)
    # Retain only the existing SQL connection; never print its credentials.
    sql = json.loads(subprocess.check_output(['docker','exec','ai-protocol-platform-backend-1','/app/.venv/bin/python','-c',
        'import json; from db.persistence import get_document; print(json.dumps(get_document("mcp_servers","mcp-sql-http")))']))
    headers = {}
    for name, value in (sql.get('headers') or {}).items():
        if value.startswith('${') and value.endswith('}'):
            value = env.get(value[2:-1])
            if not value:
                raise ValueError('SQL MCP凭据引用未解析')
        headers[name] = value
    adapter_token = secrets.token_urlsafe(48)
    ADAPTER.mkdir(parents=True, exist_ok=True)
    (ADAPTER / 'private').mkdir(mode=0o700, exist_ok=True)
    for name in ('serve.py','request.py','queries.py','presenter.py','compose.yml','README.md'):
        shutil.copy2(SOURCE / 'infrastructure/lighting-query-mcp' / name, ADAPTER / name)
    save(ADAPTER / 'private/connection.json', {'sql_url':sql['url'],'sql_headers':headers,'adapter_token':adapter_token})
    compose = (ADAPTER / 'compose.yml').read_text().replace('ai-protocol-platform-backend:v2.4.3','ai-protocol-platform-backend:lighting-skills-'+commit)
    (ADAPTER / 'compose.yml').write_text(compose)
    override = ROOT / 'docker-compose.lighting-skills.yml'
    override.write_text('services:\n  backend:\n    image: ghcr.io/yuklcool/ai-protocol-platform-backend:lighting-skills-'+commit+'\n  frontend:\n    image: ghcr.io/yuklcool/ai-protocol-platform-frontend:lighting-skills-'+commit+'\n')
    stack = ['docker','compose','--project-directory',str(ROOT),'-f',str(ROOT/'docker-compose.release.yml'),'-f',str(override)]
    run(*stack, 'pull','backend','frontend')
    # No production source bind mounts and no build on the deployment server.
    run(*stack, 'up','-d','--no-deps','backend','frontend')
    wait_backend()
    token = api('/api/auth/login', 'POST', {'email':env['SELFHOST_ADMIN_EMAIL'], 'password':env['SELFHOST_ADMIN_PASSWORD']})['access_token']
    subprocess.run(['docker','compose','-p','aip-lighting-query','-f',str(ADAPTER/'compose.yml'),'up','-d'], check=True, stdout=subprocess.DEVNULL)
    view = api('/api/admin/mcp-servers/lighting-query', 'PUT', {
        'url':'http://lighting-query-mcp:8012/mcp','transport':'streamable-http','enabled':True,
        'description':'个人照明六场景固定只读查询与原型结果,不控制设备。',
        'headers':{'Authorization':'Bearer '+adapter_token},'allowedUserIds':[uid],
    })
    if view.get('allowedUserIds') != [uid]:
        raise RuntimeError('后端未提供账号隔离,拒绝绑定照明数据库')
    discovery = None
    for _ in range(20):
        discovery = api('/api/admin/mcp-servers/lighting-query/discover','POST',{})
        if discovery.get('ok'):
            break
        time.sleep(2)
    if not discovery or not discovery.get('ok') or [t['name'] for t in discovery['tools']] != ['query_lighting']:
        raise RuntimeError('照明MCP尚未就绪,不启用技能')
    installed = []
    existing = {s['slug']:s for s in skills}
    for entry in sorted((SOURCE/'skills').glob('lighting-*/SKILL.md')):
        import re
        content = entry.read_text()
        metadata, instructions = content.split('---',2)[1:]
        description = re.search(r'^description: (.+)$',metadata,re.M).group(1)
        slug = entry.parent.name
        references = {p.name:p.read_text() for p in (entry.parent/'references').glob('*.md')}
        body = {'name':slug,'slug':slug,'displayName':instructions.strip().splitlines()[0].lstrip('# '),
                'description':description,'instructions':instructions.strip(), 'references':references,'assets':{},
                'accessControl':{'type':'private'},'skillMetadata':{'category':'data'},'tags':['lighting','readonly','a2ui']}
        if slug in existing:
            if existing[slug]['ownerId'] != uid:
                raise RuntimeError('同名技能属于其他用户,拒绝覆盖')
            skill = api('/api/skills/'+existing[slug]['skillId'],'PUT',body)
        else:
            skill = api('/api/skills','POST',body)
        target = ROOT/'skills'/slug
        if target.exists():
            shutil.copytree(target, backup/slug)
        shutil.copytree(entry.parent,target,dirs_exist_ok=True)
        installed.append({'slug':slug,'skillId':skill['skillId'],'displayName':skill['displayName']})
    config = api('/api/admin/platform-config')
    agent = config['agent']
    agent['skills'] = list(dict.fromkeys([*agent['skills'],*[s['skillId'] for s in installed]]))
    agent['mcpServers'] = list(dict.fromkeys([*agent['mcpServers'],'lighting-query']))
    agent['interaction'].update(a2uiEnabled=True,allowSurfaceContextWrites=True,allowActionTriggeredRuns=True)
    marker = '### 照明六场景原型技能'
    if marker not in agent['instructions']:
        agent['instructions'] += '\n\n'+marker+'''\n
整夜单灯、单灯报警、RTU运行、RTU报警、四类能耗和日报对账，先加载相应lighting-* Skill，优先调用query_lighting固定只读查询。已集成查询内部继续经过sql_query_readonly；这与安全查询入口约束一致。标准场景不先临时生成SQL，不调用OpenViking写入案例。query_lighting结果经平台自动进入照明原型Workbench，聊天给短结论；不重复手拼卡片、JSON或HTML。
仅在固定工具不覆盖且用户确实要求额外业务查询时加载sql-safe-query，遵循其确认和只读执行流程。标准查询失败明确说明未完成，不自动换入口掩盖失败。历史恢复、在线配置、相位支路与历史挂载未知时明确缺口，不补零、不推断；未配置的导出、控制和通知能力不宣称可用。'''
    after = api('/api/admin/platform-config','PUT',{'agent':agent})
    assert after['agent']['model'] == before['agent']['model']
    assert after['agent']['permissions'] == before['agent']['permissions']
    for skill in installed:
        access = api('/api/skills/'+skill['skillId']+'/effective-access')
        assert access['gates']['skillAccess'] and access['gates']['rootBinding']
    save(backup/'platform-config-after.json',after)
    record = {'commit':commit,'backup':str(backup),'skills':installed,'adapter':'lighting-query',
              'status':'installed-awaiting-github-live-acceptance','images':{'backend':'lighting-skills-'+commit,'frontend':'lighting-skills-'+commit}}
    save(ROOT/'lighting-a2ui-deployment.json',record)
    print(json.dumps({'installed':installed,'backup':str(backup),'status':record['status']},ensure_ascii=False))


if __name__ == '__main__':
    main(sys.argv[1])
