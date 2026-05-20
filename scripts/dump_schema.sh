#!/usr/bin/env bash
# Dump current Supabase Postgres schema to a single file for disaster recovery.
#
# Why: schema_phase*.sql files are incremental migrations. After running 15+
# of them, reconstructing the live schema mentally is hard. A flat snapshot
# captures the final state in one place.
#
# Usage:
#   1. Get your Supabase Postgres connection string from Supabase Dashboard
#      → Project Settings → Database → Connection string → URI
#      It looks like: postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT-ID].supabase.co:5432/postgres
#
#   2. Run:
#        SUPABASE_DB_URL="postgresql://..." ./scripts/dump_schema.sh
#
#   3. Commit the resulting backend/schema_snapshot.sql to git.
#
# This is meant to be run occasionally (after major schema changes), not on
# every deploy. The schema_phase*.sql migration files are still the source
# of truth for replaying changes; this snapshot is a safety net.

set -euo pipefail

if [[ -z "${SUPABASE_DB_URL:-}" ]]; then
    echo "ERROR: SUPABASE_DB_URL not set."
    echo "Find it in Supabase Dashboard → Project Settings → Database → Connection string."
    exit 1
fi

OUTPUT_PATH="${OUTPUT_PATH:-backend/schema_snapshot.sql}"

echo "Dumping schema to $OUTPUT_PATH ..."

# --schema-only: structure only, no data (no privacy risk if committed to repo)
# --no-owner: avoid GRANT statements for the supabase_admin role
# --no-privileges: drop ACL/permission lines (Supabase manages these)
# --schema=public: skip auth/storage internal schemas
pg_dump \
    --schema-only \
    --no-owner \
    --no-privileges \
    --schema=public \
    "$SUPABASE_DB_URL" \
    > "$OUTPUT_PATH"

# Add a header so future-you knows what this is.
TMP=$(mktemp)
{
    echo "-- ============================================================================"
    echo "-- Supabase schema snapshot"
    echo "--"
    echo "-- Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    echo "-- Source:    \$SUPABASE_DB_URL (public schema only)"
    echo "--"
    echo "-- This is a flat snapshot of the live schema, intended for disaster recovery"
    echo "-- and reference. The schema_phase*.sql files are the source of truth for"
    echo "-- incremental migrations; replay them in order if rebuilding from scratch."
    echo "--"
    echo "-- Regenerate with: SUPABASE_DB_URL=... ./scripts/dump_schema.sh"
    echo "-- ============================================================================"
    echo
    cat "$OUTPUT_PATH"
} > "$TMP"
mv "$TMP" "$OUTPUT_PATH"

LINES=$(wc -l < "$OUTPUT_PATH")
echo "Done. $OUTPUT_PATH ($LINES lines)"
echo
echo "Next: git add $OUTPUT_PATH && git commit -m 'Refresh schema snapshot'"
