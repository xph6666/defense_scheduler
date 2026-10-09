# 文档与项目结构

当前工作从 [STATUS.md](../STATUS.md) 开始，开发流程见 [CONTRIBUTING.md](../CONTRIBUTING.md)，安装启动见 [README.md](../README.md)。

## 当前文档

| 类别 | 入口 | 用途 |
| --- | --- | --- |
| 需求 | [需求管理](requirements/README.md) | 当前 PRD、需求缺口与待决策 |
| 规则 | [业务规则与验收](requirements/业务规则与验收.md) | 关键约束、实现位置和验证入口 |
| 架构 | [架构索引](architecture/README.md) | 分层、模块职责与决策 |
| 接口 | [API 契约](api/README.md) | 认证、字段、排期版本保护与变更流程 |
| 开发环境 | [新人上手](guides/开发环境与新人上手.md) | 首次启动和首个任务 |
| 使用 | [WIKI](../WIKI.md)、[教师快速上手](guides/教师快速上手.md)、[向导与日程](guides/分步向导与日程视图说明.md) | 用户操作和输入输出 |
| 验证 | [测试与发布](guides/测试与发布.md) | 日常检查、发布前验证 |
| 运维 | [稳定性与运维](guides/稳定性升级与运维说明.md) | 备份、迁移和部署 |
| 仓库 | [仓库设置](guides/仓库设置.md) | 管理员配置协作和分支保护 |
| 发布 | [v2026.10.02](releases/发布说明-v2026.10.02.md)、[本轮治理整理](releases/工程治理整理-2026-10-09.md) | 版本和验证记录 |
| 历史 | [归档索引](archive/README.md) | 旧需求、阶段约定和分析报告 |

## 代码与资源目录

| 路径 | 用途 |
| --- | --- |
| `src/`、`public/` | Vue 前端代码与静态资源 |
| `api/` | Django API、模型、应用服务、迁移和后端测试 |
| `defense_scheduler/` | Django 配置、运行初始化、服务和运维测试 |
| `algorithm.py`、`scheduling/` | 算法入口与纯领域规则 |
| `shared/` | 共同政策和配色数据，参与打包 |
| `scripts/` | 启动、验证、打包脚本 |
| `tests/fixtures/` | 共享的 Excel 测试样例；见[样例说明](../tests/fixtures/README.md) |
| `.github/` | CI、Issue 与 PR 模板 |
| `WIKI/` | 课程提交证据、截图和复现脚本；保持原路径，内容按原日期理解 |
| `main.py`、`manage.py`、`desktop_launcher.py`、`DefenseScheduler.spec` | 现有启动与打包入口，保持原位置 |

## 本地目录与归档边界

`app-data/`、`backups/`、`logs/`、`.tmp/`、`db.sqlite3`、`.env`、`.venv/`、`node_modules/`、`dist/`、`build/`、`release/` 属于本地运行、验证、依赖或生成产物，按 `.gitignore` 保持本地。

`排答辩文档/` 是本地参考资料，部分可选测试按原路径读取；本轮保留路径，不上传真实业务资料。旧的 `开发文档/` 和 `开发文档V2/` 文件已按用途归类，路径对照见归档索引。

文件移动需先确认引用和运行依赖，再更新链接、脚本或打包配置。历史标签中的旧路径保持原样，外部链接仍可定位对应版本。
