"""Reuse an existing Ubuntu deployment as a native BT Python project and PG connection.

Run with /www/server/panel/pyenv/bin/python3 as root on the server only.
No personal keys, passwords or cookies belong in this source file.
"""
import argparse
import grp
import json
import os
from pathlib import Path
import pwd
import secrets
import shlex
import subprocess
import sys
import time
import urllib.request

from bt_manage import PROJECT, panel_context, project_status

CODE = Path("/opt/room-search")
RUNTIME = Path("/var/lib/room-search")
PROJECT_PATH = Path("/www/wwwroot/room-search")
PRIVATE = Path("/etc/room-search")
PYTHON = str(CODE / ".venv/bin/python")
DATABASE = "host=/var/run/postgresql dbname=pku_classroom user=roomsearch"


def checked(result, operation):
    if not isinstance(result, dict) or not result.get("status"):
        raise RuntimeError(operation + "失败；请检查服务器宝塔配置。")


def runtime_environment():
    values = {"HOME": str(RUNTIME), "DISPLAY": ":99", "PYTHONUNBUFFERED": "1",
              "PKU_CLASSROOM_DATABASE_URL": DATABASE, "PKU_CLASSROOM_DATA_DIR": str(RUNTIME),
              "PKU_CLASSROOM_REMOTE_LOGIN": "1",
              "PKU_CLASSROOM_BROWSER_EXECUTABLE": str(CODE / "browser/chrome"),
              "PATH": str(CODE / ".tools/bin") + ":/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"}
    target = PRIVATE / "bt-runtime.env"
    target.write_text("umask 077\n" + "".join("export " + key + "=" + shlex.quote(value) + "\n"
                                              for key, value in values.items()))
    os.chown(target, 0, grp.getgrnam("roomsearch").gr_gid)
    target.chmod(0o640)
    return target


def register_database(public):
    """BT uses a loopback, read-only login; the app keeps its existing peer authentication."""
    from databaseModel.pgsqlModel import main as PostgreSQL
    row = public.M("database_servers").where("db_host=? AND db_port=?", ("127.0.0.1", 5432)).find()
    if row and (row["db_type"].lower() != "pgsql" or row["db_user"] != "pku_classroom"):
        raise RuntimeError("宝塔已登记其他本机数据库连接，请先人工核对，未覆盖。")
    password = row["db_password"] if row else secrets.token_urlsafe(32)
    # Password travels through stdin only; never command arguments, source files or logs.
    configure = '''import json,sys,psycopg
from psycopg import sql
value=json.load(sys.stdin)
with psycopg.connect('dbname=pku_classroom') as conn:
    exists=conn.execute("SELECT 1 FROM pg_roles WHERE rolname='pku_classroom'").fetchone()
    if exists and not value['reuse']:
        raise RuntimeError('Existing role is not owned by this panel registration')
    if not exists:
        conn.execute("CREATE ROLE pku_classroom LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION")
    conn.execute(sql.SQL('ALTER ROLE pku_classroom PASSWORD {}').format(sql.Literal(value['password'])))
    conn.execute("GRANT CONNECT ON DATABASE pku_classroom TO pku_classroom")
    conn.execute("GRANT USAGE ON SCHEMA pku_room_search TO pku_classroom")
    conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA pku_room_search TO pku_classroom")
    conn.execute("ALTER DEFAULT PRIVILEGES FOR ROLE roomsearch IN SCHEMA pku_room_search GRANT SELECT ON TABLES TO pku_classroom")
    conn.execute("ALTER ROLE pku_classroom SET default_transaction_read_only=on")
'''
    subprocess.run(["sudo", "-u", "postgres", PYTHON, "-c", configure],
                   input=json.dumps({"password": password, "reuse": bool(row)}), text=True, check=True)
    model = PostgreSQL()
    if not row:
        get = public.dict_obj()
        get.db_host, get.db_port, get.db_user = "127.0.0.1", "5432", "pku_classroom"
        get.db_password = password
        get.db_ps, get.type = "本机 PostgreSQL 18 · 教室查课（只读）", "pgsql"
        checked(model.AddCloudServer(get), "登记 PostgreSQL 连接")
        row = public.M("database_servers").where("db_host=? AND db_port=?", ("127.0.0.1", 5432)).find()
    get = public.dict_obj()
    get.sid = int(row["id"])
    checked(model.SyncGetDatabases(get), "登记已有数据库")
    record = public.M("databases").where("name=? AND sid=?", ("pku_classroom", row["id"])).find()
    if not record:
        raise RuntimeError("宝塔未返回已有课表数据库。")
    public.M("databases").where("id=?", (record["id"],)).update({"ps": "教室查课 · 原有 PostgreSQL 18"})
    connection = model.get_sql_obj_by_sid(int(row["id"]))
    counts = connection.query("SELECT count(*) FROM pku_room_search.lessons")
    if not isinstance(counts, list) or not counts or not isinstance(counts[0][0], int):
        raise RuntimeError("宝塔 PostgreSQL 只读连接校验失败。")
    return {"server_id": row["id"], "database": "pku_classroom", "lessons": counts[0][0], "read_only": True}


