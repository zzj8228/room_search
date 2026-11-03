# 本地运行与校园网部署

本项目有两种独立使用方式：Windows EXE 启动本机网页，或者 Ubuntu 服务器提供校园网共享查询。两者不共享登录凭证；GitHub 和 EXE 均不附带数据库、连接密码或教学网会话。

## Windows：双击 EXE

1. 拉取仓库，将 `RoomSearch.exe` 放在可写目录中并双击。
2. 预先准备 PostgreSQL 专用数据库。已安装的 PostgreSQL 可以继续使用；EXE 不安装任何环境。
3. 首次启动时输入本项目数据库连接串，例如 `host=127.0.0.1 port=5432 dbname=pku_classroom user=room_search_app password=YOUR_PASSWORD`。输入框隐藏内容，验证后以 Windows DPAPI 加密保存。
4. 自动打开本机网页；在启动窗口中也可重新打开网页。关闭启动窗口停止本地服务。
5. 需要更新数据时，在网页中点击“登录教学网”，使用本机已安装的 Edge/Chrome 完成官方登录，返回页面点击“已完成登录”，校验通过后自动同步所选日期。

EXE 包含 Python、psycopg、静态网页及 agent-browser 0.39.1 原生控制程序，不含环境安装器。只监听 `127.0.0.1`，端口自动选择。认证数据保存在 EXE 同目录的 `data/`；更换 Windows 用户后须重新配置数据库、重新登录。

Windows 源码的安装、配置、启动和打包统一通过 `manage.ps1` 操作，`-Action` 可选 `Setup`、`Configure`、`Start`、`Build`，省略时启动源码服务。双击 `start-classroom.cmd` 等价于 `Start`。依赖版本集中在 `requirements.txt`。

