from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    # Explicit DDL; no application metadata.create_all or destructive startup.
    for statement in Path(__file__).with_name("0001.sql").read_text().split(";\n"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    raise RuntimeError("Restore backup; M0 migration is intentionally forward-only")
