$ErrorActionPreference = "Stop"

$Server = "partstrack"

Write-Host ""
Write-Host "====================================="
Write-Host "       PartsTrack Deployment"
Write-Host "====================================="
Write-Host ""

# Commands executed on the Debian server
$RemoteScript = @'
set -e

cd /home/mcmillanparts2518/PartsTrack

echo "Checking production Git status..."

if [ "$(git branch --show-current)" != "main" ]; then
    echo "ERROR: Production is not on main."
    exit 1
fi

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "ERROR: Production has uncommitted tracked changes."
    git status --short
    exit 1
fi

echo "Checking production database..."

if [ ! -s partstrack.db ]; then
    echo "ERROR: Production database is missing or empty."
    exit 1
fi

echo "Fetching latest main branch..."
git fetch origin main

# Confirm a fast-forward merge is possible before stopping.
if ! git merge-base --is-ancestor HEAD origin/main; then
    echo "ERROR: Production cannot be fast-forwarded."
    exit 1
fi

# Confirm the migration script exists in the incoming code.
if ! git cat-file -e origin/main:migrate_db.py; then
    echo "ERROR: Database migration script is missing."
    exit 1
fi

PREVIOUS_COMMIT=$(git rev-parse HEAD)

echo "Previous production commit: $PREVIOUS_COMMIT"

BACKUP_FILE=""

# Report recovery information if deployment fails.
deployment_failed() {
    echo ""
    echo "====================================="
    echo "       DEPLOYMENT FAILED"
    echo "====================================="
    echo "Previous commit: $PREVIOUS_COMMIT"
    echo "Database backup: ${BACKUP_FILE:-Not verified}"
    echo ""
    echo "Check the application service status before recovery."
    echo "Do not automatically restore the database."
}

trap deployment_failed ERR

echo "Stopping PartsTrack..."
sudo -n systemctl stop partstrack.service

echo "Backing up production database..."

BACKUP_START=$(date +%s)

sudo -n systemctl start partstrack-backup.service

BACKUP_RESULT=$(systemctl show partstrack-backup.service \
    --property=Result --value)

if [ "$BACKUP_RESULT" != "success" ]; then
    echo "ERROR: Database backup service failed."
    deployment_failed
    exit 1
fi

# Locate the newest fresh, nonempty backup.
NEWEST_BACKUP_TIME=0

for backup in /home/mcmillanparts2518/PartsTrack/backups/partstrack-*.db; do
    [ -f "$backup" ] || continue
    [ -s "$backup" ] || continue

    BACKUP_TIME=$(stat -c %Y "$backup")

    if [ "$BACKUP_TIME" -ge "$BACKUP_START" ] && \
       [ "$BACKUP_TIME" -ge "$NEWEST_BACKUP_TIME" ]; then

        BACKUP_FILE="$backup"
        NEWEST_BACKUP_TIME="$BACKUP_TIME"
    fi
done

if [ -z "$BACKUP_FILE" ]; then
    echo "ERROR: No fresh database backup was found."
    deployment_failed
    exit 1
fi

echo "Backup located: $BACKUP_FILE"

echo "Verifying database backup integrity..."

/usr/bin/python3 - "$BACKUP_FILE" <<'PYTHON'
import sqlite3
import sys
from pathlib import Path

backup_path = Path(sys.argv[1]).resolve()

connection = sqlite3.connect(
    backup_path.as_uri() + "?mode=ro",
    uri=True
)

try:
    result = connection.execute(
        "PRAGMA integrity_check"
    ).fetchall()

    if result != [("ok",)]:
        raise RuntimeError(
            f"Backup integrity check failed: {result}"
        )

    print("SUCCESS: Backup integrity check passed.")

finally:
    connection.close()
PYTHON

echo "Updating production code..."
git merge --ff-only origin/main

echo "Installing Python dependencies..."
/home/mcmillanparts2518/PartsTrack/.venv/bin/python \
    -m pip install -r requirements.txt

echo "Running database migrations..."
/home/mcmillanparts2518/PartsTrack/.venv/bin/python \
    migrate_db.py

echo "Starting PartsTrack..."
sudo -n systemctl start partstrack.service

echo "Checking application service..."

if ! systemctl is-active --quiet partstrack.service; then
    echo "ERROR: PartsTrack service is not running."
    deployment_failed
    exit 1
fi

echo "Checking PartsTrack website..."

HEALTH_OK=false

for attempt in 1 2 3 4 5; do
    HTTP_STATUS=$(curl -L -s -o /dev/null -w "%{http_code}" \
        --max-time 10 \
        https://mmpartstrack.duckdns.org) || HTTP_STATUS="000"

    if [ "$HTTP_STATUS" = "200" ]; then
        HEALTH_OK=true
        break
    fi

    echo "Website returned HTTP $HTTP_STATUS. Retrying..."
    sleep 3
done

if [ "$HEALTH_OK" != "true" ]; then
    echo "ERROR: PartsTrack website health check failed."
    deployment_failed
    exit 1
fi

echo "PartsTrack website is responding successfully."

trap - ERR

echo ""
echo "SUCCESS: PartsTrack deployed!"
echo "Database backup: $BACKUP_FILE"
echo "Previous commit: $PREVIOUS_COMMIT"
git log -1 --format="Commit: %h - %s"
'@

# Execute the deployment over SSH
$RemoteScript = $RemoteScript -replace "`r`n", "`n"

$RemoteScript | ssh $Server "bash -se"

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "DEPLOYMENT FAILED." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Deployment completed successfully." -ForegroundColor Green