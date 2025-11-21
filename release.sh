#!/bin/bash

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <version> <comment>"
    exit 1
fi

VERSION=$1
COMMENT=$2

PYPROJECT="pyproject.toml"

# Make sure our virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Error: No virtual environment activated."
    exit 1
fi

# Get the current version from pyproject.toml
if [ -f "$PYPROJECT" ]; then
    CURRENT_VERSION=$(grep -E '^version *= *"' "$PYPROJECT" | head -1 | sed -E 's/^version *= *"([^"]+)".*$/\1/')
else
    echo "Error: $PYPROJECT not found."
    exit 1
fi

echo "Current version: $CURRENT_VERSION"
echo "New version:     $VERSION"
echo "Comment:         $COMMENT"
echo
read -p "Enter Y to continue, any other key to abort: " CONFIRM

if [[ "$CONFIRM" != "Y" && "$CONFIRM" != "y" ]]; then
    echo "Aborted."
    exit 0
fi

# Update the version in pyproject.toml
sed -i '' -E "s/(^version *= *\").*(\")/\1$VERSION\2/" "$PYPROJECT"

# Stage all changes
git add .
if [ $? -ne 0 ]; then
    echo "Error: git add failed."
    exit 1
fi

# Commit with the provided comment
git commit -m "$COMMENT"
if [ $? -ne 0 ]; then
    echo "Error: git commit failed."
    exit 1
fi

# Tag the new release
git tag "v$VERSION"
if [ $? -ne 0 ]; then
    echo "Error: git tag failed."
    exit 1
fi

# Push to origin
git push origin main
if [ $? -ne 0 ]; then
    echo "Error: git push main failed."
    exit 1
fi

git push origin "v$VERSION"
if [ $? -ne 0 ]; then
    echo "Error: git push origin v$VERSION failed."
    exit 1
fi

echo "Release v$VERSION committed and pushed with comment: $COMMENT"