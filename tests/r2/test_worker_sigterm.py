"""The worker must stop on SIGTERM well inside compose's 45s stop_grace_period.

As PID 1 in its container the worker gets no default SIGTERM handling, so before this fix
`docker compose stop` always ended in SIGKILL (exit 137) and deploys aborted at stopping_writers.
"""
import logging,os,signal,threading,time
import pytest
from app.models import Task


@pytest.fixture
def restore_signals():
    saved={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT,signal.SIGALRM)}
    yield
    signal.alarm(0)
    for s,h in saved.items():signal.signal(s,h)


def sigterm_after(seconds):
    timer=threading.Timer(seconds,os.kill,(os.getpid(),signal.SIGTERM));timer.start();return timer


def test_idle_worker_exits_zero_on_sigterm(app2,monkeypatch,restore_signals):
    import app.worker as worker
    calls=[]
    monkeypatch.setattr(worker,'run_once',lambda *a,**k:calls.append(1) or {'status':'IDLE','claimed':False})
    sigterm_after(0.3);started=time.monotonic()
    assert worker.main(app2.state.settings,poll_seconds=0.05)==0
    assert time.monotonic()-started<3 and calls


def test_busy_worker_finishes_current_task_within_grace(app2,monkeypatch,restore_signals):
    import app.worker as worker
    done=[]
    def run_once(*a,**k):
        time.sleep(0.6);done.append(1);return {'status':'DONE','claimed':True}
    monkeypatch.setattr(worker,'run_once',run_once)
    sigterm_after(0.2)
    assert worker.main(app2.state.settings,stop=worker.StopSignal(grace=5),poll_seconds=0.05)==0
    assert done==[1]


def test_busy_worker_abandons_task_after_grace_and_leaves_it_retryable(app2,monkeypatch,restore_signals,caplog):
    import app.worker as worker
    with app2.state.sessions.begin() as db:
        task=Task(kind='sync',owner_id='schooladmin',key='SIGTERM-ABANDON',payload={},state='PENDING')
        db.add(task);db.flush();ident=task.id
    def slow(db,task,registry):time.sleep(60)
    monkeypatch.setattr(worker,'process_sync_task_once',slow)
    sigterm_after(0.5);started=time.monotonic()
    with caplog.at_level(logging.WARNING,logger='app.worker'):
        assert worker.main(app2.state.settings,stop=worker.StopSignal(grace=1),poll_seconds=0.05)==0
    assert time.monotonic()-started<10
    assert 'retried' in caplog.text
    with app2.state.sessions() as db:
        task=db.get(Task,ident)
        # Rolled back, not marked FAILED: the lease simply expires and another run picks it up.
        assert task.state=='PENDING' and task.attempts==0
