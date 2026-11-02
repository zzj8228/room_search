#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
install -d /usr/share/postgresql-common/pgdg
curl --fail --show-error --silent https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
printf '%s\n' 'deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt noble-pgdg main' > /etc/apt/sources.list.d/pgdg.list
apt-get update
apt-get install -y postgresql-18 postgresql-client-18 python3-venv
systemctl enable --now postgresql
psql --version
sudo -u postgres psql -Atc 'SHOW server_version;'
