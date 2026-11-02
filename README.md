# 教室查课

按学期、上课日期、教学楼、教室、节次或时钟时间查询北京大学课程安排。支持 Windows EXE 本地运行和 Ubuntu 校园网网站部署，均使用独立的 PostgreSQL 数据库 `pku_classroom`。原回放库只作为复制来源，不写入、不共用课次表。

## 两种运行方式

| 场景 | 启动方式 | 要求 |
| --- | --- | --- |
| Windows 本地使用 | 双击仓库根目录 `RoomSearch.exe` | Windows 10/11 x64、可连接的 PostgreSQL、已安装的 Edge 或 Chrome |
| Ubuntu 校园网网站 | Nginx + systemd，详见 [DEPLOYMENT.md](DEPLOYMENT.md) | Ubuntu 24.04、PostgreSQL 18、宝塔 Nginx |

EXE 已包含 Python 运行时、应用依赖、网页及登录浏览器控制工具；不安装 Python、Node.js、数据库或其他环境。首次启动会要求输入本项目专用数据库连接串，使用当前 Windows 用户的 DPAPI 加密保存到 EXE 同目录的 `data/`。启动后自动打开本机网页，关闭启动窗口即停止服务。请将 EXE 放在有写入权限的目录中。

仓库不附带课表数据或账号。新数据库需要通过本人登录同步，或从私有备份恢复。EXE 的登录使用本机已安装的浏览器，不包含个人浏览器配置。源码运行方式和原有命令继续可用。

校园网网站的公开页面仅支持查询；管理员通过 HTTPS 管理入口打开服务器独立浏览器，在官方教学网完成登录，校验成功后自动关闭弹窗、加密保存会话并同步所选日期。管理密码、Cookie、JWT、数据库配置及备份均不包含在仓库或 EXE 中。

## 打开

完整的系统要求、PostgreSQL 建库、独立登录、虚拟环境安装及故障排查见 [REQUIREMENTS.md](REQUIREMENTS.md)。Python 依赖统一使用 `requirements.txt`，并引用 `requirements-lock.txt` 中的确定版本。

本项目独立运行，所有 Python 命令均在项目根目录运行。首次配置环境：

```powershell
.\setup.ps1
```

脚本仅创建本项目 `.venv`，并将锁定依赖装入其中，不安装全局 Python/npm 包。也可手动使用已有 Python 3.13 创建 `.venv`，然后执行 `.\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements-lock.txt`。

双击 `start-classroom.cmd`，或在项目目录运行：

```powershell
.\.venv\Scripts\python.exe classroom.py serve
```

