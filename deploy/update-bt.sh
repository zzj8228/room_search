#!/bin/bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
    echo 'Run this script with sudo on the Ubuntu server.' >&2
    exit 1
fi
code_dir=/opt/room-search
cd "$code_dir"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo 'Server code has local changes; inspect them before updating.' >&2
    exit 1
fi
git pull --ff-only origin main
sudo -u roomsearch env PKU_CLASSROOM_DATABASE_URL='host=/var/run/postgresql dbname=pku_classroom user=roomsearch' \
    "$code_dir/.venv/bin/python" "$code_dir/classroom.py" repair-departments
/www/server/panel/pyenv/bin/python3 "$code_dir/deploy/bt_manage.py" restart
curl --fail --silent --show-error http://127.0.0.1:8766/api/meta
