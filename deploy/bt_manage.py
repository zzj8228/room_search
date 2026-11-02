"""Manage the server-side BT Python project using BT's own project manager."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys

PROJECT = "room-search"
PANEL = Path("/www/server/panel")


@contextmanager
def panel_context():
    if os.name != "posix" or os.geteuid() != 0 or not (PANEL / "BT-Panel").is_file():
        raise RuntimeError("请仅在 Ubuntu 服务器上使用宝塔 Python 以 root 运行此命令。")
    os.chdir(PANEL)
    sys.path[:0] = [str(PANEL), str(PANEL / "class")]
    from BTPanel import app
    with app.test_request_context("/"):
        yield


def project_status():
    import public
    from projectModel.pythonModel import main as PythonProjects
    from mod.project.python.serviceMod import ServiceManager
    row = public.M("sites").where("name=? AND project_type=?", (PROJECT, "Python")).field(
        "id,name,path,project_config").find()
    if not row:
        return {"registered": False}
    config = json.loads(row["project_config"])
    manager = ServiceManager.new_mgr(PROJECT)
    services = manager.get_services_info()
    return {"registered": True, "id": row["id"], "name": row["name"], "path": row["path"],
            "code": "/opt/room-search", "auto_run": bool(config.get("auto_run")),
            "running": bool(PythonProjects().get_project_run_state(PROJECT)),
            "services": [{"name": value.get("name"), "pid": value.get("pid"),
                          "ports": value.get("ports", []),
                          "status": "running" if value.get("pid") else "stopped"} for value in services]}


def manage(action):
    import public
    from projectModel.pythonModel import main as PythonProjects
    if action != "status":
        get = public.dict_obj()
        get.name = PROJECT
        model = PythonProjects()
        method = {"start": model.StartProject, "stop": model.StopProject,
                  "restart": model.RestartProject}[action]
        result = method(get)
        if not isinstance(result, dict) or not result.get("status"):
            raise RuntimeError("宝塔项目操作失败，请在服务器面板查看项目日志。")
    return project_status()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "start", "stop", "restart"), default="status", nargs="?")
    arguments = parser.parse_args()
    with panel_context():
        print(json.dumps(manage(arguments.action), ensure_ascii=False))
