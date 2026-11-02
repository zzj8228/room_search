# 本地运行与校园网部署

本项目有两种独立使用方式：Windows EXE 启动本机网页，或者 Ubuntu 服务器提供校园网共享查询。两者不共享登录凭证；GitHub 和 EXE 均不附带数据库、连接密码或教学网会话。

## Windows：双击 EXE

1. 拉取仓库，将 `RoomSearch.exe` 放在可写目录中并双击。
2. 预先准备 PostgreSQL 专用数据库。已安装的 PostgreSQL 可以继续使用；EXE 不安装任何环境。
3. 首次启动时输入本项目数据库连接串，例如 `host=127.0.0.1 port=5432 dbname=pku_classroom user=room_search_app password=YOUR_PASSWORD`。输入框隐藏内容，验证后以 Windows DPAPI 加密保存。
4. 自动打开本机网页；在启动窗口中也可重新打开网页。关闭启动窗口停止本地服务。
5. 需要更新数据时，在网页中点击“登录教学网”，使用本机已安装的 Edge/Chrome 完成官方登录，返回页面点击“已完成登录”，校验通过后自动同步所选日期。

EXE 包含 Python、psycopg、静态网页及 agent-browser 0.39.1 原生控制程序，不含环境安装器。只监听 `127.0.0.1`，端口自动选择。认证数据保存在 EXE 同目录的 `data/`；更换 Windows 用户后须重新配置数据库、重新登录。

源码开发仍可使用 `setup.ps1` 和 `classroom.py`，详见 [REQUIREMENTS.md](REQUIREMENTS.md)。重建 EXE：在安装了 Python 3.13、agent-browser 0.39.1 的构建机运行 `powershell -ExecutionPolicy Bypass -File .\build-windows.ps1`。构建依赖只进入 `.build-venv/`，输出为根目录 `RoomSearch.exe`。打包资源使用白名单，不读取 `data/`、`.env` 或 SSH 文件。

## 当前服务器

| 项目 | 配置 |
| --- | --- |
| 系统 | Ubuntu 24.04 x64 |
| 查询入口 | `http://10.129.81.32/` |
| 管理入口 | `https://10.129.81.32/admin/` |
| 数据库 | PostgreSQL 18，当前安装 18.6；源数据库为 18.4 |
| 代码 / 虚拟环境 | `/opt/room-search/`、`/opt/room-search/.venv/` |
| 专用用户 / 数据库 | `roomsearch` / `pku_classroom` |
| 私有运行数据 | `/var/lib/room-search/`，用户专属目录，权限 700 |
| Nginx 站点配置 | `/www/server/panel/vhost/nginx/room-search.conf` |
| 管理员密码文件 | `/etc/room-search/admin-credentials.txt`，仅 root 可读 |
| TLS 证书 | `/etc/room-search/tls.crt`、`tls.key` |

PostgreSQL 18 的后续补丁版本可以恢复 18.4 的逻辑备份。不得用 Ubuntu 默认安装命令无意间装成其他主版本，也不要将 18 的备份直接恢复到较旧主版本。

## 新服务器安装

安装脚本面向 **Ubuntu 24.04 x64 + 宝塔 Nginx**，需要 sudo/root。使用其他 IP 或域名时，先修改 `deploy/nginx.conf` 的 `server_name`、两个应用 service 的来源地址，以及 `deploy/install.sh` 的证书地址。

```bash
git clone https://github.com/zzj8228/room_search.git
cd room_search
sudo bash deploy/bootstrap.sh
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y \
  xvfb x11vnc openbox novnc websockify fonts-noto-cjk
sudo bash deploy/install.sh
```

`bootstrap.sh` 添加 PostgreSQL 官方 PGDG 签名软件源，明确安装 PostgreSQL 18 与客户端、Python venv。`install.sh` 复制运行代码、建立独立服务用户和数据库、安装锁定的 Python 依赖、agent-browser 与 Chrome、生成管理密码和 TLS 证书，然后安装 systemd 与 Nginx 配置。数据库连接使用本机 Unix socket 的 peer 认证，不设置可公开使用的数据库密码。

有私有课表备份时，可在空数据库的首次部署中指定：

```bash
sudo env ROOM_SEARCH_CATALOG_DUMP=/absolute/path/classroom.dump bash deploy/install.sh
```

脚本拒绝将备份恢复到已有课表表的数据库。无备份时数据库最初为空，登录后按日期同步即可。GitHub 不提供数据库转储。

安装完成后检查：

```bash
sudo -u postgres psql -Atc 'SHOW server_version;'
sudo nginx -t
sudo systemctl status room-search room-search-admin room-search-desktop
curl http://127.0.0.1:8766/api/meta
sudo cat /etc/room-search/admin-credentials.txt
```

只有 80/443 需要供校园网访问。数据库 5432、查询后端 8766、管理后端 8767、远程桌面 5901 和 WebSocket 6080 都只监听回环地址，不应在安全组或防火墙中对外开放。

## 管理员登录与同步

