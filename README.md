# 智能答辩分组编排系统

截至 2026-10-30 07:28（北京时间）只读核对：**预答辩第 18 版已发布，正式答辩第 9 版为草稿；两阶段均为 54 组、301 人，无漏排或重复，31 个六人组、23 个五人组。**正式每组 5 位评审，沿用预答辩组号、学生与秘书，全部评审轮换并回避本组导师。此前正式第 7 版未排全的结果已被替代。详细状态、证据范围和未闭环事项见[当前状态与待办](docs/reviews/当前状态与待办-2026-10-30.md)。

当前 policy 3：预／正式学生每组 **5～7 人，以 6 人为主**，共同优化组内学生份额和教师出场次数。预答辩默认 3 位评审（含组长），组长按副教授及以上职称判断；必要小组允许第 2 位外院导师。正式固定 5 位含主席，外院至多 1 位，导师回避且不要求到场；具体资格、兼容入口及验证见[正式轮换说明](docs/releases/正式答辩专家轮换-2026-10-30.md)。教室在人员和时间确定后预约。

当前仍有 **33 组预答辩均衡提示、另 8 组已解释例外，两阶段各 86 条教师时间待确认提示**。已发布状态、完整覆盖和自动回归通过不能替代实际到场确认、均衡验收或新版 EXE 验证。源码验证与保存版本分别记录，详见[需求追踪](docs/requirements/全量需求追踪.md)。

历史资料入口（policy 2）：`test-data/打开当前排期.cmd` 对应先前保留的草稿，不自动代表当前源码或业务库状态。2026-10-23 旧规则交付、三／五专家试算、三专家第 12 版修复均按原日期与版本解释；“四人下限”记录为已撤销的误改，不能作为生效规则。历史链接和结果保留供追溯。

基于 Vue 3、TypeScript、Vite、Element Plus、Django 和 DRF 的答辩分组排期系统，支持基础数据管理、规则配置、自动排期、冲突检测、人工调整、Excel 导出和操作日志。

项目总体进度、需求状态、里程碑和阻塞统一维护在 [STATUS.md](STATUS.md)。原定本期目标为 2026 年 10 月 18 日前完成全部需求，当前仍在集成验收，包含完善排期质量评分；近期体验优化与待办见[清单](docs/requirements/产品体验与待办清单.md)。日常开发遵循 [CONTRIBUTING.md](CONTRIBUTING.md)，完整目录见 [文档索引](docs/README.md)。

现已支持草稿校验发布、历史快照、并发编辑保护、生成请求去重和服务端审计。升级、备份恢复及生产部署参见 [稳定性升级与运维说明](docs/guides/稳定性升级与运维说明.md)。

2026-10-23 已按原表备注和用户澄清更正：316份学生资料中301人参排、15人不参排，两阶段各50组。原始备注保留，不为不参排者补校区；系统及独立硬冲突核验通过，教室仍为拟用待确认，Word视觉分页核验尚未完成。结果见[301人排期交付](docs/releases/排期结果交付-2026-10-23.md)，操作见[本批资料操作入口](docs/guides/本批资料操作入口-2026-10-23.md)。

历史记录（2026-10-17）：新增导入前检查与标准化预览，支持显式补全年份／校区及工作表选择，并修复指定秘书因职称被排除的问题。小规模完整流程已验证，全量排期仍有资料及实现阻塞，详见[本次验证记录](docs/releases/导入修复与流程验证-2026-10-17.md)。`test-data/` 中的真实资料及验证产物仅保留本地，不提交 Git。

2026-10-19 整合三份业务分支，加入固定专家人数、资料预检、评分、随机种子和调整／日志／导出改动。来源、组合问题修复及验证限制见[分支集成记录](docs/releases/分支集成与验证-2026-10-19.md)。这次源码整合不代表全部业务验收或新版 EXE 已发布。

V2 架构将排期接口、应用服务、输入适配与纯算法领域分开，前后端共用场景规则；新增教师资格与稳定人员关联、预答辩/正式答辩联合生成、关联移动校验和 PDF 打印保存。实现范围、迁移步骤和兼容说明见 [架构升级说明](docs/architecture/架构升级说明.md)。

完整的功能说明、输入/输出格式与运行截图见 [WIKI.md](WIKI.md)；课程综合开发提交材料见 [WIKI/综合开发应用证明.md](WIKI/综合开发应用证明.md)。

## 环境要求

- Node.js 24.13.1（以 `.nvmrc` 为准）及随附 npm；通过 `npm ci` 安装锁定依赖
- Python 3.12（以 `.python-version` 为准；运行依赖在 `requirements.txt` 固定）

开发模式安装和真实后端联调见 [新人上手](docs/guides/开发环境与新人上手.md)，共享导入样例见 [tests/fixtures](tests/fixtures/README.md)。

## 一键启动（推荐）

