"""Verified text-only source patch. No database, network, git commit or push.

Default mode checks only. --apply requires every selected source file to match the
recorded base, then creates a backup before writing. Locally modified files cause
refusal rather than guessed merges. Run from an extracted delivery change kit.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import shutil
import uuid


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    payload = json.loads((args.bundle/'patch.json').read_text(encoding='utf-8'))
    if payload.get('format') != 'KEJI_INTEGRATION_CLOSEOUT_PATCH_V1':
        raise SystemExit('Unknown patch format')
    prepared, seen = [], set()
    allowed = {'backend', 'frontend', 'scripts', 'tests', 'docs', 'delivery',
               '.gitattributes', '.gitignore', 'README_START_HERE.md'}
    for item in payload['files']:
        relative = PurePosixPath(item['path'])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[0] not in allowed:
            raise SystemExit('Unsafe patch path')
        path = root.joinpath(*relative.parts)
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root):
            raise SystemExit('Refused symlink: '+str(relative))
        if not path.resolve().is_relative_to(root) or os.path.normcase(str(path)) in seen:
            raise SystemExit('Unsafe or repeated patch path')
        seen.add(os.path.normcase(str(path)))
        raw = path.read_bytes() if path.is_file() else None
        if raw is not None and sha(raw) == item['result_sha256']:
            continue
        normalized = raw.replace(b'\r\n', b'\n') if raw is not None else None
        if item['base_normalized_sha256'] is None:
            if raw is not None:
                raise SystemExit('New file already exists: '+str(relative))
            before = []
        else:
            if normalized is None or sha(normalized) != item['base_normalized_sha256']:
                raise SystemExit('Local changes or wrong base: '+str(relative))
            before = normalized.decode('utf-8').splitlines(keepends=True)
        output, cursor = [], 0
        for operation in item['operations']:
            start, end = operation['start'], operation['end']
            if not 0 <= cursor <= start <= end <= len(before):
                raise SystemExit('Invalid patch range')
            output.extend(before[cursor:start])
            output.append(operation['text'])
            cursor = end
        output.extend(before[cursor:])
        data = ''.join(output).encode('utf-8')
        if sha(data) != item['result_sha256']:
            raise SystemExit('Reconstructed checksum mismatch: '+str(relative))
        prepared.append((path, relative, raw, data))
    print('Verified source files:', len(payload['files']), '| pending writes:', len(prepared))
    if not args.apply:
        print('CHECK ONLY. No files changed. Add --apply after review.')
        return
    if not prepared:
        print('Already applied. No files changed.')
        return
    backup = root/('.keji-closeout-backup-'+uuid.uuid4().hex[:12])
    backup.mkdir()
    for path, relative, raw, data in prepared:
        if raw is not None:
            destination = backup.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
    written = []
    try:
        for path, relative, raw, data in prepared:
            current = path.read_bytes() if path.is_file() else None
            if current != raw:
                raise RuntimeError('File changed after preflight: '+str(relative))
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name('.'+path.name+'.keji-'+uuid.uuid4().hex+'.tmp')
            temporary.write_bytes(data)
            os.replace(temporary, path)
            written.append((path, raw, data))
    except Exception:
        for path, raw, data in reversed(written):
            if not path.is_file() or path.read_bytes() != data:
                continue  # Never overwrite a concurrent editor's changes.
            if raw is None:
                path.unlink()
            else:
                path.write_bytes(raw)
        print('Patch interrupted. Original files are backed up at:', backup)
        raise
    print('Applied', len(prepared), 'source files. Backup:', backup)
    print('No database operations, dependency installation, commit or push were performed.')


if __name__ == '__main__':
    main()
