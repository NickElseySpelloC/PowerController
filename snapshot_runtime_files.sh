#!/bin/bash

# Change directory to the location of the script
cd "$(dirname "$0")"

# List of filenames to snapshot
FILES_TO_SNAPSHOT=("logfile.log" "system_state.json" "latest_prices.json")

# Maximum age of snapshots in hours
MAX_HOURS=72

# Create the snapshots directory if it doesn't exist
SNAPSHOT_DIR="snapshots"
mkdir -p "$SNAPSHOT_DIR"

# Get the current date in YYYYMMDD format
CURRENT_DATETIME=$(date +"%Y%m%d_%H%M%S")

# Copy files to the snapshots directory with the date prepended
for FILE in "${FILES_TO_SNAPSHOT[@]}"; do
    if [[ -f "$FILE" ]]; then
        cp "$FILE" "$SNAPSHOT_DIR/${CURRENT_DATETIME}_$FILE"
        echo "Snapshot created for $FILE"
    else
        echo "File $FILE does not exist, skipping..."
    fi
done

# Find and delete snapshots older than MAX_HOURS
find "$SNAPSHOT_DIR" -type f -mmin +$((MAX_HOURS * 60)) -exec rm {} \;
echo "Old snapshots older than $MAX_HOURS hours have been deleted."