#!/usr/bin/env bash
set -Eeo pipefail
# db-init.sql is an administrator-provided secret containing CREATE USER ...
# statements for nondegree_app/nondegree_migration with strong passwords.
# It must never be committed into the source package.
secret=/run/secrets/db_init_sql
[[ -f "$secret" && ! -L "$secret" && -s "$secret" ]] || { echo 'database user secret missing' >&2; exit 2; }
mysql --defaults-extra-file=/run/secrets/root_cnf --protocol=socket "$MYSQL_DATABASE" < "$secret"
