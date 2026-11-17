
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


echo "Backing up production database..."

# Record the current time before starting the backup
BACKUP_START=$(date +%s)

# Run the backup service
sudo -n systemctl start partstrack-backup.service

# Verify the backup service completed successfully
BACKUP_RESULT=$(systemctl show partstrack-backup.service \
    --property=Result --value)

if [ "$BACKUP_RESULT" != "success" ]; then
    echo "ERROR: Database backup service failed."
    exit 1
fi

# Verify a fresh, nonempty backup file was created
BACKUP_FOUND=false

for backup in /home/mcmillanparts2518/PartsTrack/backups/partstrack-*.db; do
    [ -f "$backup" ] || continue
    [ -s "$backup" ] || continue

    BACKUP_TIME=$(stat -c %Y "$backup")

    if [ "$BACKUP_TIME" -ge "$BACKUP_START" ]; then
        BACKUP_FOUND=true
        echo "Backup verified: $backup"
        break
    fi
done

if [ "$BACKUP_FOUND" != "true" ]; then
    echo "ERROR: No fresh database backup was found."
    exit 1
fi

echo "Fetching latest main branch..."
git fetch origin main


echo "Updating production code..."
git merge --ff-only origin/main

echo "Installing Python dependencies..."
/home/mcmillanparts2518/PartsTrack/.venv/bin/python \
    -m pip install -r requirements.txt

echo "Restarting PartsTrack..."
sudo -n systemctl restart partstrack.service

echo "Checking application service..."
if ! systemctl is-active --quiet partstrack.service; then
    echo "ERROR: PartsTrack service is not running."
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
    exit 1
fi

echo "PartsTrack website is responding successfully."

echo ""
echo "SUCCESS: PartsTrack deployed!"
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
