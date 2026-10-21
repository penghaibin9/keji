"""Incremental migration must preserve the signed original baseline and existing rows."""
from pathlib import Path
import copy
import pytest
from alembic import command, op
from alembic.config import Config
from sqlalchemy import create_engine, text, inspect, ForeignKeyConstraint
from app.installation import require_canonical
from app.database_snapshot import take_snapshot, validate_snapshot
from app.settings_catalog import DEFAULT_BUSINESS_DICTIONARY


@pytest.mark.parametrize('legacy_dictionary',[False,True])
def test_baseline_upgrade_preserves_existing_data_and_checks_full_schema(tmp_path,monkeypatch,legacy_dictionary):
    root=Path(__file__).resolve().parents[2]
    url='sqlite:///'+str(tmp_path/'school.sqlite')
    monkeypatch.setenv('ND_ENV','test');monkeypatch.setenv('ND_DATABASE_URL',url)
    cfg=Config(str(root/'backend/alembic.ini'))
    command.upgrade(cfg,'20260918_0001')
    engine=create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO settings (`key`,value,version) VALUES ('preserved','{}',7)"))
        if legacy_dictionary:
            value=copy.deepcopy(DEFAULT_BUSINESS_DICTIONARY)
            value['status_labels'].pop('SOCIAL')
            value['status_labels']['DRAFT']='学校草稿'
            conn.execute(text("INSERT INTO settings (`key`,value,version) VALUES ('business_dictionary',:value,8)"),{'value':__import__('json').dumps(value)})
        proof=require_canonical(conn,allow_baseline=True)
    create_table=op.create_table
    def checked_create_table(name,*columns,**kwargs):
        required={fk.target_fullname.split('.')[0] for column in columns
                  if isinstance(column,ForeignKeyConstraint) for fk in column.elements}
        assert required <= set(inspect(op.get_bind()).get_table_names()), f'{name}: foreign-key target must already exist'
        return create_table(name,*columns,**kwargs)
    monkeypatch.setattr(op,'create_table',checked_create_table)
    command.upgrade(cfg,'head')
    with engine.connect() as conn:
        current=require_canonical(conn)
        assert current['installation_id']==proof['installation_id']
        assert conn.execute(text("SELECT version FROM settings WHERE `key`='preserved'")).scalar_one()==7
        if legacy_dictionary:
            row=conn.execute(text("SELECT value,version FROM settings WHERE `key`='business_dictionary'")).one()
            value=__import__('json').loads(row.value)
            assert row.version==9 and value['status_labels']['DRAFT']=='学校草稿'
            assert value['status_labels']['SOCIAL']=='社会培训认定'
        assert len([t for t in inspect(conn).get_table_names() if t.startswith('social_')])==6
    snapshot=take_snapshot(engine,require_mysql=False)
    assert validate_snapshot(snapshot)==snapshot
    assert len(snapshot['tables'])==56
    assert snapshot['tables']['form_drafts']['rows']==0
    assert snapshot['tables']['settings']['rows']==(2 if legacy_dictionary else 1)
    engine.dispose()
