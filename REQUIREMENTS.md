# 环境要求与安装配置

本软件当前面向 **Windows 10/11 x64、Python 3.13**。数据库和校园登录凭证使用 Windows DPAPI；macOS、Linux 尚未适配。所有命令在项目根目录运行，以下以 PowerShell 为例。

## 需要哪些环境

| 组件 | 要求与用途 |
| --- | --- |
| Python | 3.13 x64，已验证 3.13.5；应用依赖仅装入项目 `.venv` |
| PostgreSQL | 已验证 18.4；数据库可在本机或其他可连接服务器，不在 pip 中安装 |
| Git | 克隆与更新代码；下载源码 ZIP 时可不用 |
| 浏览器 | Edge、Chrome 等，用于访问本机查课页面 |
| agent-browser | 官方登录时需要，已验证 0.39.1；离线搜索无需此工具 |
| Node.js / npm | 仅安装或运行浏览器工具、检查前端 JS 时需要；agent-browser 0.39.1 声明要求 Node.js 24+ |
| 校园网络 | 登录教学网、智云 SSO、同步目录时需要；查询已有数据只需连接 PostgreSQL |

Python 依赖文件：`requirements.txt` 引用 `requirements-lock.txt`。锁定版本为 `psycopg==3.3.6`、`psycopg-binary==3.3.6`、`tzdata==2026.6`。后端其余功能使用 Python 标准库，前端为原生 HTML/CSS/JavaScript，不需要前端构建。

## 1. 获取项目并创建独立虚拟环境

```powershell
git clone https://github.com/zzj8228/room_search.git
Set-Location room_search
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

仓库若为私有，需要先取得访问权限并完成自己的 GitHub 登录。`ExecutionPolicy Bypass` 仅作用于这次 PowerShell 进程，不修改系统策略。

`setup.ps1` 使用 Python 3.13 创建当前项目 `.venv`，安装锁定依赖并执行 `pip check`。不执行全局 pip/npm 安装，不需要激活虚拟环境。手动安装等价命令：

```powershell
py.exe -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable); print(sys.prefix != sys.base_prefix)"
```

最后应输出本项目 `.venv\Scripts\python.exe` 和 `True`。不要复制其他项目的 `.venv`；如果已有 `.venv` 使用其他 Python 版本，停止本项目服务，将其改名留存，再重新运行安装脚本。

PowerShell 脚本保存为带 BOM 的 UTF-8，以兼容 Windows PowerShell 5.1 的中文解析；编辑这些脚本时保留该编码。

## 2. 创建独立 PostgreSQL 数据库

已有本软件专用 `pku_classroom` 数据库时，直接进入第 3 步。全新安装需要先准备 PostgreSQL 服务；可使用已有服务器，安装脚本不会替你安装系统服务或修改其配置。

使用管理员在 `psql` 中执行以下 SQL。用户名和库名是示例；`\password` 会交互设置密码，不把真实密码写入 SQL 文件：

```sql
CREATE ROLE room_search_app LOGIN;
\password room_search_app
CREATE DATABASE pku_classroom OWNER room_search_app ENCODING 'UTF8' TEMPLATE template0;
```

应用账号应拥有该数据库、可建立 `pku_room_search` schema 和表；日常运行不需要超级用户权限。`psycopg-binary` 自带数据库客户端组件，应用运行无需 `psql` 或编译器；上面的建库操作也可通过 PostgreSQL 管理工具完成。

程序另提供 `classroom.py create-database --name pku_classroom`。此命令需要显式的 `PKU_CLASSROOM_ADMIN_DATABASE_URL`，其账号具备 `CREATEDB` 权限；创建出的库由该账号拥有。推荐采用上面的独立应用账号方式。

## 3. 保存本项目数据库连接

```powershell
.\.venv\Scripts\python.exe classroom.py configure-database
```

在隐藏输入提示中输入自己的连接信息。例如下面只是格式示例，不是可直接使用的凭证：

```text
host=127.0.0.1 port=5432 dbname=pku_classroom user=room_search_app password='YOUR_DATABASE_PASSWORD'
```

连接验证成功后，配置加密保存在 `data/auth/postgres.dpapi`。目标数据库包含原回放表时命令会拒绝保存。DPAPI 文件绑定当前 Windows 用户，换机器或账号后应重新配置，不要复制别人的凭证文件。

临时环境变量也可提供连接，优先于加密配置；不会自动读取 `.env` 文件。下表变量均属于本项目，普通安装只需要通过上面的交互命令保存数据库连接：

| 变量 | 用途 |
| --- | --- |
| `PKU_CLASSROOM_DATABASE_URL` | 覆盖本项目数据库连接，仅在需要时设置 |
| `PKU_CLASSROOM_DATA_DIR` | 更改数据/配置目录，默认项目 `data/` |
| `PKU_CLASSROOM_ADMIN_DATABASE_URL` | 可选建库命令的显式管理连接 |
| `PKU_CLASSROOM_IMPORT_DATABASE_URL` | 可选从旧回放库只读复制课表时的源连接 |
| `PKU_ROOM_SCHEMA` | 高级选项，默认 `pku_room_search`，通常不改 |

## 4. 启动软件

双击 `start-classroom.cmd`，或执行：

```powershell
.\.venv\Scripts\python.exe classroom.py serve --port 8766
```

打开 <http://127.0.0.1:8766>。首次启动自动建立 schema、表和固定节次。新建空库没有课程属于正常情况，需要同步或导入；GitHub 仓库不携带本机的课表数据或数据库备份。

命令行启动时按 Ctrl+C 结束。若双击启动器后服务已在后台运行，端口仍占用；应确认 `data/classroom-server.pid` 对应本项目进程后再停止它，不要终止其他软件的进程。使用其他端口时手动打开相应地址，双击启动器仍使用 8766。

## 5. 配置独立登录工具（需要在线同步时）

如果已有可用的 `agent-browser.cmd`，无需重复安装。否则在项目内部安装，不使用 `npm install -g`：

```powershell
npm.cmd --prefix .tools install --save-exact --no-audit --no-fund agent-browser@0.39.1
& .\.tools\node_modules\.bin\agent-browser.cmd install
```

第一条命令将 npm 包安装到项目 `.tools/`，应用优先发现其中的 CLI；没有该文件才查找 PATH 中已有 CLI。第二条命令安装工具所需的浏览器资产，资产使用工具自身管理的用户缓存；不会安装全局 npm 包或改系统 PATH。若需完全限制安装目录，可先使用已有浏览器工具，或依据该工具对应版本的说明配置其浏览器位置。

本机现有环境不需要运行这两条命令。离线查询、首次建表和数据库配置都不依赖 Node.js 或 agent-browser。

1. 在查课页面点击“登录教学网”，打开本项目专属的官方登录窗口。
2. 在官方窗口完成登录，再返回查课页面点击“已完成登录”。
3. 通过智云在线校验后，会话加密写入 `data/auth/pku-browser-state.dpapi`。
4. 点击“同步所选日期”，或运行下面的命令：

```powershell
.\.venv\Scripts\python.exe classroom.py sync --from 2026-10-21 --to 2026-10-21
```

校园账号必须具有对应服务的访问权限；浏览器登录成功后仍需 SSO 与目录接口校验。本项目不读取 `pku_resource_gui` 的登录态，也不保存明文密码。网络或认证失败时保留已有课表。

## 6. 可选：从现有回放库复制课表

仅适用于已有与原项目兼容的 `pku_courses`、`pku_lessons`、`pku_catalog_days` 表。显式向当前进程提供 `PKU_CLASSROOM_IMPORT_DATABASE_URL` 后运行：

```powershell
.\.venv\Scripts\python.exe classroom.py import-existing
Remove-Item Env:PKU_CLASSROOM_IMPORT_DATABASE_URL -ErrorAction SilentlyContinue
```

源连接应使用具有这些表读取权限的账号；导入事务为只读。目标和源必须是不同数据库。不复制媒体链接或认证数据。学期按课次日期重算，默认教室丢弃；默认只导入已配置校历最早日期及以后的数据。完整规则见 README。

## 7. 验证安装

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe classroom.py --help
Invoke-RestMethod http://127.0.0.1:8766/api/meta
```

