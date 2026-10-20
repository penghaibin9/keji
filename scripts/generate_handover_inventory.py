"""Generate school delivery hashes without recursive self-hashes or private data."""
import argparse
import hashlib
import json
from pathlib import Path
from school_package import package_names, scan_package

ROOT = Path(__file__).resolve().parents[1]
GENERATED = {'docs/源代码与资料移交清单.md', 'docs/验收材料清单.md', 'docs/交付文件校验清单.json'}


def generate(root):
    names = [name for name in package_names(root) if name not in GENERATED]
    report = scan_package(root, names)
    assert report['status'] == 'PASS', report['blockers']
    files = {name: {'sha256': hashlib.sha256((root / name).read_bytes()).hexdigest(),
                    'size': (root / name).stat().st_size} for name in names}
    version = json.loads((root / 'delivery/R11_BASE_MANIFEST.json').read_text(encoding='utf-8'))
    schema = json.loads((root / 'docs/交付结构清单.json').read_text(encoding='utf-8'))
    result = {'kind': 'school_delivery_working_tree_snapshot', 'program_baseline': version['input_zip_sha256'],
              'migration_heads': schema['migration_heads'], 'file_count': len(files), 'files': files,
              'self_excluded': sorted(GENERATED), 'final_archive_hash_source': 'release-metadata.json and SHA256SUMS'}
    (root / 'docs/交付文件校验清单.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    lines = ['# 源代码与资料移交清单（交付候选）', '',
             '版本日期：2026-10-12。以审批精简版为施工基础，包含本轮导入批次、考核目标、码表展示和交付整理修复。',
             '源码基础提交与施工修改另列在外层版本元数据；当前程序摘要才是本次源码字节的识别依据，不能把基础提交号当作全部新修复的提交号。', '',
             f"程序摘要：`{version['input_zip_sha256']}`。迁移头：`{', '.join(schema['migration_heads'])}`。", '',
             f"业务表 {schema['table_count']} 张、字段 {schema['column_count']} 个、接口 {schema['api_route_count']} 项。", '',
             '学校取得本项目定制源代码、字段映射、数据库结构与接口资料的移交方式，仍需在介质签收或学校托管方案中确认。',
             '不包含真实数据、运行数据库、附件、密钥、密码、会话或开发内部材料。账号与密钥由学校管理员在受限配置目录配置及交接。', '',
             '## 文件与摘要', '', f'本清单列 {len(files)} 份源文件或交付资料。再生成入口：`scripts/generate_handover_inventory.py`。',
             '本文件、验收材料清单和机器清单不记录自身摘要，避免循环；安装包最终的 `PACKAGE_MANIFEST.json` 会记录它们的摘要。',
             '源码压缩包、安装包、离线镜像及分卷摘要取自外层 `release-metadata.json` 和 `SHA256SUMS`，不能在压缩包里写入该压缩包自身摘要。', '',
             '| 文件 | 字节数 | SHA256（文件校验摘要） |', '|---|---|---|']
    lines += [f"| `{name}` | {row['size']} | `{row['sha256']}` |" for name, row in files.items()]
    lines += ['', '## 双方签收', '', '移交介质或学校托管地址：【待双方填写】。学校接收人、供应商负责人、日期及签章：【待双方填写】。',
              '学校所有权及双方服务责任以合同和正式签收为准；本次生成文件清单不等于完成源码归属签认。', '']
    (root / 'docs/源代码与资料移交清单.md').write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    documents = ['USER_MANUAL.md', 'ADMIN_OPERATIONS_MANUAL.md', '权限配置说明.md', '培训方案与课件.md',
                 '数据字典.md', '数据字典.xlsx', 'API_ENDPOINT_CATALOG.md', '测试报告_20261012.md',
                 '数据中台字段映射核对表_20261012.md', '学校接口字段映射模板_20261012.json',
                 '安全配置与等保自查表.md', '第三方组件与许可证清单.md', '101条款现场待办_20261012.md']
    acceptance = ['# 验收材料清单（交付候选）', '',
                  '日期：2026-10-12。旧历史统计不作为当前验收结论。101条采购核对详见当前跟踪表和逐条明细。', '',
                  '本机合成数据测试、真实本地生产数据库演练、学校真实接口、性能和双方签章分别记载，不能互相代替。', '',
                  '| 资料 | 版本日期 | 文件摘要 | 当前状态 |', '|---|---|---|---|']
    for name in documents:
        row = files.get('docs/' + name)
        acceptance.append(f"| `docs/{name}` | 2026-10-12 | `{row['sha256']}` | 已生成；相应学校实测或签认另列 |" if row else
                          f'| `docs/{name}` | 2026-10-12 | 尚未生成 | 未完成 |')
    tracker = 'acceptance/R11_PDF_101_Clause_Tracker_交付版_20261012.xlsx'
    if tracker in files:
        acceptance.append(f"| `{tracker}` | 2026-10-12 | `{files[tracker]['sha256']}` | 101条全覆盖；待逐条现场签认 |")
    acceptance += ['', '## 学校现场仍需出示', '',
                   '- 正式安装及空机恢复记录、四类正常账号浏览器办理和权限检查。',
                   '- 学校统一认证、数据中台、消息中心与省平台真实联调签认；尚缺协议或授权的数据类型须书面说明。',
                   '- 学校手工样本与系统双轨比对、性能条款13.7/13.8实测、试运行记录、问题整改闭环。',
                   '- 售后服务承诺书、合同责任与源码移交签收、实际培训签到、操作考核及反馈。',
                   '- 已知依赖漏洞处理或针对性评估、集中日志六个月留存和加密异地备份方案确认。', '',
                   '本材料清单不签署服务承诺、不代填学校制度、不替代学校盖章验收。', '']
    (root / 'docs/验收材料清单.md').write_text('\n'.join(acceptance), encoding='utf-8', newline='\n')
    return {'file_count': len(files), 'program_baseline': result['program_baseline']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    print(json.dumps(generate(parser.parse_args().root), ensure_ascii=False))
