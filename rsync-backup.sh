#!/bin/bash

if [ $# -ne 2 ]; then
    echo "Usage: $0 <source_dir> <destination_dir>"
    exit 1
fi

SRC="$1"
DEST="$2"

LOG_DIR="/var/log/rsync_backup"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Create safe filenames from paths
SRC_NAME=$(echo "$SRC" | sed 's#^/##; s#/#_#g; s#[^a-zA-Z0-9_-]#_#g')
DEST_NAME=$(echo "$DEST" | sed 's#^/##; s#/#_#g; s#[^a-zA-Z0-9_-]#_#g')

DATE=$(date +"%Y-%m-%d")

LOG="${LOG_DIR}/${SRC_NAME}-to-${DEST_NAME}-${DATE}.log"

echo "===== Backup started: $(date) =====" >> "$LOG"
echo "Source: $SRC" >> "$LOG"
echo "Destination: $DEST" >> "$LOG"

rsync -av --delete "$SRC/" "$DEST/" >> "$LOG" 2>&1

STATUS=$?

if [ $STATUS -eq 0 ]; then
    echo "Backup completed successfully: $(date)" >> "$LOG"
else
    echo "Backup FAILED with exit code $STATUS: $(date)" >> "$LOG"
fi

echo "====================================" >> "$LOG"

exit $STATUS