`/api/meta` 应返回 `application: pku-classroom`，新库的课次数可以为零。数据库配置后可执行完整测试；测试只创建和清理新生成的临时 schema：

```powershell
.\.venv\Scripts\python.exe -m unittest room_search.test_classroom room_search.test_independence -v
```

仅运行 Python 逻辑测试、不连接 PostgreSQL：

```powershell
.\.venv\Scripts\python.exe -m unittest room_search.test_classroom.ModelTests room_search.test_independence -v
```

前端语法检查可运行 `node --check room_search/static/app.js`；教室联动回归脚本 `room_search/test-location-controls.ps1` 还需要服务运行和 `agent-browser.cmd` 在当前进程 PATH 中。项目内安装工具时，仅对当前 PowerShell 会话添加路径：

```powershell
$env:PATH = (Join-Path $PWD '.tools/node_modules/.bin') + ';' + $env:PATH
.\room_search\test-location-controls.ps1
```

## 常见问题

| 现象 | 检查方法 |
| --- | --- |
| 找不到 Python 3.13 | 检查 `py.exe -0p`；安装对应 Python 后重新运行 setup |
| PowerShell 拒绝执行脚本 | 使用第 1 步的进程级 `-ExecutionPolicy Bypass`，无需改全局策略 |
| 缺少 psycopg | 确认用本项目 `.venv` 的 Python 执行，重跑 setup |
| 无法读取 PostgreSQL | 确认服务、主机、端口、库名、账号权限；重新执行 configure-database |
| 无法解密配置 | 使用保存时的 Windows 用户，或重新配置/登录 |
| 页面没有课程 | 检查所选日期是否已同步；空库、未覆盖日期不能解释为教室空闲 |
| 找不到 agent-browser | 安装到项目 `.tools` 或使用 PATH 中已有 CLI；安装后重试登录 |
| SSO 超时或会话过期 | 检查校园网、代理，再通过本项目官方窗口重新登录 |
| 8766 端口被占用 | 检查已有本项目服务，或用 `serve --port 8767` 并手动访问 |

`.venv/`、`.tools/`、`data/`、`.env`、数据库转储均由 Git 忽略。更新代码后重新运行 setup；修改校历后重启服务，并执行 `classroom.py reclassify`。
