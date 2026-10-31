# 2026-10-31 独立项目迁移

目标项目：`D:/pku_resource/room_search`，使用独立 `.git`、`.venv` 和 `data`。

原项目：`D:/pku_resource/pku_resource_gui`。用户所指“2.3.0”对应本机可核验的迁移前发布基准 **v0.2.3**：`60cfb46`（package.json 的 version 为 `0.2.3`）；仓库没有 `2.3.0` 标签。恢复该提交的代码，并移除本次迁出的课表文件；不重置 Git 历史、不删除旧项目环境、发布产物及私有运行数据。

迁移前备份：`D:/pku_resource/.runtime/room-search-migration-20261031-174501/`，包含 `before-migration.zip`、`tracked.patch`、`manifest.json`。备份保存原 README 改动和全部课表源码，不含校园凭证、数据库连接或虚拟环境。

独立数据库继续使用 `pku_classroom` / `pku_room_search`；仅把其专用加密连接文件从旧公共运行目录复制至新项目 `data/auth/postgres.dpapi`。没有复制回放库的登录态、浏览器目录、视频或回放地址，没有更改原回放数据库。新项目不读取旧项目文件；可选的导入只能通过显式的源数据库环境变量，在只读事务中运行。

独立认证模块参考原项目 SSO 实现，作为新项目源码维护。提供自己的登录 API 与专属浏览器会话；凭证保存在新项目内，登录、刷新、退出均无需运行回放软件。

环境只安装在项目 `.venv`，没有安装全局 Python 或 npm 依赖。依赖版本记录于 `requirements-lock.txt`。

迁移完成验证：原项目 `git status --short` 为空，`git diff --exit-code 60cfb46` 成功；新项目 19 项自动化测试、JavaScript 语法检查、教学楼/教室浏览器回归均通过。运行数据库自检为 `pku_classroom`，不存在回放表 `public.pku_lessons`，有效课次仍为 120,382。独立登录窗口已实际打开，退出登录已通过界面验证；未登录真实校园账号，没有声称完整 SSO 或在线同步成功。

实际启动验证中修复了 Windows 浏览器后台进程继承输出管道导致登录状态卡在“正在打开”的问题：无需输出的打开/关闭命令使用空设备，只有读取 Cookie 时在内存中捕获输出。相关回归包含在 19 项测试中。
