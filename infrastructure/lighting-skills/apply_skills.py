"""Update installed Skills after deploying this commit; never executes business SQL."""

import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

ROOT = Path('/opt/ai-protocol-platform')
SOURCE = Path(__file__).resolve().parents[2]


def main(commit, skills_commit):
    container = json.loads(subprocess.check_output(['docker', 'inspect', 'ai-protocol-platform-backend-1']))[0]
    assert container['Config']['Labels']['org.opencontainers.image.revision'] == commit
    env = dict(item.split('=', 1) for item in container['Config']['Env'] if '=' in item)
    token = None

    def api(path, method='GET', data=None):
        request = urllib.request.Request('http://127.0.0.1:1956' + path, method=method,
            data=None if data is None else json.dumps(data, ensure_ascii=False).encode(),
            headers={'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + token} if token else {})})
        with urllib.request.urlopen(request, timeout=60) as response:
            return None if response.status == 204 else json.load(response)

    token = api('/api/auth/login', 'POST', {
        'email': env['SELFHOST_ADMIN_EMAIL'], 'password': env['SELFHOST_ADMIN_PASSWORD'],
    })['access_token']
    config = api('/api/admin/platform-config')
    agent = config['agent']
    installed = {skill['slug']: skill for skill in api('/api/skills')}
    assert 'sql-safe-query' in installed, 'Install the existing safety Skill first'
    assert {'mcp-sql-http', 'sql-safe-query-examples'} <= set(agent['mcpServers'])
    assert installed['sql-safe-query']['skillId'] in agent['skills']
    records = []
    for source in sorted((SOURCE / 'skills').glob('lighting-*/SKILL.md')):
        old = installed[source.parent.name]
        body = {'instructions': source.read_text(encoding='utf-8').split('---', 2)[2].strip()}
        body['references'] = {str(path.relative_to(source.parent / 'references')): path.read_text(encoding='utf-8')
                              for path in (source.parent / 'references').rglob('*') if path.is_file()}
        updated = api('/api/skills/' + old['skillId'], 'PUT', body)
        assert updated['skillId'] == old['skillId']
        records.append({'skillId': old['skillId'], 'slug': source.parent.name})
    replacement = '''### 照明六场景原型技能

所有照明业务查询先加载 sql-safe-query 和相关 lighting-* 技能，根据当前对话检索可信案例、核实口径、动态生成只读 SQL。案例查找只使用技能指定的 find/read/grep，不调用 search；无可信案例时用 sql_retrieve_examples。SQL 唯一执行入口是 sql_query_readonly，不调用 query_lighting 或固定场景查询服务。
原型结构严格遵循已加载技能 references/presentation.schema.json，列类型只能为 text/number/time，不写 integer/numeric/boolean/datetime。
展示时间字段保留真实时区，generated_at 直接用 CURRENT_TIMESTAMP 写入 JSON，不用 AT TIME ZONE 后拼 OF 或 to_char 造偏移。
历史 anchor/evidence.at 等必须带经可信资料确认的时区；无时区且口径未核实则置 null 并记 missing，不能猜测或隐式强转。lighting_presentation_error 表示页面校验失败，按字段错误修正动态 SQL 后重查，不另填事实。
只要数字时返回实际聚合结果；需要原型页面时，按业务技能 runtime.md 由本次动态 SQL 返回 lighting-query/v1 payload，平台从真实 SQL 回包自动展示，不调用展示工具重新填写事实。先完成安全查询，再处理展示；查询失败不能用零值或编造卡片掩盖。
保留安全 SQL 技能的案例复用与沉淀流程；交互追查或用户明确要求只读时不写案例。时间、范围、报警状态、分组和指标都以当前对话及可信业务口径为准，不能用固定模板覆盖用户条件。未核实的历史恢复、在线标准和历史归属明确留缺口。
'''
    instructions = agent['instructions']
    marker = '### 照明六场景原型技能'
    agent['instructions'] = (re.sub(r'(?ms)^### 照明六场景原型技能\n.*?(?=^### |\Z)',
                                    replacement + '\n', instructions)
                             if marker in instructions else instructions + '\n\n' + replacement)
    agent['mcpServers'] = [name for name in agent['mcpServers'] if name != 'lighting-query']
    after = api('/api/admin/platform-config', 'PUT', {'agent': agent})
    assert after['agent']['model'] == config['agent']['model']
    assert after['agent']['permissions'] == config['agent']['permissions']
    old_server = api('/api/admin/mcp-servers/lighting-query')
    if old_server.get('enabled'):
        body = {key: old_server[key] for key in ('url', 'transport', 'description', 'allowedUserIds')}
        api('/api/admin/mcp-servers/lighting-query', 'PUT', {**body, 'enabled': False})
    record_path = ROOT / 'lighting-a2ui-deployment.json'
    record = json.loads(record_path.read_text())
    record.update(commit=commit, skills_commit=skills_commit, skills=records, query_mode='sql-safe-query', status='awaiting-github-acceptance')
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print('Six Skills now use dynamic safe SQL; legacy query service unbound and disabled.')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
