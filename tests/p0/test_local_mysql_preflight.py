"""Native Windows CLI reports a closed gate before POSIX-only imports."""
import json,os,subprocess,sys
from pathlib import Path
import pytest

@pytest.mark.skipif(os.name=='posix',reason='native Windows entry-point regression')
def test_non_posix_cli_records_blocked_without_commands(tmp_path):
    script=Path(__file__).resolve().parents[2]/'scripts/run_mysql_acceptance.py'
    result=subprocess.run([sys.executable,str(script),'--run-isolated','--output',str(tmp_path)],capture_output=True,text=True)
    assert result.returncode==2 and 'Traceback' not in result.stderr
    report=json.loads((tmp_path/'mysql_acceptance.json').read_text(encoding='utf-8'))
    assert report['reason']==['POSIX_RUNTIME_REQUIRED']
    assert not report['mysql_tested'] and not report['restore_executed']
    assert not report['production_contacted'] and not report['fallback_engine_used']