首次从源码安装（PowerShell，在项目根目录执行）：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
npm ci
$env:VITE_USE_MOCK = 'false'
$env:VITE_ENABLE_DEMO_TOOLS = 'false'
npm run build
.\.venv\Scripts\python main.py
```

安装并构建一次后，在已激活虚拟环境的终端执行 `python main.py` 即可启动。`dist/` 不进入 Git，首次获取源码必须先构建前端；主程序不会自动运行 npm。

`main.py` 会自动完成运行时初始化、数据库迁移、首次空库生成管理员（写入 `app-data/INITIAL_ADMIN.txt`），并在 `http://127.0.0.1:8000` 提供服务、自动打开浏览器。端口被占用时自动选择空闲端口，以终端输出地址为准。

## 安装与启动

Windows 本机部署可直接使用脚本：

```powershell
.\scripts\setup-windows.ps1
.\.venv\Scripts\python manage.py createsuperuser
.\scripts\start-windows.ps1
```

脚本会安装依赖、构建前端、执行数据库迁移，并通过 Django 托管 `dist` 前端产物。启动后访问 `http://127.0.0.1:8000`。

开发模式前端启动：

```bash
npm ci
npm run dev
```

后端本地启动：

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

本机启动后直接进入工作台，无需账号或密码；系统自动使用本机管理员身份。

## Mock 与真实后端切换

前端通过环境变量控制数据来源：

```env
VITE_USE_MOCK=true
VITE_ENABLE_DEMO_TOOLS=true
VITE_API_BASE_URL=http://localhost:8000/api
VITE_API_PROXY_TARGET=http://localhost:8000
VITE_USE_REMOTE_RULE_CONFIG=false
VITE_USE_REMOTE_CONFLICT_CHECK=false
DJANGO_DEBUG=true
DJANGO_SECRET_KEY=change-me-in-local-dev
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,testserver
DJANGO_CORS_ALLOWED_ORIGINS=http://localhost:5173
```

- `VITE_USE_MOCK=true`：使用前端 Mock 和浏览器本地存储，适合单机演示。
- `VITE_USE_MOCK=false`：请求 `VITE_API_BASE_URL` 指向的后端接口，适合前后端联调。
- `VITE_ENABLE_DEMO_TOOLS=true`：显示演示指南、验收测试和重置演示数据入口；生产环境保持 `false`。
- 未设置 `VITE_API_BASE_URL` 时，开发服务器会把 `/api/*` 代理到 `VITE_API_PROXY_TARGET`，默认 `http://localhost:8000`。
- 真实后端模式始终使用后端规则与冲突检测；旧 `VITE_USE_REMOTE_*` 开关不再用于降级到本地数据。
- 后端默认关闭 `DEBUG` 与全开放 CORS；本地开发请在环境变量中显式开启需要的配置。

构建后的前端会由 Django 根路径托管，`/api/` 仍保留给后端接口，`/admin/` 保留给 Django 管理后台。

## 常用命令

```bash
npm run check
npm run lint
npm run test:domain
npm run build
npm run preview
python scripts/check-project-docs.py
python manage.py test
python manage.py check --deploy
```

生产部署前请参考 `.env.production.example` 设置长随机 `DJANGO_SECRET_KEY`、关闭 `DJANGO_DEBUG`、限制 `DJANGO_ALLOWED_HOSTS` / `DJANGO_CORS_ALLOWED_ORIGINS`，并在 HTTPS 环境中开启 secure cookie、HSTS 和 SSL redirect。

## 打包说明

仓库已支持生成单文件 Windows 可执行程序：

V2 Windows 64 位发行版见 [v2026.10.02 Release](https://github.com/xph6666/defense_scheduler/releases/tag/v2026.10.02)，升级旧版前请备份整个 `app-data` 文件夹。具体变更与实现范围见 [本次发布说明](docs/releases/发布说明-v2026.10.02.md)。

```powershell
.\scripts\build-exe.ps1
.\release\DefenseScheduler.exe
```

可执行程序会在 `release\app-data` 下保存运行数据：

- `db.sqlite3`：本机数据库
- `secret.key`：本机 Django 密钥

本机启动后直接进入工作台，无需输入密码，也不再生成初始密码文件。请妥善保管 `release\app-data` 目录。默认会监听 `http://127.0.0.1:8000` 并打开浏览器；可通过环境变量调整：

```powershell
$env:DEFENSE_SCHEDULER_PORT = "8080"
$env:DEFENSE_SCHEDULER_HOST = "127.0.0.1"
$env:DEFENSE_SCHEDULER_OPEN_BROWSER = "false"
.\release\DefenseScheduler.exe
```

这个 exe 面向本机单用户或小范围离线使用。若要作为多人局域网/公网服务部署，建议改用标准 Django 部署方式，配置独立数据库、HTTPS、反向代理和生产级 WSGI 服务。
