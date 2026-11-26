from alembic import context
from sqlalchemy.engine import Connection

from taskflow.config import Settings
from taskflow.database import make_engine
from taskflow.models import Base


def run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=Settings().database_url, target_metadata=Base.metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    existing = context.config.attributes.get("connection")
    if existing is not None:
        run(existing)
    else:
        engine = make_engine(Settings().database_url)
        try:
            with engine.connect() as connection:
                run(connection)
        finally:
            engine.dispose()
