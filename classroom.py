"""PKU classroom search and PostgreSQL import/sync CLI."""
import argparse
import datetime as dt
import json

from room_search import store
from room_search.model import today


def main():
    parser = argparse.ArgumentParser(description="北京大学 · 教室查课")
    commands = parser.add_subparsers(dest="command")
    server = commands.add_parser("serve", help="启动搜索软件")
    server.add_argument("--port", type=int, default=8766)
    commands.add_parser("import-existing", help="离线导入现有 PostgreSQL 课次库；不修改回放表")
    commands.add_parser("reclassify", help="校历修改后，按日期重算所有已存课次的学期")
    commands.add_parser("configure-database", help="单独输入并加密保存课表数据库连接")
    create = commands.add_parser("create-database", help="创建独立 PostgreSQL 数据库并加密保存连接")
    create.add_argument("--name", default="pku_classroom")
    sync = commands.add_parser("sync", help="正常认证接口按日同步，需已有本人登录态")
    sync.add_argument("--from", dest="start", type=dt.date.fromisoformat, default=today())
    sync.add_argument("--to", dest="end", type=dt.date.fromisoformat)
    args = parser.parse_args()
    if args.command == "configure-database":
        import getpass
        from room_search.database import save_configuration
        print(json.dumps(save_configuration(getpass.getpass("PostgreSQL 连接串（隐藏输入）: ")), ensure_ascii=False))
        return
    if args.command == "create-database":
        from room_search.database import create_database
        print(json.dumps(create_database(args.name), ensure_ascii=False))
        return
    if args.command in (None, "serve"):
        from room_search.server import serve
        return serve(getattr(args, "port", 8766))
    store.init_schema()
    if args.command == "import-existing":
        print(json.dumps(store.import_existing(), ensure_ascii=False), flush=True)
    elif args.command == "reclassify":
        print(json.dumps(store.reclassify(), ensure_ascii=False), flush=True)
    elif args.command == "sync":
        from room_search.sync import sync_day
        start, end = args.start, args.end or args.start
        if end < start:
            parser.error("结束日期不能早于开始日期")
        day = start
        while day <= end:
            result = sync_day(day, lambda message: print(f"{day} {message}", flush=True))
            print(json.dumps(result, ensure_ascii=False), flush=True)
            day += dt.timedelta(days=1)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        from room_search.auth import AuthError
        print(str(error) if isinstance(error, (AuthError, ValueError, RuntimeError)) else
              f"运行失败（{type(error).__name__}），请检查数据库配置或网络。", flush=True)
        raise SystemExit(1)
