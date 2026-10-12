"""School delivery must keep source and reject local/internal payloads."""
from pathlib import Path
import zipfile
import pytest
from school_package import EXCLUDED_FILES,package_names,scan_package


def fixture(root,name,content='fixture'):
    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
    return path


def test_school_selection_preserves_internal_source_and_product_assets(tmp_path):
    excluded=[*EXCLUDED_FILES,'docs/历史版本/old.md','docs/10.10/old.md','docs/学校对接资料_20261009/原始资料.xlsx','开始部署.sh','先读我_部署与演示.html',
              'backend/evidence/local.sqlite','backend/runtime/account.json','frontend/shot.png','deploy/.env',
              'backend/cache.db','delivery/accounts.json','deploy/secrets/admin_password','docs/test-accounts.txt','frontend/assets/screenshot.png']
    kept=['backend/app/main.py','scripts/install.sh','scripts/deployment_config.py','README_START_HERE.md',
          'frontend/assets/school.png','tests/p0/test_example.py','docs/USER_MANUAL.md','delivery/tests/test_deploy_guards.py']
    for name in excluded+kept:fixture(tmp_path,name)
    assert package_names(tmp_path)==sorted(kept)
    assert all((tmp_path/name).is_file() for name in excluded)


def test_school_selection_keeps_workbook_and_excludes_its_inspection_file(tmp_path):
    name='acceptance/R11_PDF_101_Clause_Tracker_交付版_20261012.xlsx'
    fixture(tmp_path,name)
    fixture(tmp_path,name+'.inspect.ndjson')
    assert package_names(tmp_path)==[name]
    assert (tmp_path/(name+'.inspect.ndjson')).is_file()


@pytest.mark.parametrize('name',['backend/local.sqlite','runtime/private.json','docs/screenshot.jpg','deploy/.env','docs/20261012_复审与打包接收.md'])
def test_staged_scan_rejects_private_or_internal_payload(tmp_path,name):
    fixture(tmp_path,name)
    assert scan_package(tmp_path,[name])['status']=='BLOCKED'


@pytest.mark.parametrize('content',['C:/Users/local/secret','C:\\Users\\local\\secret','Codex 内部记录','Claude 内部记录','合成演示','10.20.30.40'])
def test_internal_or_host_content_in_school_document_blocks_release(tmp_path,content):
    fixture(tmp_path,'docs/USER_MANUAL.md',content)
    assert scan_package(tmp_path,['docs/USER_MANUAL.md'])['status']=='BLOCKED'


def test_program_technical_names_and_localhost_get_explicit_retention_reasons(tmp_path):
    fixture(tmp_path,'tests/p0/test_codex.py','Codex regression 10.20.30.40')
    fixture(tmp_path,'README_START_HERE.md','http://127.0.0.1:8773 0.0.0.0')
    report=scan_package(tmp_path,package_names(tmp_path))
    assert report['status']=='PASS' and len(report['retained_with_reason'])==2
    assert all(row['reason'] for row in report['retained_with_reason'])


def test_real_machine_path_in_program_is_not_exempted(tmp_path):
    fixture(tmp_path,'backend/app/main.py','C:/Users/local/secret')
    assert scan_package(tmp_path,['backend/app/main.py'])['status']=='BLOCKED'


def test_inventory_source_reference_does_not_exempt_internal_prose(tmp_path):
    name='tests/p0/test_codex_example.py'
    fixture(tmp_path,name)
    document='docs/源代码与资料移交清单.md'
    fixture(tmp_path,document,'| `'+name+'` | 123 |')
    report=scan_package(tmp_path,package_names(tmp_path))
    assert report['status']=='PASS' and report['retained_with_reason'][0]['reason']
    fixture(tmp_path,document,'Codex 内部记录 | `'+name+'` |')
    assert scan_package(tmp_path,package_names(tmp_path))['status']=='BLOCKED'


def test_office_document_xml_is_scanned_for_internal_content(tmp_path):
    path=tmp_path/'docs/report.xlsx';path.parent.mkdir()
    with zipfile.ZipFile(path,'w') as archive:archive.writestr('xl/sharedStrings.xml','<t>C:/Users/local/private</t>')
    assert scan_package(tmp_path,['docs/report.xlsx'])['status']=='BLOCKED'


def test_school_selection_rejects_links(tmp_path):
    path=fixture(tmp_path,'backend/real.py')
    try:(tmp_path/'backend/link.py').symlink_to(path)
    except OSError:pytest.skip('当前操作系统不允许创建符号链接')
    with pytest.raises(ValueError,match='链接'):package_names(tmp_path)
