from sqlalchemy import inspect, text

from app import create_app, db
from app.models import ReceiptImport


def add_column_if_missing(connection, table_name, column_name, definition):
    inspector = inspect(connection)

    existing_columns = {
        column["name"]
        for column in inspector.get_columns(table_name)
    }

    if column_name in existing_columns:
        print(f"SKIPPED: {table_name}.{column_name} already exists.")
        return

    connection.execute(
        text(
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name} {definition}"
        )
    )

    print(f"ADDED: {table_name}.{column_name}")


def migrate_database():
    app = create_app()

    with app.app_context():

        print("")
        print("=====================================")
        print("    PartsTrack Database Migration")
        print("=====================================")
        print("")

        if db.engine.dialect.name != "sqlite":
            raise RuntimeError("This migration requires SQLite.")

        print(f"Database: {db.engine.url.database}")
        print("")

        # Apply missing database columns.
        with db.engine.begin() as connection:

            add_column_if_missing(
                connection,
                "work_item",
                "requires_order_verification",
                "BOOLEAN NOT NULL DEFAULT 0"
            )

            add_column_if_missing(
                connection,
                "parts_order",
                "created_from_receipt",
                "BOOLEAN NOT NULL DEFAULT 0"
            )

        # Ensure the Receipt Import History table exists.
        ReceiptImport.__table__.create(
            db.engine,
            checkfirst=True
        )

        print("VERIFIED: receipt_import table exists.")

        # Verify the final database schema.
        inspector = inspect(db.engine)

        required_columns = {
            "work_item": "requires_order_verification",
            "parts_order": "created_from_receipt"
        }

        for table_name, column_name in required_columns.items():

            columns = {
                column["name"]
                for column in inspector.get_columns(table_name)
            }

            if column_name not in columns:
                raise RuntimeError(
                    f"Migration verification failed: "
                    f"{table_name}.{column_name} is missing."
                )

        if not inspector.has_table("receipt_import"):
            raise RuntimeError(
                "Migration verification failed: "
                "receipt_import table is missing."
            )

        print("")
        print("SUCCESS: Database migration completed.")
        print("")


if __name__ == "__main__":
    migrate_database()