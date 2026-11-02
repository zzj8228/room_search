#!/bin/bash
set -euo pipefail
source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
if ! id roomsearch >/dev/null 2>&1; then
    useradd --system --home-dir /var/lib/room-search --create-home --shell /usr/sbin/nologin roomsearch
fi
install -d -m 700 -o roomsearch -g roomsearch /var/lib/room-search
install -d -m 755 /opt/room-search
if [ "$source_dir" != /opt/room-search ]; then
    tar -C "$source_dir" -cf - classroom.py requirements.txt requirements-lock.txt room_search deploy |
        tar --no-same-owner -xf - -C /opt/room-search
fi
python3 -m venv /opt/room-search/.venv
/opt/room-search/.venv/bin/pip install --disable-pip-version-check -r /opt/room-search/requirements.txt
/opt/room-search/.venv/bin/pip check
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
install -d -m 755 /opt/room-search/.tools/bin
if [ ! -x /opt/room-search/.tools/bin/agent-browser ]; then
    curl --fail --show-error --silent --location https://registry.npmjs.org/agent-browser/-/agent-browser-0.39.1.tgz |
        tar -xz -C /opt/room-search/.tools --strip-components=1 package/bin/agent-browser-linux-x64 package/skill-data
    install -m 755 /opt/room-search/.tools/bin/agent-browser-linux-x64 /opt/room-search/.tools/bin/agent-browser
fi
sudo -u roomsearch env HOME=/var/lib/room-search AGENT_BROWSER_SKILLS_DIR=/opt/room-search/.tools/skill-data /opt/room-search/.tools/bin/agent-browser skills get core > /var/lib/room-search/browser-workflow.txt
sudo -u roomsearch env HOME=/var/lib/room-search /opt/room-search/.tools/bin/agent-browser install
browser_dir=$(find /var/lib/room-search/.agent-browser/browsers -mindepth 1 -maxdepth 1 -type d -name 'chrome-*' | sort -V | tail -n 1)
test -x "$browser_dir/chrome"
install -d -m 755 /opt/room-search/browser
cp -a "$browser_dir/." /opt/room-search/browser/
chown -R root:root /opt/room-search/browser
install -m 644 /opt/room-search/deploy/room-search-chrome.apparmor /etc/apparmor.d/room-search-chrome
apparmor_parser -r /etc/apparmor.d/room-search-chrome
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
install -m 644 /opt/room-search/deploy/nginx.conf /www/server/panel/vhost/nginx/room-search.conf
nginx -t
systemctl daemon-reload
systemctl enable room-search.service room-search-desktop.service room-search-admin.service
systemctl restart room-search.service room-search-desktop.service room-search-admin.service
nginx -s reload
systemctl is-active room-search.service room-search-desktop.service room-search-admin.service
sudo -u postgres psql -d pku_classroom -c 'SELECT count(*) AS lessons, count(DISTINCT room) AS rooms FROM pku_room_search.lessons;'
