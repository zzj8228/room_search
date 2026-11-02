"""Portable desktop launcher: bundled runtime, no environment installation."""
from __future__ import annotations

import http.server
import json
from pathlib import Path
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser

from room_search import database, store
from room_search.paths import ROOT
from room_search.server import Handler


def open_json(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=5) as response:
        return json.load(response)


def make_server():
    store.init_schema()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def smoke_test(destination):
    server, url = make_server()
    try:
        meta = open_json(url + "/api/meta")
        locations = open_json(url + "/api/locations")
        search = open_json(url + "/api/search?date=2026-10-21&room=" + urllib.parse.quote("理教-307"))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=5) as response:
            html = response.read()
        assert b"search-form" in html and meta["application"] == "pku-classroom"
        Path(destination).write_text(json.dumps({"ok": True, "frozen": bool(getattr(sys, "frozen", False)),
            "listen": "127.0.0.1", "totals": meta["totals"], "locations": len(locations["locations"]),
            "sample_results": search["total"], "runtime_data": str(ROOT / "data")}, ensure_ascii=False), encoding="utf-8")
    finally:
        server.shutdown()
        server.server_close()


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        return smoke_test(sys.argv[2])
    import tkinter as tk
    from tkinter import messagebox, simpledialog, ttk
    root = tk.Tk()
    root.title("教室查课 · 本地服务")
    root.geometry("470x245")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=24)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="北京大学 · 教室查课", font=("Microsoft YaHei UI", 17)).pack(anchor="w")
    status = tk.StringVar(value="正在连接 PostgreSQL…")
    ttk.Label(frame, textvariable=status, wraplength=420).pack(anchor="w", pady=(18, 12))
    ttk.Label(frame, text="关闭此窗口将停止本次本地服务。", foreground="#666666").pack(anchor="w")
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(20, 0))
    open_button = ttk.Button(buttons, text="打开查询网页", state="disabled")
    open_button.pack(side="left")
    server = None

    def configure():
        value = simpledialog.askstring("配置 PostgreSQL", "请输入本项目专用 PostgreSQL 连接串。\n例如 host=127.0.0.1 dbname=pku_classroom user=... password=...\n不会安装数据库，连接配置将使用 Windows DPAPI 加密保存。", show="*", parent=root)
        if not value:
            return False
        try:
            database.save_configuration(value)
            return True
        except Exception:
            messagebox.showerror("连接失败", "无法连接数据库，请核对服务、数据库名称、账号和密码。", parent=root)
            return False

    def change_configuration():
        if configure():
            messagebox.showinfo("已保存", "数据库连接已加密保存。请关闭后重新启动本程序。", parent=root)

    ttk.Button(buttons, text="配置数据库", command=change_configuration).pack(side="left", padx=10)
    ttk.Button(buttons, text="关闭服务", command=root.destroy).pack(side="right")

    def start():
        nonlocal server
        try:
            database.require_database_url()
        except Exception:
            if not configure():
                status.set("尚未配置数据库。请点击“配置数据库”，保存后重新启动。")
                return
        try:
            server, url = make_server()
        except Exception:
            status.set("无法启动：请检查 PostgreSQL 服务和本项目数据库连接。")
            return
        status.set("本地服务已启动：" + url + "\n仅本机可访问，教学网登录态加密保存在本机。")
        open_button.configure(state="normal", command=lambda: webbrowser.open(url))
        webbrowser.open(url)

    root.after(100, start)
    root.mainloop()
    if server:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