访问 [http://127.0.0.1:8766](http://127.0.0.1:8766)。例如选择 2026-10-21、理教-307，查询当天全天课程。教室为下拉列表，先选择教学楼可缩小候选范围；切楼或切学期后，不再适用的旧教室会自动清空。选择“全部教室”可查看该教学楼全部记录。教学楼与教室选择后自动更新结果。

支持：

- 按学期、日期和教室组合检索；显示课程、教师、院系、教室、具体节次。
- 全天、连续节次、单个时刻、时间范围四种模式；点击 12 个节次按钮快速查询。
- 每个日期的每条课次单独保留，不按课程去重，不把某一周课表复制到全学期。
- 同教室同时间存在多条课程记录时全部保留，便于发现数据冲突。
- 查询条件保存在浏览器地址栏，刷新后恢复；支持桌面和手机窄屏。
- 搜索仅访问 PostgreSQL，无需有效校园登录态；同步当日目录才使用本人登录态。
- 未入库、已入库但无匹配课次分别提示，不将无匹配解释成教室空闲。

## 独立数据库

本项目所有运行数据保存在 `data/`；数据库连接为 `data/auth/postgres.dpapi`，教学网会话为 `data/auth/pku-browser-state.dpapi`，均由当前 Windows 用户的 DPAPI 加密。`PKU_CLASSROOM_DATA_DIR` 可重设本项目数据目录。不会读取回放软件的配置、Cookie、JWT、浏览器配置或环境变量。

新机器可连接一个独立的空数据库（连接串隐藏输入）：

```powershell
.\.venv\Scripts\python.exe classroom.py configure-database
```

也可只在当前 PowerShell 进程设置 `PKU_CLASSROOM_DATABASE_URL`。创建新数据库时，显式提供 `PKU_CLASSROOM_ADMIN_DATABASE_URL` 后执行 `classroom.py create-database --name pku_classroom`；不从其他项目取得连接。目标库若存在回放表，配置命令会拒绝保存。

离线复制回放库数据是可选的一次性引导步骤：仅在当前进程显式配置 `PKU_CLASSROOM_IMPORT_DATABASE_URL`，再执行 `classroom.py import-existing`。源和目标必须是不同数据库，不保存源库连接、不自动寻找旧项目。

导入时原库事务为 `REPEATABLE READ READ ONLY`，只读取课程名、教师、院系、课次 ID、日期、课次标题和地点，以及日期覆盖标记。**不复制密码、Cookie、JWT、回放地址或视频。** 当前仅复制 `semesters.json` 中最早已配置教学期（2025-09-08）之后的数据。

独立库的 `pku_room_search` schema 包含：

| 表 | 内容 |
| --- | --- |
| `terms` | 日期计算得到的学期名称和排序 |
| `periods` | 12 个固定节次及开始、结束时间 |
| `lessons` | 实际上课日期、地点、课程、教师、院系、节次数组、学期 ID |
| `days` | 当日目录覆盖、入库数量、剔除原因、更新时间 |

按日期、学期、教学楼、教室建立索引，SQL 参数化。同步成功后以事务替换该日快照；网络、认证、格式或数据库失败时保留原有数据。重复导入不重复增加课次；已经直接从平台同步的日期不会被旧库复制结果覆盖。

每日课程列表不一定包含院系。同步时先复用**同一课程 ID** 下唯一的已知院系，其余有效课次通过正常 `schedule/search-live-course-list` 接口补全；仅提取院系名称，不保留详情响应及其中可能含有的回放信息。接口未返回院系或请求失败时保留已有院系，仍缺失的课次显示“院系未提供”，同步结果提示待补充数量。不根据教师、课程名称或其他课程猜测院系。

历史空院系可执行 `.\.venv\Scripts\python.exe classroom.py repair-departments`，仅用本库同一课程的已知院系补齐，不访问网络。添加 `--online` 可使用本项目已保存的有效登录态查询排课接口补全剩余项；此命令只更新空院系，不替换日期课表、不修改非空院系。

## 按上课日期划分三个学期

学期完全根据**该条课次的上课日期**落入哪个校历区间确定，忽略原库课程的学期标签。北京大学学年从秋季开始，例如 2026 年秋季、2027 年春季和夏季属于 2026–2027 学年。

已于 2026-10-31 通过[官方校历页面](https://simso.pku.edu.cn/pages/ccSchoolCalendar.html#/home)核对：

| 学年 | 秋季学期 | 春季学期 | 夏季学期 |
| --- | --- | --- | --- |
| 2025–2026 | 2025-09-08～2026-01-11 | 2026-03-02～2026-06-28 | 2026-07-06～2026-08-09 |
| 2026–2027 | 2026-09-07～2027-01-10 | 2027-02-22～2027-06-27 | 2027-07-05～2027-08-08 |

首尾日期包含。秋、春学期采用校本部上课开始日至考试结束所在周末；夏季严格使用约五周的暑期学校时间，不等同整个暑假。放假期间不生成课次、不根据星期推算补课，界面只显示源目录实际返回的日期记录。

当前统一采用**校本部校历**，医学部、深圳研究生院个别开课或考试日期可能不同；如需覆盖各校区专属边界，应扩展校历配置与匹配规则。未配置的历史／未来日期、寒暑假非教学期单列为“非教学期／校历待配置”，不借用原课程标签猜测归属。

配置文件：`room_search/semesters.json`。修改后重启服务，执行 `.\.venv\Scripts\python.exe classroom.py reclassify` 重算全部已存课次的学期，包括直接同步过的日期。程序检查区间不重叠、起止合法；新学年可以继续增加三个区间。

## 12 个标准节次

| 节次 | 时间 | 节次 | 时间 |
| --- | --- | --- | --- |
| 1 | 08:00–08:50 | 7 | 15:10–16:00 |
| 2 | 09:00–09:50 | 8 | 16:10–17:00 |
| 3 | 10:10–11:00 | 9 | 17:10–18:00 |
| 4 | 11:10–12:00 | 10 | 18:40–19:30 |
| 5 | 13:00–13:50 | 11 | 19:40–20:30 |
| 6 | 14:00–14:50 | 12 | 20:40–21:30 |

北京时间 UTC+8。时间匹配使用左闭右开区间 `[开始,结束)`：08:00 匹配第一节，08:50 和 08:55 均不匹配；09:00 匹配第二节。连上两节课不会把中间休息时间视为上课。范围查询只要和任一真实节次存在正长度交集即匹配，单个课次只返回一次。

节次来自真实课次标题，例如“2026-10-21第5-6节”。不能识别或超出第1–12节的条目计入 `unrecognized_period`，不会擅自安排时间。

## 过滤“默认教学楼默认教室”

在规范化、入库之前舍弃包含“默认教学楼”或“默认教室”的地点，包括“默认校区默认教学楼-默认教室”、有空格和分隔符的变体；空地点也舍弃。保留原始地点与简化地点，实际地点去掉“北京大学本部”前缀，按最后一个连字符拆分教学楼与房号。

地点和节次的剔除计数按天记录；页面显示默认教室及无法识别节次的数量。新库不包含这些占位地点，原库不删除任何记录。

## 独立登录与目录同步

参考固定提交 `145f0319467b7dfead4f0c139d8d5885d6aeedd0` 的 `claspider/src/zhiyun.rs` 中 `fetch_day` 参数。认证实现借鉴 PKU Replay v0.2.3 的官方 SSO 流程，代码已复制并适配在本项目 `room_search/auth.py` 中独立维护；目录 HTTP 客户端是本项目的 `room_search/client.py`，不导入、不调用回放软件或其服务。

1. 点击页面“登录教学网”，通过已安装的 `agent-browser.cmd` 打开本项目专属的可见浏览器会话。
2. 在官方教学网窗口完成账号或扫码登录，无需把密码交给本软件。
3. 返回课表页面点击“已完成登录”。服务器从专属浏览器在内存中取得 Cookie，通过教学网本人课程入口建立智云 SSO，并在线验证目录访问成功后才加密保存会话；不会把原始 Cookie/JWT 写入日志。
4. 点击“同步所选日期”，或执行下面的同步命令。会话过期后在本软件重新登录。

登录接口为本服务的 `/api/auth/*`，独立端口 8766，浏览器会话名以本项目绝对路径计算，不带旧浏览器 profile，也不使用浏览器明文状态文件。登录成功关闭专属窗口；退出登录只删除本项目的校园会话并关闭该窗口，数据库和离线搜索保留。登录操作后台运行，页面轮询状态。优先使用项目 `.tools/node_modules/.bin/agent-browser.cmd`，再查找 PATH 中已有工具；本项目不会安装任何全局 npm 包。安装方法见 [REQUIREMENTS.md](REQUIREMENTS.md)。

查询正常日期目录，不按是否存在回放筛选，不获取或下载视频。

```powershell
.\.venv\Scripts\python.exe classroom.py sync --from 2026-10-28 --to 2026-10-31
```

页面“同步所选日期”在后台同步一天，显示任务状态；已有同步任务时不重复启动。详情学期标签不参与分类；只为缺少可复用院系的有效课程请求排课信息，每门课程在本次同步中最多请求一次。

使用正常 `course-live/search-live-course-list`，参数为 `need_time_quantum=1`、`unique_course=1`、`with_sub_duration=1`、`search_time=日期`、`tenant=226`、`course_student_type=`、`sub_live_status=`、`with_sub_data=1`。展开时段及真实课次，按课程 ID+课次 ID 去重；子课次自己的地点优先于课程地点。不使用展示已删除内容的额外参数。

当前数据库是智云目录的覆盖范围，不能保证包含智云没有收录的课程或线下临时调课。[教务部](https://dean.pku.edu.cn/service/web/courseSearch.php)和[选课系统](https://elective.pku.edu.cn)是补充核对入口，本版本没有把它们的学期周课表按假定周次展开成实际日期。

## API

- `GET /api/auth/status`：本项目会话状态，不返回 Cookie/令牌。
- `POST /api/auth/login`、`/api/auth/complete`、`/api/auth/logout`：JSON `{}`，独立登录、验证保存、退出。
- `GET /api/meta`：总量、学期、校历边界、节次与覆盖日期。
- `GET /api/locations?term=2026-2027-1`：该学期教学楼和教室列表。
- `GET /api/search?date=2026-10-21&term=2026-2027-1&room=理教-307&mode=time&time=08:30`。
- `mode=period&period_from=3&period_to=4`，或 `mode=range&start=10:00&end=12:00`。
- `GET /api/search?...&page=2`：每页60课次，返回总数、当日覆盖与日期实际学期。
- `POST /api/sync`：JSON 请求体 `{"date":"2026-10-31"}`，返回任务 ID。
- `GET /api/job?id=任务ID`：本次进程内任务状态。

默认仅监听 `127.0.0.1`，校验 Host、Origin、跨站请求；无跨站 CORS。前端用文本节点展示来源数据，不将课程名称当 HTML 执行。服务器模式仍只监听回环地址，由 Nginx 提供公开只读查询和受认证保护的管理入口；详见部署说明。不提供多用户校园账号托管。

## 项目结构

- `classroom.py`：CLI；`start-classroom.cmd` / `.ps1`：本机启动器。
- `room_search/model.py`、`semesters.json`：日期学期、节次、教室规范化。
- `room_search/database.py`、`store.py`：独立 PostgreSQL 配置与事务查询/写入。
- `room_search/auth.py`、`login.py`、`client.py`、`sync.py`：独立加密会话、浏览器登录、目录请求及按日同步。
- `room_search/server.py`、`static/`：本机 API 与中文界面。
- `data/`、`.venv/`：本机私有数据和虚拟环境，均被 Git 忽略。

仓库只记录运行代码、使用文档、依赖锁定文件及 Windows EXE。真实密钥与凭据仅保存在私有运行目录；`data/`、`*_secrets.py`、`*_credentials.py`、`*.local.py`、`local_config.py`、`secrets.py`、`credentials.py`、`*.key`、`*.pem` 和 `.ssh/` 均忽略。认证模块只包含加解密逻辑，不内嵌任何个人密钥。已经被 Git 跟踪的文件不会因新增忽略规则而自动移除，发布前必须检查跟踪列表。
