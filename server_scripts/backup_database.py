import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path.home() / "PartsTrack"
DATABASE_PATH = BASE_DIR / "partstrack.db"
BACKUP_DIR = BASE_DIR / "backups"

RETENTION_DAYS = 7

BACKUP_DIR.mkdir(exist_ok=True)

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
backup_path = BACKUP_DIR / f"partstrack-{timestamp}.db"

try:
    # Create a consistent SQLite backup
    with sqlite3.connect(DATABASE_PATH) as source:
        with sqlite3.connect(backup_path) as destination:
            source.backup(destination)

    print(f"Backup completed successfully: {backup_path}")

    # Delete backups older than 7 days
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)

    for backup_file in BACKUP_DIR.glob("partstrack-*.db"):
        try:
            backup_timestamp = datetime.strptime(
                backup_file.stem,
                "partstrack-%Y-%m-%d_%H-%M-%S"
            )
        except ValueError:
            continue

        if backup_timestamp < cutoff:
            backup_file.unlink()
            print(f"Deleted expired backup: {backup_file.name}")

    print("Backup retention cleanup completed.")

except Exception as error:
    print(f"Backup or cleanup failed: {error}")
    raise