重建 EXE 需要构建机上的 Python 3.13 和 agent-browser 0.39.1。可按下方源码说明安装项目内的浏览器工具，然后执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\manage.ps1 -Action Build
```

构建依赖只进入 `.build-venv/`，PyInstaller 固定为 6.19.0，输出为根目录 `RoomSearch.exe`。优先打包项目 `.tools/` 中的原生浏览器控制程序，也兼容构建机已有的全局安装。打包资源使用白名单，不读取 `data/`、`.env` 或 SSH 文件；不会启动应用或运行测试。

## Windows：源码安装与配置

所有命令均在项目根目录运行。Windows 安装操作只管理项目虚拟环境，不访问宝塔面板。

### 需要哪些环境

| 组件 | 要求与用途 |
| --- | --- |
| Python | 3.13 x64；应用依赖仅装入项目 `.venv` |
| PostgreSQL | PostgreSQL 18（源库 18.4，服务器 18.6）；数据库可在本机或其他可连接服务器，不在 pip 中安装 |
| Git | 克隆与更新代码；下载源码 ZIP 时可不用 |
| 浏览器 | Edge、Chrome 等，用于访问本机查课页面 |
| agent-browser | 官方登录时需要，使用 0.39.1；离线搜索无需此工具 |
| Node.js / npm | 仅安装或运行浏览器工具时需要；agent-browser 0.39.1 声明要求 Node.js 24+ |
| 校园网络 | 登录教学网、智云 SSO、同步目录时需要；查询已有数据只需连接 PostgreSQL |

Python 依赖版本集中锁定在 `requirements.txt`。锁定版本为 `psycopg==3.3.6`、`psycopg-binary==3.3.6`、`tzdata==2026.6`。后端其余功能使用 Python 标准库，前端为原生 HTML/CSS/JavaScript，不需要前端构建。

### 1. 获取项目并创建独立虚拟环境

```powershell
git clone https://github.com/zzj8228/room_search.git
Set-Location room_search
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\manage.ps1 -Action Setup
```

仓库若为私有，需要先取得访问权限并完成自己的 GitHub 登录。`ExecutionPolicy Bypass` 仅作用于这次 PowerShell 进程，不修改系统策略。

`manage.ps1 -Action Setup` 使用 Python 3.13 创建当前项目 `.venv`，安装锁定依赖并执行 `pip check`。不执行全局 pip/npm 安装，不需要激活虚拟环境。手动安装等价命令：

```powershell
py.exe -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable); print(sys.prefix != sys.base_prefix)"
```

最后应输出本项目 `.venv\Scripts\python.exe` 和 `True`。不要复制其他项目的 `.venv`；如果已有 `.venv` 使用其他 Python 版本，停止本项目服务，将其改名留存，再重新运行安装脚本。

`manage.ps1` 使用 ASCII 提示以兼容 Windows PowerShell 5.1；若添加中文，应保存为带 BOM 的 UTF-8。

### 2. 创建独立 PostgreSQL 数据库

已有本软件专用 `pku_classroom` 数据库时，直接进入第 3 步。全新安装需要先准备 PostgreSQL 服务；可使用已有服务器，安装脚本不会替你安装系统服务或修改其配置。

使用管理员在 `psql` 中执行以下 SQL。用户名和库名是示例；`\password` 会交互设置密码，不把真实密码写入 SQL 文件：

```sql
CREATE ROLE room_search_app LOGIN;
\password room_search_app
CREATE DATABASE pku_classroom OWNER room_search_app ENCODING 'UTF8' TEMPLATE template0;
```

应用账号应拥有该数据库、可建立 `pku_room_search` schema 和表；日常运行不需要超级用户权限。`psycopg-binary` 自带数据库客户端组件，应用运行无需 `psql` 或编译器；上面的建库操作也可通过 PostgreSQL 管理工具完成。

程序另提供 `classroom.py create-database --name pku_classroom`。此命令需要显式的 `PKU_CLASSROOM_ADMIN_DATABASE_URL`，其账号具备 `CREATEDB` 权限；创建出的库由该账号拥有。推荐采用上面的独立应用账号方式。

### 3. 保存本项目数据库连接

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\manage.ps1 -Action Configure
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

### 4. 启动软件

双击 `start-classroom.cmd`，或执行：

```powershell
.\.venv\Scripts\python.exe classroom.py serve --port 8766
```

打开 <http://127.0.0.1:8766>。首次启动自动建立 schema、表和固定节次。新建空库没有课程属于正常情况，需要同步或导入；GitHub 仓库不携带本机的课表数据或数据库备份。

命令行启动时按 Ctrl+C 结束。若双击启动器后服务已在后台运行，端口仍占用；应确认 `data/classroom-server.pid` 对应本项目进程后再停止它，不要终止其他软件的进程。使用其他端口时手动打开相应地址，双击启动器仍使用 8766。

### 5. 配置独立登录工具（需要在线同步时）

如果已有可用的 `agent-browser.cmd`，无需重复安装。否则在项目内部安装，不使用 `npm install -g`：

```powershell
npm.cmd --prefix .tools install --save-exact --no-audit --no-fund agent-browser@0.39.1
& .\.tools\node_modules\.bin\agent-browser.cmd install
```

第一条命令将 npm 包安装到项目 `.tools/`，应用优先发现其中的 CLI；没有该文件才查找 PATH 中已有 CLI。第二条命令安装工具所需的浏览器资产，资产使用工具自身管理的用户缓存；不会安装全局 npm 包或改系统 PATH。若需完全限制安装目录，可先使用已有浏览器工具，或依据该工具对应版本的说明配置其浏览器位置。

离线查询、首次建表和数据库配置都不依赖 Node.js 或 agent-browser。

1. 在查课页面点击“登录教学网”，打开本项目专属的官方登录窗口。
2. 在官方窗口完成登录，再返回查课页面点击“已完成登录”。
3. 通过智云在线校验后，会话加密写入 `data/auth/pku-browser-state.dpapi`。
4. 点击“同步所选日期”，或运行下面的命令：

```powershell
.\.venv\Scripts\python.exe classroom.py sync --from 2026-10-21 --to 2026-10-21
```

校园账号必须具有对应服务的访问权限；浏览器登录成功后仍需 SSO 与目录接口校验。本项目不读取 `pku_resource_gui` 的登录态，也不保存明文密码。网络或认证失败时保留已有课表。

### 6. 可选：从现有回放库复制课表

仅适用于已有与原项目兼容的 `pku_courses`、`pku_lessons`、`pku_catalog_days` 表。显式向当前进程提供 `PKU_CLASSROOM_IMPORT_DATABASE_URL` 后运行：

```powershell
.\.venv\Scripts\python.exe classroom.py import-existing
Remove-Item Env:PKU_CLASSROOM_IMPORT_DATABASE_URL -ErrorAction SilentlyContinue
```

源连接应使用具有这些表读取权限的账号；导入事务为只读。目标和源必须是不同数据库。不复制媒体链接或认证数据。学期按课次日期重算，默认教室丢弃；默认只导入已配置校历最早日期及以后的数据。完整规则见 [README.md](README.md)。

### 常见问题

| 现象 | 检查方法 |
| --- | --- |
| 找不到 Python 3.13 | 检查 `py.exe -0p`；安装对应 Python 后重新运行 `manage.ps1 -Action Setup` |
| PowerShell 拒绝执行脚本 | 使用第 1 步的进程级 `-ExecutionPolicy Bypass`，无需改全局策略 |
| 缺少 psycopg | 确认用本项目 `.venv` 的 Python 执行，重跑 `manage.ps1 -Action Setup` |
| 无法读取 PostgreSQL | 确认服务、主机、端口、库名、账号权限；重新执行 configure-database |
| 无法解密配置 | 使用保存时的 Windows 用户，或重新配置/登录 |
| 页面没有课程 | 检查所选日期是否已同步；空库、未覆盖日期不能解释为教室空闲 |
| 找不到 agent-browser | 安装到项目 `.tools` 或使用 PATH 中已有 CLI；安装后重试登录 |
| SSO 超时或会话过期 | 检查校园网、代理，再通过本项目官方窗口重新登录 |
| 8766 端口被占用 | 检查已有本项目服务，或用 `serve --port 8767` 并手动访问 |

`.venv/`、`.tools/`、`data/`、`.env`、数据库转储均由 Git 忽略。更新代码后重新运行 `manage.ps1 -Action Setup`；修改校历后重启服务，并执行 `classroom.py reclassify`。

## 当前服务器

| 项目 | 配置 |
| --- | --- |
| 系统 | Ubuntu 24.04 x64 |
| 查询入口 | `http://10.129.81.32/` |
| 管理入口 | `https://10.129.81.32/admin/` |
| 数据库 | PostgreSQL 18，当前安装 18.6；源数据库为 18.4 |
| 代码 / 虚拟环境 | `/opt/room-search/`、`/opt/room-search/.venv/` |
| 宝塔项目 | 网站 → Python 项目 → `room-search` |
| 宝塔项目工作目录 | `/www/wwwroot/room-search/`，仅作为启动目录；代码仍在 `/opt/room-search/` |
| 专用用户 / 数据库 | `roomsearch` / `pku_classroom` |
| 私有运行数据 | `/var/lib/room-search/`，用户专属目录，权限 700 |
| Nginx 站点配置 | `/www/server/panel/vhost/nginx/python_room-search.conf` |
| 管理员密码文件 | `/etc/room-search/admin-credentials.txt`，仅 root 可读 |
| TLS 证书 | `/etc/room-search/tls.crt`、`tls.key` |

