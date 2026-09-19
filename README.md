# 智能答辩分组编排系统

基于 Vue 3、TypeScript、Vite、Element Plus、Django 和 DRF 的答辩分组排期系统，支持基础数据管理、规则配置、自动排期、冲突检测、人工调整、Excel 导出和操作日志。

现已支持草稿校验发布、历史快照、并发编辑保护、生成请求去重和服务端审计。升级、备份恢复及生产部署参见 [稳定性升级与运维说明](开发文档/稳定性升级与运维说明.md)。

完整的功能说明、输入/输出格式与运行截图见 [WIKI.md](WIKI.md)；课程综合开发提交材料见 [WIKI/综合开发应用证明.md](WIKI/综合开发应用证明.md)。

## 环境要求

- Node.js 18+
- npm 9+
- Python 3.12（推荐；当前固定依赖按此版本验证）

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
npm install
npm run dev
```

后端本地启动：

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

真实后端模式下，前端登录使用 Django 用户账号；请先创建管理员或业务用户。

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
npm run build
npm run preview
python manage.py test
python manage.py check --deploy
```

生产部署前请参考 `.env.production.example` 设置长随机 `DJANGO_SECRET_KEY`、关闭 `DJANGO_DEBUG`、限制 `DJANGO_ALLOWED_HOSTS` / `DJANGO_CORS_ALLOWED_ORIGINS`，并在 HTTPS 环境中开启 secure cookie、HSTS 和 SSL redirect。

## 打包说明

仓库已支持生成单文件 Windows 可执行程序：

```powershell
.\scripts\build-exe.ps1
.\release\DefenseScheduler.exe
```

可执行程序会在 `release\app-data` 下保存运行数据：

- `db.sqlite3`：本机数据库
- `secret.key`：本机 Django 密钥
- `INITIAL_ADMIN.txt`：首次启动自动生成的管理员账号和密码

首次登录后请立即修改管理员密码，并妥善保管 `release\app-data` 目录。默认会监听 `http://127.0.0.1:8000` 并打开浏览器；可通过环境变量调整：

```powershell
$env:DEFENSE_SCHEDULER_PORT = "8080"
$env:DEFENSE_SCHEDULER_HOST = "127.0.0.1"
$env:DEFENSE_SCHEDULER_OPEN_BROWSER = "false"
.\release\DefenseScheduler.exe
```

这个 exe 面向本机单用户或小范围离线使用。若要作为多人局域网/公网服务部署，建议改用标准 Django 部署方式，配置独立数据库、HTTPS、反向代理和生产级 WSGI 服务。