def register():
    import public
    from projectModel.pythonModel import main as PythonProjects
    from mod.project.python.pyenv_tool import EnvironmentManager
    from mod.project.python.serviceMod import ServiceManager
    for path in (CODE / "classroom.py", Path(PYTHON), PRIVATE / "admin.htpasswd", PRIVATE / "tls.crt",
                 PRIVATE / "tls.key", CODE / "browser/chrome"):
        if not path.is_file():
            raise RuntimeError("缺少现有部署文件：" + str(path))
    account = pwd.getpwnam("roomsearch")
    PROJECT_PATH.mkdir(parents=True, exist_ok=True)
    if any(PROJECT_PATH.iterdir()):
        # This directory is only a BT working directory, never a public copy of the application.
        raise RuntimeError("宝塔工作目录非空，未覆盖，请核对 /www/wwwroot/room-search。")
    os.chown(PROJECT_PATH, account.pw_uid, account.pw_gid)
    PROJECT_PATH.chmod(0o750)
    environment = runtime_environment()
    subprocess.run(["sudo", "-u", "roomsearch", "env", "PKU_CLASSROOM_DATABASE_URL=" + DATABASE,
                    PYTHON, str(CODE / "classroom.py"), "repair-departments"], check=True)
    manager = EnvironmentManager()
    if not manager.get_env_py_path(PYTHON):
        error = manager.add_python_env("venv", str(CODE / ".venv"))
        if error:
            raise RuntimeError("登记已有 Python 虚拟环境失败。")
    database = register_database(public)
    model = PythonProjects()
    row = public.M("sites").where("name=?", (PROJECT,)).find()
    if row and (row["project_type"] != "Python" or row["path"] != str(PROJECT_PATH)):
        raise RuntimeError("同名宝塔项目已存在，未覆盖。")
    get = public.dict_obj()
    get.pjname, get.port, get.stype = PROJECT, "8766", "command"
    get.path, get.user, get.python_bin = str(PROJECT_PATH), "roomsearch", PYTHON
    get.env_file, get.env_list, get.framework = str(environment), [], "python"
    get.project_cmd = PYTHON + " " + str(CODE / "classroom.py") + " serve --public-origin http://10.129.81.32"
    get.auto_run, get.release_firewall = True, False
    # Scoped adapters reuse the existing low-privilege service account and ready-made venv.
    # BT's default wizard filters out system users and installs unrelated WSGI servers.
    system_users = model.get_system_user_list
    model.get_system_user_list = lambda: sorted(set(system_users()) | {account.pw_name})
    model.run_simple_prep_env = lambda _project_id, _values: (True, "existing environment reused")
    subprocess.run(["systemctl", "stop", "room-search", "room-search-admin", "room-search-desktop"], check=True)
    try:
        if not row:
            checked(model.CreateProject(get), "创建宝塔 Python 项目")
        config = model._get_project_conf(PROJECT)
        if not config:
            raise RuntimeError("读取宝塔项目配置失败。")
        if config.get("project_cmd") != get.project_cmd or config.get("user") != "roomsearch":
            raise RuntimeError("现有宝塔项目启动配置与本项目不一致，未覆盖。")
        model._main__prepare_start_conf(config, force=True)
        manager = ServiceManager.new_mgr(PROJECT)
        for service in ({"name": "desktop", "command": "/bin/bash " + str(CODE / "deploy/desktop.sh"), "level": 5},
                        {"name": "admin", "command": PYTHON + " " + str(CODE / "classroom.py") +
                         " serve --port 8767 --admin-origin https://10.129.81.32", "level": 8}):
            existing = next((item for item in manager.other_services if item["name"] == service["name"]), None)
            error = manager.modify_service(existing["sid"], service) if existing else manager.add_service(service)
            if error:
                raise RuntimeError("登记宝塔附加服务失败。")
        config = model._get_project_conf(PROJECT)
        domain = public.M("domain").where("name=? AND port=?", ("10.129.81.32", 80)).find()
        site_id = public.M("sites").where("name=?", (PROJECT,)).getField("id")
        if domain and domain["pid"] != site_id:
            raise RuntimeError("站点地址已绑定其他宝塔项目，未覆盖。")
        if not domain:
            public.M("domain").insert({"name": "10.129.81.32", "pid": site_id, "port": 80, "addtime": public.getDate()})
        config["domains"], config["bind_extranet"], config["auto_run"] = ["10.129.81.32:80"], 1, True
        public.M("sites").where("id=?", (site_id,)).update({"project_config": json.dumps(config), "ps": "北京大学教室查课"})
        vhost = Path("/www/server/panel/vhost/nginx")
        old, target = vhost / "room-search.conf", vhost / "python_room-search.conf"
        if old.exists() and target.exists():
            raise RuntimeError("存在两份站点配置，请先核对，未覆盖。")
        if old.exists():
            old.rename(target)
        elif not target.exists():
            target.write_bytes((CODE / "deploy/nginx.conf").read_bytes())
        target.chmod(0o644)
        subprocess.run(["nginx", "-t"], check=True)
        ServiceManager.new_mgr(PROJECT).start_project()
        status = project_status()
        if not status["running"] or len(status["services"]) != 3 or any(not item["pid"] for item in status["services"]):
            raise RuntimeError("宝塔项目或附加服务未启动。")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for url in ("http://127.0.0.1:8766/api/meta", "http://127.0.0.1:8767/api/meta", "http://127.0.0.1:6080/vnc.html"):
            for attempt in range(10):
                try:
                    with opener.open(url, timeout=3) as response:
                        if response.status != 200:
                            raise RuntimeError("宝塔服务健康检查失败。")
                    break
                except OSError:
                    if attempt == 9:
                        raise RuntimeError("宝塔服务健康检查未通过。") from None
                    time.sleep(0.5)
        subprocess.run(["nginx", "-s", "reload"], check=True)
        subprocess.run(["systemctl", "disable", "room-search", "room-search-admin", "room-search-desktop"], check=True)
    except Exception:
        # Keep an existing deployment available if migration fails before completion.
        try:
            manager = ServiceManager.new_mgr(PROJECT)
            if not isinstance(manager, str):
                manager.stop_project()
        finally:
            subprocess.run(["systemctl", "start", "room-search-desktop", "room-search-admin", "room-search"], check=False)
        raise
    return {"project": status, "database": database}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    with panel_context():
        result = project_status() if args.check else register()
        print(json.dumps(result, ensure_ascii=False))