PostgreSQL 18 的后续补丁版本可以恢复 18.4 的逻辑备份。不得用 Ubuntu 默认安装命令无意间装成其他主版本，也不要将 18 的备份直接恢复到较旧主版本。安装入口会确认默认 Unix socket 连接的 PostgreSQL 主版本为 18；若系统已有其他版本占用默认连接，会停止，需先处理集群配置。

以下宝塔命令**只在 Ubuntu 服务器执行**，不会访问或修改本机 Windows 宝塔。服务器使用宝塔 Python 项目管理器管理主查询服务及 `admin` 附加服务，开机自动启动；原应用 systemd 服务禁用。服务器登录改用 IAAA 官方扫码接口，不使用 noVNC、远程桌面或服务器浏览器。PostgreSQL 本身仍使用系统安装的 18.6。

宝塔“数据库 → PostgreSQL”通过 `127.0.0.1:5432` 的连接登记已有 `pku_classroom`，显示为本机系统 PostgreSQL 的接入连接；不安装第二套数据库。面板专用账号 `pku_classroom` 只有查询权限，密码在服务器生成并保存于宝塔私有配置中，应用继续使用原 `roomsearch` 的 Unix socket peer 认证。管理员的网页登录和同步由应用原有权限执行。

## 新服务器安装

安装脚本面向 **Ubuntu 24.04 x64 + 宝塔 Nginx**，需要 sudo/root。使用其他 IP 或域名时，先修改 `deploy/nginx.conf` 的 `server_name`、两个应用 service 的来源地址，以及 `deploy/install.sh` 的证书地址。

```bash
sudo git clone https://github.com/zzj8228/room_search.git /opt/room-search
cd /opt/room-search
sudo bash deploy/install.sh install
```

