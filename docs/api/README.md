# 当前 API 契约与变更约定

统一前缀 `/api/`。路由来源为 `api/urls.py`、`api/views.py` 和 `api/schedule_views.py`；前端适配在 `src/api/`，字段映射在 `api/serializers.py`。本文件描述跨端共同约定，详细字段以对应请求适配、Serializer 和测试共同核对。

## 认证与权限

`POST /api/auth/login/` 提交 `username`、`password`，成功返回 `data.token`、`data.username`、`data.isAdmin`。后续 API 使用：

```http
Authorization: Token <登录取得的 token>
```

API 使用服务端 Token 认证，默认有效期为 12 小时（可由配置调整）。退出调用 `POST /api/auth/logout/` 撤销 Token；修改密码调用 `POST /api/auth/change-password/`。Django 管理后台独立使用后台登录流程。

基础数据读取要求登录，受限写操作要求管理员；普通用户的排期读取只展示发布结果。权限以对应 View 和 `api/permissions.py` 为准，接口变更必须验证允许与拒绝两条路径。

## 响应、错误和字段

普通 JSON 成功响应：

```json
{"success": true, "data": {}, "message": "ok"}
```

普通 JSON 失败响应保留 HTTP 错误状态，`success=false`，`data` 保留原始字段或导入错误详情，`message` 提供提示。已构造的响应壳按实现保留。导出接口返回文件，不套 JSON 壳。

前端统一通过 `src/api/request.ts` 解包和处理 401，业务页面不重复实现认证与响应解包。

- 页面内部答辩类型使用中文，请求 `defense_type` 为 `pre`／`formal`／`mid`。
- API 命令字段遵守现有契约，如 `version_id`、`group_id`、`group_data`、`expected_revision`；资源字段通过 Serializer 映射，不全局强制改变命名。
- 日期、时段、教师关系字段的格式、空值和兼容输入参见对应 Serializer、时间服务和[架构说明](../architecture/架构升级说明.md)。

## 主要路由

下表为模块入口；资源详情更新与删除使用 `/资源/{id}/`，集合动作保持当前路由拼写。

| 模块 | 路由或动作 |
| --- | --- |
| 教师 | `/teachers/`、`import_data/`、`batch_delete/`、`import_timetable/` |
| 学生 | `/students/`、`import_data/`、`batch_delete/` |
| 教室 | `/rooms/`、`import_data/`、`batch_delete/` |
| 规则 | `/rule-config/`，按 `defense_type` 读取和保存 |
| 生成 | `POST /schedule/generate/`、`POST /schedule/generate-linked/` |
| 读取 | `GET /schedule/current/`、`GET /schedule/versions/` |
| 编辑 | `POST /schedule/adjust/`、`POST /schedule/adjust-group/` |
| 重验 | `POST /schedule/check-conflicts/` |
| 发布 | `POST /schedule/publish/` |
| 导出 | `GET /schedule/export-excel/`、`GET /schedule/export_word/` |
| 日志 | `/operation-logs/`，查询、上报及受权限限制的清空 |

## 排期写入保护

- 新生成请求提供 `request_key`，重复键的重试遵守幂等语义；同键不同规则返回冲突。联合生成的来源、日期与原子性见架构说明。
- 编辑请求携带当前版本的 `expected_revision`。旧 revision 返回 409；手调缺少 revision 返回 428，并回滚操作。发布缺少或不匹配 revision 按发布接口当前实现返回 409。
- `version_id` 标识排期版本实体，`revision` 表示该版本的修改序号，不能互换。
- 已发布、已归档或跨版本编辑受到保护；出现 409 应刷新并重新确认修改，不能盲目覆盖或自动循环重试。
- 发布时重验，仍有错误级冲突或空排期时拒绝发布。草稿和历史版本的读取、导出都必须确认所选版本。

发布请求示例（ID 和 revision 必须取自当前读取结果）：

```json
{"version_id": 42, "expected_revision": 3}
```

## 接口变更清单

1. 在任务／PR 写出 URL、方法、字段类型、必填与空值、成功与错误响应、权限和兼容策略。
2. 前端、后端负责人确认后实现，同步类型、Serializer、适配、Mock 和本文档。
3. 校验正常输入、错误输入、权限、版本冲突和真实后端流程。
4. 若业务意图改变，同步[需求规则](../requirements/业务规则与验收.md)；若涉及模型则提交并验证迁移。

旧的前端领先阶段接口清单见[归档](../archive/README.md)，其中待实现描述和部分约定只适用于当时阶段。
