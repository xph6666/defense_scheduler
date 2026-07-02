# 智能答辩分组编排系统

基于 Vue 3、TypeScript、Vite、Element Plus、Django 和 DRF 的答辩分组排期系统，支持基础数据管理、规则配置、自动排期、冲突检测、人工调整、Excel 导出和操作日志。

## 环境要求

- Node.js 18+
- npm 9+
- Python 3.12+

## 安装与启动

Windows 本机部署可直接使用脚本：

```powershell
.\scripts\setup-windows.ps1
python manage.py createsuperuser
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
- `VITE_USE_REMOTE_RULE_CONFIG=true`：启用后端规则配置接口；后端未部署该接口时保持 `false`。
- `VITE_USE_REMOTE_CONFLICT_CHECK=true`：启用后端冲突检测接口；后端未部署该接口时保持 `false`。
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

当前仓库已具备单服务运行基础：先 `npm run build`，再由 Django 服务前端与 API。若要生成真正的 Windows `.exe`，建议下一步引入 PyInstaller 或桌面壳；本机当前未安装 PyInstaller。
