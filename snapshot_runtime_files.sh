#!/bin/bash

# Change directory to the location of the script
cd "$(dirname "$0")"

# List of filenames to snapshot
FILES_TO_SNAPSHOT=("logs/*" "system_state.json" "config.yaml")

# Maximum age of snapshots in hours
MAX_HOURS=72

# Create the snapshots directory if it doesn't exist
SNAPSHOT_DIR="snapshots"
mkdir -p "$SNAPSHOT_DIR"

# Get the current date in YYYYMMDD_HHMMSS format
CURRENT_DATETIME=$(date +"%Y%m%d_%H%M%S")

# NEW: keep each snapshot in its own timestamped folder, preserve relative paths
SNAPSHOT_STAMP_DIR="$SNAPSHOT_DIR/$CURRENT_DATETIME"
mkdir -p "$SNAPSHOT_STAMP_DIR"

# Copy files to the snapshots directory, creating parent dirs for relative paths
for PATTERN in "${FILES_TO_SNAPSHOT[@]}"; do
    # Expand the pattern (handle wildcards)
    shopt -s nullglob
    for FILE in $PATTERN; do
        if [[ -f "$FILE" ]]; then
            # Strip leading slash (safety) so absolute paths don't escape SNAPSHOT_DIR
            REL_PATH="${FILE#/}"
            DEST="$SNAPSHOT_STAMP_DIR/$REL_PATH"
            mkdir -p "$(dirname "$DEST")"
            cp -a "$FILE" "$DEST"
            echo "Snapshot created for $FILE -> $DEST"
        fi
    done
    shopt -u nullglob
done

# Find and delete snapshots older than MAX_HOURS (by file mtime), then prune empty dirs
find "$SNAPSHOT_DIR" -type f -mmin +$((MAX_HOURS * 60)) -delete
find "$SNAPSHOT_DIR" -type d -empty -delete

echo "Old snapshots older than $MAX_HOURS hours have been deleted."