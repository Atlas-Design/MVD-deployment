from playhouse.migrate import SqliteMigrator, migrate

from database.db import db
from database.job import Job

migrator = SqliteMigrator(db)


def run_migrations():
    try:
        db.create_tables([Job])
        with db.atomic():
            migrate(
                migrator.add_column(
                    Job._meta.table_name,
                    Job.logs.column_name,
                    Job.logs
                )
            )
    except:
        pass