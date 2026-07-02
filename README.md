# 智能答辩分组编排系统

基于 Vue 3、TypeScript、Vite 和 Element Plus 的答辩分组排期前端，支持基础数据管理、规则配置、自动排期、冲突检测、人工调整、操作日志和前端验收清单。

## 环境要求

- Node.js 18+
- npm 9+
- Python 3.12+

## 安装与启动

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
- 未设置 `VITE_API_BASE_URL` 时，开发服务器会把 `/api/*` 代理到 `VITE_API_PROXY_TARGET`，默认 `http://localhost:8000`。
- `VITE_USE_REMOTE_RULE_CONFIG=true`：启用后端规则配置接口；后端未部署该接口时保持 `false`。
- `VITE_USE_REMOTE_CONFLICT_CHECK=true`：启用后端冲突检测接口；后端未部署该接口时保持 `false`。
- 后端默认关闭 `DEBUG` 与全开放 CORS；本地开发请在环境变量中显式开启需要的配置。

真实联调前请确认后端已提供教师、学生、教室、排期、冲突检测、人工调整、规则配置和操作日志相关接口。

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

## 第八周前端联调重点

1. 关闭 Mock 后核心页面不应静默读取本地假数据。
2. 答辩类型统一映射为后端字段：`预答辩 -> pre`、`正式答辩 -> formal`、`中期答辩 -> mid`。
3. 排期人工调整应优先提交后端，保存后刷新排期和冲突检测结果。
4. 规则配置与操作日志优先走 API；后端未实现时页面应给出明确提示。
5. 前端验收清单仅作为本地自测记录，不代表后端验收状态。
