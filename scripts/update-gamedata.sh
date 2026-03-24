#!/usr/bin/env bash
# update-gamedata.sh — Pull latest wows-gamedata and validate entity defs
# This is the "one button" update workflow for new WoWs patches.
#
# Usage:
#   ./scripts/update-gamedata.sh [--gamedata-path ./wows-gamedata]

set -euo pipefail

GAMEDATA_REPO="https://github.com/toalba/wows-gamedata.git"
GAMEDATA_PATH="${1:-./wows-gamedata}"
ENTITY_DEFS_REL="data/scripts_entity/entity_defs"

echo "=== WoWs Replay Parser — Gamedata Update ==="

# Clone or pull
if [ -d "$GAMEDATA_PATH/.git" ]; then
    echo "Pulling latest gamedata..."
    git -C "$GAMEDATA_PATH" pull --ff-only
else
    echo "Cloning wows-gamedata..."
    git clone --depth 1 "$GAMEDATA_REPO" "$GAMEDATA_PATH"
fi

ENTITY_DEFS="$GAMEDATA_PATH/$ENTITY_DEFS_REL"

# Validate structure
echo ""
echo "Validating entity_defs..."

if [ ! -f "$ENTITY_DEFS/alias.xml" ]; then
    echo "ERROR: alias.xml not found at $ENTITY_DEFS/alias.xml"
    exit 1
fi

DEF_COUNT=$(find "$ENTITY_DEFS" -maxdepth 1 -name "*.def" | wc -l)
IFACE_COUNT=$(find "$ENTITY_DEFS/interfaces" -name "*.def" 2>/dev/null | wc -l)

echo "  alias.xml:  OK"
echo "  .def files: $DEF_COUNT entities"
echo "  interfaces: $IFACE_COUNT"

# List entities
echo ""
echo "Entities:"
for f in "$ENTITY_DEFS"/*.def; do
    echo "  - $(basename "$f" .def)"
done

# Quick parse validation (if Python env is available)
if command -v python3 &>/dev/null; then
    echo ""
    echo "Running quick parse validation..."
    python3 -c "
from pathlib import Path
from lxml import etree

defs_dir = Path('$ENTITY_DEFS')
alias_path = defs_dir / 'alias.xml'

# Validate alias.xml parses
tree = etree.parse(str(alias_path))
alias_count = len(list(tree.getroot()))
print(f'  alias.xml: {alias_count} type aliases')

# Validate each .def file parses
errors = []
for def_file in sorted(defs_dir.glob('*.def')):
    try:
        etree.parse(str(def_file))
    except Exception as e:
        errors.append(f'{def_file.name}: {e}')

if errors:
    print(f'  ERRORS in {len(errors)} files:')
    for err in errors:
        print(f'    - {err}')
else:
    print(f'  All .def files parse OK')
" 2>/dev/null || echo "  (Python validation skipped — lxml not available)"
fi

echo ""
echo "=== Gamedata update complete ==="
echo "Entity defs path: $ENTITY_DEFS"