`deploy/install.sh install` 先确认 root 权限、Ubuntu 24.04 x64、代码目录和服务器宝塔环境，再添加 PostgreSQL 官方 PGDG 签名源，明确安装 PostgreSQL 18、客户端、Python venv 与 OpenSSL。随后建立独立服务用户和数据库、安装锁定的 Python 依赖，并在缺失时生成管理密码和 TLS 证书。服务器无需安装 agent-browser、Chrome 或桌面组件。最后 `bt_register.py` 使用服务器宝塔自带管理器登记现有环境、Python 项目、附加服务与 PostgreSQL 接入连接，保留已有认证文件和 Nginx 配置。

有私有课表备份时，可在空数据库的首次部署中指定：

```bash
sudo env ROOM_SEARCH_CATALOG_DUMP=/absolute/path/classroom.dump bash deploy/install.sh
```

脚本拒绝将备份恢复到已有课表表的数据库。无备份时数据库最初为空，登录后按日期同步即可。GitHub 不提供数据库转储。

安装完成后检查：

```bash
sudo -u postgres psql -Atc 'SHOW server_version;'
sudo nginx -t
sudo /www/server/panel/pyenv/bin/python3 /opt/room-search/deploy/bt_manage.py status
curl http://127.0.0.1:8766/api/meta
sudo cat /etc/room-search/admin-credentials.txt
```

只有 80/443 需要供校园网访问。数据库 5432、查询后端 8766、管理后端 8767 只监听回环地址，不应在安全组或防火墙中对外开放。旧桌面端口 5901/6080 不再使用，旧 `/admin/desktop/` 路径返回 404。

## 管理员登录与同步

1. 通过 HTTPS 管理入口登录管理账号；公开查询页不提供登录和同步功能。
2. 当前内网 IP 使用自签名证书。先通过可信渠道核对证书指纹并在设备上信任；不要跳过未知证书警告。IP 不变时可使用包含 IP SAN 的内部 CA 证书，但访问设备须信任该 CA。管理页不得使用 HTTP。
3. 选择同步日期，点击“IAAA 扫码登录”，管理页直接显示 IAAA 官方生成的二维码。
4. 使用“北京大学”App 扫描，并在手机上核对授权对象为北京大学教学网后确认。校园密码仅在官方 App 内处理，不在查课网站输入。
5. 服务器先访问教学网建立初始会话，再使用同一内存 Cookie 容器申请并轮询官方二维码。扫码确认后经 HTTPS 回调并访问教学网首页，随后通过本人课程入口完成智云 SSO 与在线校验。仅有初始 Cookie 不算登录成功，只有完整校验通过后才加密保存，页面自动隐藏二维码并同步所选日期。
6. 二维码本地有效期三分钟；取消或超时后清除内存中的图片和临时 Cookie。刷新管理页可恢复显示仍有效的二维码；刷新后成功登录需要手动点击“同步所选日期”。已有有效会话时可直接同步，过期则重新扫码。
7. “取消扫码”停止本次授权等待；“退出登录”删除本项目已保存的教学网会话，保留课表数据。取消本地等待不代表撤销已在官方 App 确认的其他会话。

管理页另有“同步至当前日期”按钮：从最早已覆盖日期起补齐尚无覆盖记录的日期，一直处理到点击时的北京时间今天；已有覆盖的历史日期跳过，今天每次都会刷新。空数据库先同步今天，有课表的空日也算已覆盖。未来覆盖记录不影响这个范围。任务显示日期和进度，与单日同步互斥；中途失败保留已完成的日期，再次点击继续补齐。按钮只在管理页显示，后端也仅接受管理服务发起的请求，公开查询服务和本地普通模式均拒绝该接口。批量任务只在本次进程内运行，重启服务后需重新点击。

IAAA 使用教学网的既有 `blackboard` 应用配置与官方回调，网站自身没有申请通用 IAAA OAuth 应用。当前官方配置中的 redirect 值含历史 HTTP 地址，本项目仅把它作为官方协议参数传给 IAAA；实际携带票据的请求使用对应 HTTPS 回调，拒绝 HTTP 降级和非允许域名跳转。若校方更改接口、回调或验证要求，登录将停止；不会改为明文传输、请求粘贴 Cookie 或索取校园密码。

二维码属于短时授权入口，只允许已认证的管理员读取，不可截图转发。服务器不向浏览器返回 IAAA 票据、Cookie、JWT 或上游原始响应；扫码图片、IAAA Cookie 和票据只在内存中暂存。二维码只接受具有 PNG/JPEG 文件特征的内容，并使用对应图片类型返回；兼容 IAAA 将 JPEG 错标为 `text/html` 的响应，不将上游 HTML 作为二维码页面显示。只将经过校验的教学网与智云会话加密保存，不保存 IAAA 通用 SSO Cookie。管理路径关闭 Nginx 访问日志，API 与二维码响应禁用缓存并限制为同源读取；官方 HTTPS 连接使用系统 CA 校验。