1. 访问 HTTPS 管理入口，输入服务器生成的管理账号密码。普通用户使用公开查询入口，无需校园账号。
2. 当前使用内网 IP 自签名证书，浏览器首次会提示不受信任。先核对证书指纹；正式长期使用时可换成已申请域名与受信任证书。不要将管理页改回 HTTP。
3. 选择希望同步的日期，点击“登录教学网”，允许该站点弹窗。
4. 弹窗显示服务器专用浏览器的官方教学网页面。账号密码或扫码操作在该浏览器内完成；不是在本机获取 Cookie，也不是查课网站模仿的登录表单。
5. 程序检测到官方教学网页面登录完成后，通过本人课程入口建立智云 SSO 并在线校验。成功后保存加密会话，关闭浏览器及弹窗，自动同步所选日期。
6. 已有有效会话时可直接点击“同步所选日期”。会话过期则重新登录。退出登录只删除教学网会话，不删除课表数据。

弹窗仅管理员可访问，十分钟未完成登录会自动结束。不要向他人分享管理密码、管理浏览器弹窗或远程桌面连接。当前设计为单个管理员维护共享课表，不是多用户校园账号托管平台。

Linux 会话使用 Fernet 加密，密钥为 `/var/lib/room-search/auth/secret.key`，权限 600、属于服务用户；Windows 继续使用用户绑定的 DPAPI。不要单独复制 Linux 会话而丢失密钥；也不要把密钥与会话备份放入公开目录。

## 维护

```bash
# 重启应用；公开查询与管理员界面分别运行
sudo systemctl restart room-search room-search-admin

# 查看应用日志；不输出原始 Cookie/JWT
sudo journalctl -u room-search -u room-search-admin -n 80 --no-pager

# 仅导出课表 schema，不含校园登录态
sudo -u roomsearch pg_dump -Fc --no-owner --no-acl \
  --schema=pku_room_search pku_classroom > classroom.dump
```

当前服务器的 `/opt/room-search` 已登记为 Git 工作目录。更新时先在本地修改、验证并推送 GitHub，再在服务器备份并拉取。以下命令均在服务器执行：

```bash
# 私有备份不放进项目目录或 GitHub
sudo install -d -m 700 /var/backups/room-search
sudo sh -c 'umask 077; sudo -u roomsearch pg_dump -Fc --no-owner --no-acl --schema=pku_room_search pku_classroom > /var/backups/room-search/before-update-$(date +%Y%m%d-%H%M%S).dump'

sudo git -C /opt/room-search status --short
sudo git -C /opt/room-search pull --ff-only origin main
# 仅在 requirements*.txt 变化时更新依赖
# sudo /opt/room-search/.venv/bin/pip install -r /opt/room-search/requirements.txt
sudo -u roomsearch env PKU_CLASSROOM_DATABASE_URL='host=/var/run/postgresql dbname=pku_classroom user=roomsearch' \
  /opt/room-search/.venv/bin/python /opt/room-search/classroom.py repair-departments
sudo systemctl restart room-search room-search-admin
curl --fail http://127.0.0.1:8766/api/meta
```

如果 `git status` 显示服务器源码被修改，先核对差异，不要使用强制覆盖。原安装脚本复制文件形成的新部署需要先核对已部署文件，再将运行目录登记为 Git 工作目录；不能直接覆盖已有配置。修改 Nginx 后先执行 `sudo nginx -t`，成功后 `sudo nginx -s reload`。不要覆盖 `/var/lib/room-search` 或 `/etc/room-search`。

`repair-departments` 离线补齐同一课程已有院系，无法推断的记录仍留空。管理员在网站完成教学网登录后，可重新同步受影响日期；也可在上方环境变量命令后为 `repair-departments` 添加 `--online`，并同时设置 `PKU_CLASSROOM_DATA_DIR=/var/lib/room-search`，只查询排课接口补全历史空院系。不要在终端粘贴 Cookie 或 JWT。

仓库提供可选的 `room-search-sync.timer`，默认不启用；按需启用后在北京时间 06:30、12:30、19:30 更新昨日、今日和明日目录。过期会话需要管理员重新登录，任务失败保留原课表。

## 凭证与发布边界

- 公开服务运行只读模式：拒绝所有写请求，不提供教学网登录状态或任务状态接口；管理服务只经 Nginx HTTPS + Basic Auth 访问。
- 校验 Host、Origin 与跨站请求，登录弹窗 WebSocket 也必须来自管理站点；没有公开 CORS；前端将课程数据作为文本显示。
- 登录 Cookie/JWT 在服务端校验后加密保存；API、网页、GitHub 和 EXE 均不返回这些值。应用不保存校园账号密码。
- 数据库走本机 socket，服务用户无 PostgreSQL 超级用户权限；应用及桌面服务以专用普通用户运行。
- 发布内容不包含 `data/`、`.env`、`.dpapi`、`secret.key`、SSH 密钥、数据库备份、日志或管理员密码。
- 服务器 root 和拥有管理入口访问权的人属于信任边界，应限制这些权限并妥善保管私有备份。
