#!/bin/zsh
# Per-table row count and digest of every row's text, for every table of the copy. Read-only.
DB="$1"
docker exec repair-pg psql -U postgres -d "$DB" -At -F '|' -c "SELECT table_schema||'.'||table_name FROM information_schema.tables WHERE table_schema IN ('users','predictions','ml_models','analytics','audit') AND table_type='BASE TABLE' ORDER BY 1" | while read -r t; do
  docker exec repair-pg psql -U postgres -d "$DB" -At -F '|' -c "SELECT '$t', count(*), coalesce(md5(string_agg(x::text, '|' ORDER BY x::text)), '') FROM $t x"
done
