"""招标第2、6项：业务办理各页按角色限定数据范围。教研室只读本教研室教师负责或参与的项目，教师只看本人相关课程。"""
from conftest import auth, post
from test_social_training import setup_social, import_rows, row, detail  # noqa: F401  复用同一套隔离夹具


def workspace(client, section):
    r = client.get('/api/social/workspace?section=' + section); assert r.status_code == 200, r.text; return r.json()


def test_dept_reads_own_teachers_projects_read_only(setup_social, client2):
    pid = setup_social
    auth(client2, 'reviewer'); assert import_rows(client2, pid, [row()]).status_code == 200
    auth(client2, 'depthead')
    assert [p['id'] for p in workspace(client2, 'projects')['projects']] == [pid]
    d = detail(client2, 'social_project', pid)
    assert d['view_only'] is True and d['facts']['units']
    assert [c['code'] for c in workspace(client2, 'courses')['courses']] == ['SOC-C1']
    version = d['item']['version']
    r = post(client2, f'/api/social/projects/{pid}/actions', {'action': 'refile', 'expected_version': version, 'reason': '越权尝试'})
    assert r.status_code == 403
    r = post(client2, '/api/social/resources', {'kind': 'base', 'org_id': 'college1', 'code': 'B-X', 'name': '越权基地', 'recognition': '无', 'reason': '越权尝试'})
    assert r.status_code == 403
    auth(client2, 'otherdept')
    assert workspace(client2, 'projects')['projects'] == [] and workspace(client2, 'courses')['courses'] == []
    assert client2.get('/api/social/objects/social_project/' + pid).status_code == 403


def test_teacher_courses_limited_to_own_projects(setup_social, client2):
    auth(client2, 'teacher')
    assert [c['code'] for c in workspace(client2, 'courses')['courses']] == ['SOC-C1']
    auth(client2, 'otherteacher')
    assert workspace(client2, 'courses')['courses'] == []
    assert client2.get('/api/social/resource-stats').status_code == 403
    auth(client2, 'collegehead')
    assert [c['code'] for c in workspace(client2, 'courses')['courses']] == ['SOC-C1']
