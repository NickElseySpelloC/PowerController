#!/bin/bash

# Change directory to the location of the script
cd "$(dirname "$0")"

# List of filenames to snapshot
FILES_TO_SNAPSHOT=("logs/*" "system_state.json" "config.yaml")

# Maximum age of snapshots in hours where we keep all snapshots
MAX_HOURS=72

# Maximum age of snapshots in days where we keep the last snapshot of the day
MAX_DAYS=30

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

# Cleanup strategy:
# 1. Keep all snapshots from the past MAX_HOURS hours
# 2. For days beyond MAX_HOURS, keep only the last snapshot of each day up to MAX_DAYS
# 3. Delete everything older than MAX_DAYS

# Get current time in seconds since epoch
CURRENT_TIME=$(date +%s)
MAX_HOURS_SECONDS=$((MAX_HOURS * 3600))
MAX_DAYS_SECONDS=$((MAX_DAYS * 86400))

# Process snapshot directories
declare -A daily_snapshots  # Associative array to track last snapshot per day

# Iterate through all snapshot directories (format: YYYYMMDD_HHMMSS)
for SNAPSHOT in "$SNAPSHOT_DIR"/*/; do
    [[ -d "$SNAPSHOT" ]] || continue
    
    SNAPSHOT_NAME=$(basename "$SNAPSHOT")
    
    # Parse the timestamp from directory name (YYYYMMDD_HHMMSS)
    if [[ $SNAPSHOT_NAME =~ ^([0-9]{8})_([0-9]{6})$ ]]; then
        DATE_PART="${BASH_REMATCH[1]}"
        TIME_PART="${BASH_REMATCH[2]}"
        
        # Convert to Unix timestamp
        YEAR="${DATE_PART:0:4}"
        MONTH="${DATE_PART:4:2}"
        DAY="${DATE_PART:6:2}"
        HOUR="${TIME_PART:0:2}"
        MINUTE="${TIME_PART:2:2}"
        SECOND="${TIME_PART:4:2}"
        
        SNAPSHOT_TIME=$(date -j -f "%Y-%m-%d %H:%M:%S" "$YEAR-$MONTH-$DAY $HOUR:$MINUTE:$SECOND" +%s 2>/dev/null)
        
        if [[ -z "$SNAPSHOT_TIME" ]]; then
            echo "Warning: Could not parse timestamp for $SNAPSHOT_NAME, skipping"
            continue
        fi
        
        AGE_SECONDS=$((CURRENT_TIME - SNAPSHOT_TIME))
        
        # Delete if older than MAX_DAYS
        if [[ $AGE_SECONDS -gt $MAX_DAYS_SECONDS ]]; then
            echo "Deleting snapshot older than $MAX_DAYS days: $SNAPSHOT_NAME"
            rm -rf "$SNAPSHOT"
            continue
        fi
        
        # Keep all snapshots within MAX_HOURS
        if [[ $AGE_SECONDS -le $MAX_HOURS_SECONDS ]]; then
            continue
        fi
        
        # For snapshots between MAX_HOURS and MAX_DAYS, track the last one per day
        DAY_KEY="${DATE_PART}"
        if [[ -z "${daily_snapshots[$DAY_KEY]}" ]] || [[ "$SNAPSHOT_NAME" > "${daily_snapshots[$DAY_KEY]}" ]]; then
            daily_snapshots[$DAY_KEY]="$SNAPSHOT_NAME"
        fi
    fi
done

# Delete snapshots that are not the last snapshot of their day (for days beyond MAX_HOURS)
for SNAPSHOT in "$SNAPSHOT_DIR"/*/; do
    [[ -d "$SNAPSHOT" ]] || continue
    
    SNAPSHOT_NAME=$(basename "$SNAPSHOT")
    
    if [[ $SNAPSHOT_NAME =~ ^([0-9]{8})_([0-9]{6})$ ]]; then
        DATE_PART="${BASH_REMATCH[1]}"
        
        # Convert to Unix timestamp to check age
        YEAR="${DATE_PART:0:4}"
        MONTH="${DATE_PART:4:2}"
        DAY="${DATE_PART:6:2}"
        TIME_PART="${SNAPSHOT_NAME:9}"
        HOUR="${TIME_PART:0:2}"
        MINUTE="${TIME_PART:2:2}"
        SECOND="${TIME_PART:4:2}"
        
        SNAPSHOT_TIME=$(date -j -f "%Y-%m-%d %H:%M:%S" "$YEAR-$MONTH-$DAY $HOUR:$MINUTE:$SECOND" +%s 2>/dev/null)
        
        if [[ -n "$SNAPSHOT_TIME" ]]; then
            AGE_SECONDS=$((CURRENT_TIME - SNAPSHOT_TIME))
            
            # If this snapshot is beyond MAX_HOURS but within MAX_DAYS
            if [[ $AGE_SECONDS -gt $MAX_HOURS_SECONDS ]] && [[ $AGE_SECONDS -le $MAX_DAYS_SECONDS ]]; then
                # Delete if it's not the last snapshot of its day
                if [[ "${daily_snapshots[$DATE_PART]}" != "$SNAPSHOT_NAME" ]]; then
                    echo "Deleting non-last snapshot of the day: $SNAPSHOT_NAME"
                    rm -rf "$SNAPSHOT"
                fi
            fi
        fi
    fi
done

# Clean up any empty directories
find "$SNAPSHOT_DIR" -type d -empty -delete

echo "Snapshot cleanup complete:"
echo "  - Kept all snapshots from the past $MAX_HOURS hours"
echo "  - Kept last snapshot of each day for the past $MAX_DAYS days"
echo "  - Deleted snapshots older than $MAX_DAYS days"