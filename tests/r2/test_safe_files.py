import os
from pathlib import Path
import pytest
from app.safe_files import open_nofollow

def test_secure_file_roundtrip_and_exclusive_write(tmp_path):
    path=tmp_path/'合成附件.bin'
    with os.fdopen(open_nofollow(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL),'wb') as f:f.write(b'synthetic')
    with os.fdopen(open_nofollow(path,os.O_RDONLY),'rb') as f:assert f.read()==b'synthetic'
    with pytest.raises(OSError):open_nofollow(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
    assert path.read_bytes()==b'synthetic'

def test_secure_file_missing_and_directory_fail_closed(tmp_path):
    with pytest.raises(OSError):open_nofollow(tmp_path/'missing',os.O_RDONLY)
    if os.name=='nt':
        with pytest.raises(OSError):open_nofollow(tmp_path,os.O_RDONLY)

def test_secure_file_rejects_symlink(tmp_path):
    target=tmp_path/'target';target.write_bytes(b'protected')
    link=tmp_path/'link'
    try:link.symlink_to(target)
    except OSError:pytest.skip('OS does not permit creation of symbolic links')
    with pytest.raises(OSError):open_nofollow(link,os.O_RDONLY)
    assert target.read_bytes()==b'protected'

@pytest.mark.skipif(os.name!='nt',reason='Windows reparse parents')
def test_secure_file_rejects_junction_parent(tmp_path):
    import subprocess
    target=tmp_path/'target';target.mkdir();(target/'data').write_bytes(b'protected')
    junction=tmp_path/'junction'
    result=subprocess.run(['cmd','/c','mklink','/J',str(junction),str(target)],capture_output=True)
    if result.returncode:pytest.skip('OS does not permit junction creation')
    try:
        with pytest.raises(OSError):open_nofollow(junction/'data',os.O_RDONLY)
    finally:junction.rmdir()  # Remove the junction itself, never its target.
    assert (target/'data').read_bytes()==b'protected'