这是单个管理员维护共享课表的方案。服务器 root、宝塔管理员和掌握管理账号的人属于信任边界；本机加密无法抵御这些权限被攻破。不要分享管理密码、二维码或私有备份。

Linux 会话使用 Fernet 加密，密钥为 `/var/lib/room-search/auth/secret.key`，权限 600、属于服务用户；Windows 继续使用用户绑定的 DPAPI。不要单独复制 Linux 会话而丢失密钥；也不要把密钥与会话备份放入公开目录。

## 维护

```bash
# 更新依赖并合并宝塔配置，重启主服务和 admin；也可在面板直接重启
sudo bash /opt/room-search/deploy/install.sh restart

# 运行日志可在宝塔项目中查看，不输出原始 Cookie/JWT
sudo tail -n 40 /www/wwwlogs/python/room-search/error.log

# 仅导出课表 schema，不含校园登录态
sudo -u roomsearch pg_dump -Fc --no-owner --no-acl \
  --schema=pku_room_search pku_classroom > classroom.dump
```

当前服务器的 `/opt/room-search` 为 Git 工作目录。先在本地修改并推送 GitHub，再在服务器拉取；默认不备份旧代码。以下命令均在服务器执行：

```bash
sudo git -C /opt/room-search status --short
sudo bash /opt/room-search/deploy/install.sh update
```

`update` 拒绝覆盖服务器上的未提交改动，使用 `git pull --ff-only` 后执行新版本的 `restart`。`restart` 安装 `requirements.txt` 依赖、离线补全院系，随后重新登记宝塔项目：移除旧 desktop 附加服务、保留 admin，合并 Nginx 的旧桌面路由后重启。不会重新初始化数据库、证书或管理密码。本次从复制部署迁移到 Git 部署时，已按管理员要求用仓库版本覆盖旧的复制代码，保留独立虚拟环境与私有配置。修改 Nginx 后先执行 `sudo nginx -t`，成功后 `sudo nginx -s reload`。不要覆盖 `/var/lib/room-search` 或 `/etc/room-search`。

从已有 systemd 部署迁移时，在核对 Git 代码并拉取后执行一次 `sudo bash /opt/room-search/deploy/install.sh register`。该脚本复用已有环境和配置，检测到同名的其他项目/数据库连接时停止，不创建代码副本。旧版桌面服务会停止并从本项目中移除，保留其他软件可能使用的系统包；Nginx 只迁移已知桌面路由及管理日志/Referrer 设置，格式不符时停止而不覆盖。宝塔项目启动目录与代码目录分开，避免面板的目录属主调整影响 root 管理的代码。

更新脚本中的 `repair-departments` 离线补齐同一课程已有院系，无法推断的记录仍留空。管理员在网站完成教学网登录后，可重新同步受影响日期；也可执行下面的命令，只补全历史空院系。不要在终端粘贴 Cookie 或 JWT。

```bash
sudo -u roomsearch env PKU_CLASSROOM_DATABASE_URL='host=/var/run/postgresql dbname=pku_classroom user=roomsearch' \
  PKU_CLASSROOM_DATA_DIR=/var/lib/room-search /opt/room-search/.venv/bin/python \
  /opt/room-search/classroom.py repair-departments --online
```

仓库提供可选的 `room-search-sync.timer`，默认不启用；按需启用后在北京时间 06:30、12:30、19:30 更新昨日、今日和明日目录。过期会话需要管理员重新登录，任务失败保留原课表。

## 凭证与发布边界

- 公开服务运行只读模式：拒绝所有写请求，不提供教学网登录状态或任务状态接口；管理服务只经 Nginx HTTPS + Basic Auth 访问。
- 校验 Host、Origin 与跨站请求，二维码接口仅管理站点可用；没有公开 CORS；前端将课程数据作为文本显示。
- 登录 Cookie/JWT 在服务端校验后加密保存；API、网页、GitHub 和 EXE 均不返回这些值。应用不保存校园账号密码。
- 数据库走本机 socket，服务用户无 PostgreSQL 超级用户权限；应用以专用普通用户运行。
- 发布内容不包含 `data/`、`.env`、`.dpapi`、`secret.key`、SSH 密钥、数据库备份、日志或管理员密码。
- 服务器 root 和拥有管理入口访问权的人属于信任边界，应限制这些权限并妥善保管私有备份。
