# 智能答辩分组编排系统

当前实际预答辩第 12 版草稿已保存：**3 专家、301 人全部安排、44 个六人组、6 个五人组、1 个七人组、0 硬错误**。组长按用户确认的副教授及以上职称判断；仍有均衡和时间待核对提示，未宣称全部业务验收通过。详见[本轮实际页面修复](docs/releases/三专家预答辩实际流程修复-2026-10-30.md)。

最新范围：[仅修复三专家预答辩的实际页面流程](docs/releases/三专家预答辩实际流程修复-2026-10-30.md)。组长按副教授及以上职称判断，不要求另勾角色；组内偏斜逐组提示，完整可行预答辩方案经重新校验后保留，避免限时重算退回缺人结果。本轮不生成正式答辩，旧五专家隔离试算不能作为当前页面验收。

新增[跨组联合调整](docs/releases/跨组联合调整-2026-10-30.md)：两组学生、教师、时间共同重排，五专家 301 人只读试算中保持 44 个六人组、6 个五人组、1 个七人组，组内集中度降低 37.5%，出场次数平方和降低约 4.2%。仍有均衡未达标项，未替换业务库排期或重新打包 EXE。

2026-10-30 后续澄清：在每组 5～7 人的硬范围内，六人组偏好、组内各评审所带学生数均衡、教师参加次数均衡共同优化。下文 44 个六人组是先前人数优先目标的试算，不能作为当前教师均衡达标结论。参见[共同均衡说明](docs/releases/人数与教师共同均衡-2026-10-30.md)。

历史资料入口（policy 2）：2026-10-24 本地资料整理到忽略的 `test-data/`，`test-data/打开当前排期.cmd` 对应当时保留的 301 人两阶段草稿，不是新版重新生成的结果。旧诊断、旧交付、旧 EXE 和旧备份经用户确认已永久删除。远端检查与整理记录见[检查报告](docs/reviews/GitHub与本地整理-2026-10-24.md)。

2026-10-30 最新规则：先生成预答辩、核对后平移正式答辩；预答辩 3 位专家。**每组仅允许 5～7 人，以 6 人为主，少量 5／7 人组消化余数**。先尝试每组最多 1 位外院专家；人数底线无法满足时，必要的小组允许第 2 位外院导师。教师时间、资格、学生完整性及固定组号严格保留，联合优化出场次数和参与学生数，再集中同日上午下午。301 人快照采用 5 专家后实现 44 个六人组、6 个五人组、1 个七人组，全部覆盖；默认 3 专家仍有 3 人未安排。详见[本轮验证](docs/releases/仅五至七人与六人优先-2026-10-30.md)。

历史口径：2026-10-23 的[至少 4 人规则](docs/releases/预答辩导师评审规则修正-2026-10-23.md)及[人数上调记录](docs/releases/专家人数可调-2026-10-23.md)仅解释旧 policy 2。上述 301 人结果和旧 EXE 不自动代表新版算法验收完成。已修复旧资料空白时间被当作不可用及同时段秘书容量漏检的问题，Chrome 真实资料副本现已生成两阶段各 91 组、301 人、0 未安排；84 位教师额外时间仍待核对。详见[真实全量修复记录](docs/releases/真实全量排期修复-2026-10-29.md)；日常业务库及原交付库未迁移，未重打包 EXE。新版日常运行前须备份并应用 `0012_current_scheduling`。

基于 Vue 3、TypeScript、Vite、Element Plus、Django 和 DRF 的答辩分组排期系统，支持基础数据管理、规则配置、自动排期、冲突检测、人工调整、Excel 导出和操作日志。

项目总体进度、需求状态、里程碑和阻塞统一维护在 [STATUS.md](STATUS.md)。本期目标为 2026 年 10 月 18 日前完成全部需求，包含完善排期质量评分；近期体验优化与待办见[清单](docs/requirements/产品体验与待办清单.md)。日常开发遵循 [CONTRIBUTING.md](CONTRIBUTING.md)，完整目录见 [文档索引](docs/README.md)。

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
