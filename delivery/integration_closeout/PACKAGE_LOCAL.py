"""Build source/changes/evidence archives from an explicit locally audited base."""
from pathlib import Path
import argparse
import difflib
import hashlib
import json
import subprocess
import tempfile
import zipfile


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, base, out = args.root.resolve(), args.baseline.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    baseline_sha = '90a97f866e20974789bf985dad81e1a3f29c5891'
    def git(*params):
        return subprocess.check_output(['git', *params], cwd=root)
    names = git('ls-tree', '-r', '--name-only', '-z', baseline_sha).decode().split('\0')
    names += git('ls-files', '--others', '--exclude-standard', '-z').decode().split('\0')
    names += git('ls-files', '-z').decode().split('\0')
    names = sorted({name for name in names if name and (root/name).is_file()})
    if any((root/name).is_symlink() for name in names):
        raise SystemExit('Refused symlink source')
    names = [name for name in names if Path(name).suffix.lower() not in {'.ttf', '.otf', '.woff', '.woff2'}]
    patch = {'format': 'KEJI_INTEGRATION_CLOSEOUT_PATCH_V1', 'base_commit': baseline_sha,
             'working_commit': git('rev-parse', 'HEAD').decode().strip(), 'files': []}
    for name in names:
        raw = (root/name).read_bytes()
        old = (base/name).read_bytes() if (base/name).is_file() else None
        if old == raw:
            continue
        normalized = old.replace(b'\r\n', b'\n') if old is not None else None
        before = normalized.decode('utf-8').splitlines(keepends=True) if normalized is not None else []
        after = raw.decode('utf-8').splitlines(keepends=True)
        operations = [{'start': i, 'end': j, 'text': ''.join(after[a:b])}
                      for tag, i, j, a, b in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes()
                      if tag != 'equal']
        patch['files'].append({'path': name, 'base_normalized_sha256': sha(normalized) if normalized is not None else None,
                               'result_sha256': sha(raw), 'operations': operations})
    payload = json.dumps(patch, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    kit = out/'02_修改融合包_Keji_Integration_Closeout_R1.zip'
    with zipfile.ZipFile(kit, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr('patch.json', payload)
        archive.write(root/'delivery/integration_closeout/APPLY_PATCH.py', 'APPLY_PATCH.py')
        archive.write(root/'docs/INTEGRATION_CLOSEOUT_R1.md', 'README_交付说明.md')
        archive.write(root/'evidence/integration-closeout/verification-summary.json', 'verification-summary.json')
    source = out/'01_完整源码_Keji_Integration_Closeout_R1.zip'
    with zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in names:
            archive.write(root/name, name)
    evidence = out/'03_测试证据_Keji_Integration_Closeout_R1.zip'
    evidence_root = root/'evidence/integration-closeout'
    with zipfile.ZipFile(evidence, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(evidence_root.rglob('*')):
            if path.is_file() and path.suffix.lower() in {'.json', '.xml', '.log', '.png', '.zip'}:
                archive.write(path, path.relative_to(evidence_root).as_posix())
    for path in (source, kit, evidence):
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
    report = {'base_commit': baseline_sha, 'working_commit': patch['working_commit'],
              'source_files': len(names), 'changed_files': len(patch['files']),
              'archives': [{'name': path.name, 'bytes': path.stat().st_size,
                            'sha256': sha(path.read_bytes())} for path in (source, kit, evidence)]}
    (out/'SHA256_交付校验.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (out/'00_先看这里.md').write_bytes((root/'docs/INTEGRATION_CLOSEOUT_R1.md').read_bytes())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
