from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config,pool
from app.config import Settings
from app.models import Base
from app import org_assessment,integrations,reference_data,inbound_sync,installation  # register extension metadata
from app import social_models
config=context.config
if config.config_file_name is not None:fileConfig(config.config_file_name)
target_metadata=Base.metadata

def url():return Settings().database_url

def run_migrations_offline():
    raise RuntimeError('Offline execution cannot verify an empty database; use an inspected online fresh installation')

def run_migrations_online():
    command = getattr(getattr(config, 'cmd_opts', None), 'cmd', None)
    command = command[0] if isinstance(command, tuple) else command
    if getattr(command, '__name__', '') in {'stamp', 'downgrade'}:
        raise RuntimeError('stamp/downgrade are forbidden for the fresh-only canonical lineage')
    section=config.get_section(config.config_ini_section) or {};section['sqlalchemy.url']=url()
    connectable=engine_from_config(section,prefix='sqlalchemy.',poolclass=pool.NullPool)
    with connectable.connect() as connection:
        settings = Settings()
        if settings.env == 'production':
            if connection.dialect.name != 'mysql': raise RuntimeError('MySQL 8.4 required')
            import sqlalchemy as sa
            version = str(connection.execute(sa.text('SELECT VERSION()')).scalar_one())
            if not version.startswith('8.4.') or 'mariadb' in version.lower(): raise RuntimeError('MySQL 8.4 required')
        installation.migration_preflight(connection)
        connection.commit()  # End inspection transaction before Alembic owns DML.
        context.configure(connection=connection,target_metadata=target_metadata,compare_type=True)
        with context.begin_transaction():context.run_migrations()
    connectable.dispose()

if context.is_offline_mode():run_migrations_offline()
else:run_migrations_online()
