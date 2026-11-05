#!/usr/bin/env bash
# Download pinned Volve data, OSDU schemas and reference values into data/raw/.
# Safe to re-run: existing, correctly pinned folders are skipped.
# Usage: bash scripts/download_data.sh   (works from any directory)
set -euo pipefail

cd "$(dirname "$0")/.."   # run from the repository root, whatever the caller's directory
RAW="data/raw"
mkdir -p "$RAW"

# clone_pinned <url> <folder-name> <commit-hash>
clone_pinned() {
  local url="$1" name="$2" sha="$3"
  local dest="$RAW/$name"
  if [ -d "$dest/.git" ]; then
    echo "skip $name (already downloaded)"
  else
    git clone --quiet "$url" "$dest"
    git -C "$dest" checkout --quiet "$sha"
  fi
  local actual
  actual=$(git -C "$dest" rev-parse HEAD)
  if [ "$actual" != "$sha" ]; then
    echo "ERROR: $name is at $actual, expected $sha" >&2
    exit 1
  fi
  echo "ok   $name @ ${sha:0:7}"
}

# Pinned commits: see docs/PROJECT_GUIDE.md section 4.1 and docs/architecture.md.
clone_pinned https://github.com/andymcdgeo/spwla_volve.git    spwla_volve       c293edf37c1b567b8dc9c81ea88f2cf288eab423
clone_pinned https://github.com/awgeo/Volve_field_data.git    volve_field_data  7cdecf1f1d24811d21bb2e2f379ff048404f4ce7
clone_pinned https://github.com/equinor/osdu-mcp-poc.git      osdu-mcp-poc      b2a648d68b12c60848098636dcbce621cf4e9277

# --- OSDU reference values, data-definitions v0.30.1 ---
DD_SHA="ff89d87caa43d05d1341dcaa6d258e1186ec8aa6"
DD_URL="https://community.opengroup.org/osdu/data/data-definitions/-/raw/$DD_SHA/ReferenceValues/Manifests/reference-data"
REF_FILES=(
  OPEN/UnitOfMeasure.1.json
  OPEN/VerticalMeasurementType.1.json
  OPEN/VerticalMeasurementPath.1.json
  LOCAL/LogCurveType.1.json
  LOCAL/LogCurveFamily.1.json
  LOCAL/CoordinateReferenceSystem.1.json
)
mkdir -p "$RAW/reference"
for f in "${REF_FILES[@]}"; do
  out="$RAW/reference/$(basename "$f")"
  if [ -f "$out" ]; then
    echo "skip reference/$(basename "$f")"
  else
    echo "get  reference/$(basename "$f")"
    curl -sSfL "$DD_URL/$f" -o "$out.part"
    mv "$out.part" "$out"
  fi
done

echo "done."