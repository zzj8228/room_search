#!/bin/bash
set -euo pipefail
source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
action=${1:-install}
if [ "$#" -gt 1 ]; then
    echo 'Usage: sudo bash deploy/install.sh [install|update|register|restart]' >&2
    exit 1
fi
case "$action" in
    install|update|register|restart) ;;
    *) echo 'Usage: sudo bash deploy/install.sh [install|update|register|restart]' >&2; exit 1 ;;
esac
if [ "$(id -u)" -ne 0 ] || [ "$source_dir" != /opt/room-search ]; then
    echo 'Run with sudo from the repository cloned into /opt/room-search on Ubuntu.' >&2
    exit 1
fi
if [ ! -f /etc/os-release ]; then
    echo 'Ubuntu 24.04 x64 is required.' >&2
    exit 1
fi
. /etc/os-release
if [ "${ID:-}" != ubuntu ] || [ "${VERSION_ID:-}" != 24.04 ] || [ "$(dpkg --print-architecture)" != amd64 ]; then
    echo 'Ubuntu 24.04 x64 is required.' >&2
    exit 1
fi
panel_python=/www/server/panel/pyenv/bin/python3
if [ ! -x "$panel_python" ] || [ ! -f /www/server/panel/BT-Panel ] || [ ! -d /www/server/panel/vhost/nginx ]; then
    echo 'Install BT Panel with Nginx on the Ubuntu server first.' >&2
    exit 1
fi
cd "$source_dir"

install_dependencies() {
    /opt/room-search/.venv/bin/pip install --disable-pip-version-check -r /opt/room-search/requirements.txt
}
restart_project() {
    # Registration also migrates older BT desktop sidecars and Nginx routes.
    install -m 644 /opt/room-search/deploy/room-search*.service /opt/room-search/deploy/room-search*.timer /etc/systemd/system/
    systemctl daemon-reload
    sudo -u roomsearch env PKU_CLASSROOM_DATABASE_URL='host=/var/run/postgresql dbname=pku_classroom user=roomsearch' \
        PKU_CLASSROOM_DATA_DIR=/var/lib/room-search \
        /opt/room-search/.venv/bin/python /opt/room-search/classroom.py repair-departments
    "$panel_python" /opt/room-search/deploy/bt_register.py
}
case "$action" in
    update)
        if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
            echo 'Server code has local changes; inspect them before updating.' >&2
            exit 1
        fi
        git pull --ff-only origin main
        exec bash "$source_dir/deploy/install.sh" restart
        ;;
    register)
        exec "$panel_python" /opt/room-search/deploy/bt_register.py
        ;;
    restart)
        install_dependencies
        restart_project
        exit 0
        ;;
esac

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl
install -d /usr/share/postgresql-common/pgdg
curl --fail --show-error --silent https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
printf '%s\n' 'deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt noble-pgdg main' > /etc/apt/sources.list.d/pgdg.list
apt-get update
apt-get install -y postgresql-18 postgresql-client-18 python3-venv openssl
systemctl enable --now postgresql
postgres_version=$(sudo -u postgres psql -Atc 'SHOW server_version;')
case "$postgres_version" in
    18.*) ;;
    *) echo 'The default PostgreSQL socket must use version 18. Resolve existing clusters before installing.' >&2; exit 1 ;;
esac
if ! id roomsearch >/dev/null 2>&1; then
    useradd --system --home-dir /var/lib/room-search --create-home --shell /usr/sbin/nologin roomsearch
fi
install -d -m 700 -o roomsearch -g roomsearch /var/lib/room-search
python3 -m venv /opt/room-search/.venv
install_dependencies
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='roomsearch'" | grep -qx 1; then
    sudo -u postgres createuser roomsearch
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='pku_classroom'" | grep -qx 1; then
    sudo -u postgres createdb --owner=roomsearch --encoding=UTF8 --template=template0 pku_classroom
fi
if [ -n "${ROOM_SEARCH_CATALOG_DUMP:-}" ]; then
    if sudo -u roomsearch psql -d pku_classroom -tAc "SELECT to_regclass('pku_room_search.lessons') IS NOT NULL" | grep -qx t; then
        echo 'Refusing to restore over an initialized catalog database.' >&2
        exit 1
    fi
    install -m 600 -o roomsearch -g roomsearch "$ROOM_SEARCH_CATALOG_DUMP" /var/lib/room-search/initial.dump
    sudo -u roomsearch pg_restore --exit-on-error --no-owner --no-acl --dbname=pku_classroom /var/lib/room-search/initial.dump
fi
sudo -u postgres psql -c "ALTER DATABASE pku_classroom SET timezone TO 'Asia/Shanghai';"
install -d -m 750 -o root -g www /etc/room-search
if [ ! -f /etc/room-search/tls.key ]; then
    openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 365 \
        -keyout /etc/room-search/tls.key -out /etc/room-search/tls.crt \
        -subj '/CN=10.129.81.32' -addext 'subjectAltName=IP:10.129.81.32'
    chmod 600 /etc/room-search/tls.key
fi
python3 - <<'PY'
import os
import grp
import secrets
import subprocess
from pathlib import Path
os.umask(0o077)
directory = Path('/etc/room-search')
if not (directory / 'admin.htpasswd').exists():
    password = secrets.token_urlsafe(24)
    hashed = subprocess.run(['openssl', 'passwd', '-6', '-stdin'], input=password + '\n', text=True, capture_output=True, check=True).stdout.strip()
    target = directory / 'admin.htpasswd'
    target.write_text('classroom_admin:' + hashed + '\n')
    os.chown(target, 0, grp.getgrnam('www').gr_gid)
    target.chmod(0o640)
    (directory / 'admin-credentials.txt').write_text('Management: https://10.129.81.32/admin/\nUsername: classroom_admin\nPassword: ' + password + '\n')
PY
install -m 644 /opt/room-search/deploy/room-search*.service /opt/room-search/deploy/room-search*.timer /etc/systemd/system/
if [ ! -f /www/server/panel/vhost/nginx/room-search.conf ] && [ ! -f /www/server/panel/vhost/nginx/python_room-search.conf ]; then
    install -m 644 /opt/room-search/deploy/nginx.conf /www/server/panel/vhost/nginx/room-search.conf
fi
systemctl daemon-reload
"$panel_python" /opt/room-search/deploy/bt_register.py
sudo -u postgres psql -d pku_classroom -c 'SELECT count(*) AS lessons, count(DISTINCT room) AS rooms FROM pku_room_search.lessons;'
