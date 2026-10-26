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
| 学生 | `/students/`、`import_data/`、`import-cohort/`、`batch-defense-types/`、`batch_delete/` |
| 教室 | `/rooms/`、`import_data/`、`batch_delete/` |
| 规则 | `/rule-config/`，按 `defense_type` 读取和保存 |
| 生成 | `POST /schedule/generate/`、`POST /schedule/generate-linked/` |
| 生成前预检 | `POST /schedule/preflight/`，管理员提交 `{"rules": {...}}`，返回 `canGenerate`、`errors`、`warnings`、`stats`；不创建版本或写审计 |
| 读取 | `GET /schedule/current/`、`GET /schedule/versions/` |
| 编辑 | `POST /schedule/adjust/`、`POST /schedule/adjust-group/` |
| 重验 | `POST /schedule/check-conflicts/` |
| 发布 | `POST /schedule/publish/` |
| 导出 | `GET /schedule/export-excel/`、`GET /schedule/export_word/` |
| 日志 | `/operation-logs/`，查询、上报及受权限限制的清空 |

## 基础资料导入与预览

教师、学生、教室的 `POST /api/{teachers|students|rooms}/import_data/` 使用管理员认证和 `multipart/form-data`。课表导入仍走独立的 `import_timetable/`，不要混用两类参数。

| 字段 | 含义 |
| --- | --- |
| `file` | 必填，CSV 或受支持的 Excel 文件 |
| `preview` | 字符串 `true` 为仅检查预览；确认导入传 `false` |
| `campus` | 教室导入可选，仅补充源文件缺失的校区（创新港／兴庆），不覆盖已有值；其他资料须在源文件提供校区 |
| `importYear` | 可选，1900～2100 四位年份，仅补充缺少年份的日期，不改写完整日期 |
| `sheetName` | 可选，Excel 工作表名；预览返回工作表列表，不指定时使用默认表 |
| `defenseTypes` | 学生普通导入可选，JSON 数组（预答辩／正式答辩／中期答辩），仅补充文件及文件名均未注明的参与环节；不替换原表环节，与已有学生环节合并 |

预览成功解析后以 HTTP 200 返回数据对象，外层遵守统一响应壳：`preview=true`、`canImport`、`rows`、`validCount`、`invalidCount`、`errors`、`warnings`、`sheets`、`sheetName`。每条 `rows` 包含 `row`、`sheet`、`sourceRows`、`originalTime`、`normalizedTime`、`values`。`canImport=false` 表示检查未通过，不能仅按 HTTP 200 启用确认；文件本身不可读等请求错误仍返回错误状态。

预览不保存业务对象、不写审计日志。正式确认重新上传文件和参数，后端重新校验；有错误 HTTP 400 整批回滚，错误详情保留来源行。前端在文件、工作表、校区或年份变化后使旧预览失效；预览不是可绕过校验的授权凭据。日期范围按每天相同时段展开，上限 366 天；无效时刻和部分缺失的日期／时间必须修正，不能退化为全天。

学生文件的“参与答辩类型／参与环节”支持合法 JSON 数组或顿号、逗号等分隔文本，解析后只允许预答辩、正式答辩、中期答辩并去重；格式错误或未知环节整批拒绝。直接学生 JSON API 的 `defenseTypes` 必须为合法环节数组。文件已有环节优先，不被补充参数覆盖；与已有合法环节合并，明确不参排备注仍优先。

带选项的地点表头（例如“中期答辩地点（创新港/兴庆）”）支持中英文括号、空格和校区选项顺序，预览与保存均保留识别出的校区。同一文件识别出多个校区／地点列时返回 HTTP 400，要求保留本次使用的一列，不按列顺序静默取值。类型定义见 `src/types/import.ts`，请求封装见 `src/api/import.ts`；本轮修复见[交付缺陷修复](../releases/交付缺陷修复-2026-10-26.md)。混合线上地点和同一教室跨批追加仍须按既有范围核对，不能据此认定已支持。

## 学生与导师联合批量导入

学生已录入不等于参加当前环节。工作台和向导同时展示总人数、当前环节人数，区分未导入、未设置环节、仅参加其他环节；切换显示类型不修改学生资料。

学生读取响应增加只读 `participationExcluded`：参与环节为空且备注为明确不参排原因时为 `true`。此类学生计入资料总人数，但不计入当前参排或“未设置环节”人数。允许校区为空，不产生缺参与类型的排期提示；单纯校区空白不能判断不参排。

普通导入和联合导入均优先识别完整备注声明：休学、转博、已转博、已毕业、退学、外院答辩（可带学院说明）、不参加答辩等。识别后保留备注、清空 `defenseTypes`，覆盖之前错误的参与环节；不会用统一校区参数或逐行修正给不参排者补校区。“未转博”“申请休学待审批”等不明确或否定表达不会自动排除。普通导入的文件／文件名／请求参数环节补充及旧值合并仅适用于未识别为不参排的行。

`POST /api/students/batch-defense-types/` 仅管理员，JSON `{"ids":[1,2],"defenseTypes":["正式答辩"]}`。ids 为 1～1000 个正整数，环节为非空合法数组；任一学生不存在或参数无效 HTTP 400，整批回滚。成功返回 `message`、`count`，只追加所选环节，保留原环节、导师及其他字段，并按基础资料修改机制记审计、使草稿 revision 失效。该动作不修改发布快照。

所选学生包含明确不参排备注时，该批次同样 HTTP 400、整批不写入。恢复参加须先核对并更正备注、校区，再设置参与环节。

`POST /api/students/import-cohort/`，仅管理员，`multipart/form-data`：

| 字段 | 含义 |
| --- | --- |
| `teacherFile` | 必填，一份软件学院教师名单，含姓名及可选职称、指定角色 |
| `studentFiles` | 必填，重复字段上传 1～10 份学生名册，须有学号、姓名、导师表头 |
| `defenseTypes` | 必填，JSON 数组，明确选取预答辩／正式答辩／中期答辩，不从文件名推断 |
| `preview` | `true` 仅预览；`false` 重新校验并确认 |
| `campus` | 可选，仅补充空白校区，创新港／兴庆 |
| `teacherSheet` / `studentSheets` | 可选，教师工作表名／学生文件下标到工作表名的 JSON 对象 |
| `corrections` | 可选，JSON 对象：预览行 `key` → `{"campus":"兴庆"}`，仅支持校区修正；文件或工作表变化后旧 key 被拒绝 |

支持 XLSX、XLS、CSV；每份 5 MB、本批合计 20 MB，每表 1000 行、学生合计 3000 行。预览返回 `preview`、`canImport`、`stats`、`files`、`teachers`、`students`、`errors`、`warnings`；行包含 `key`、`sources`（文件／工作表／原始行）、`action`（create/update/keep）。预览无业务、审计、草稿 revision 或写锁 revision 变更。解析成功但不合格仍 HTTP 200 且 `canImport=false`；确认有错误 HTTP 400，整批回滚。成功确认返回 `message`、`stats`、`warnings`，记录汇总审计。

预览另返回 `excludedStudents`，结构同学生行并保留原始 `remark`、来源和操作；`students` 只包含参排学生。`stats.totalStudents` 为去重后的总资料人数，`stats.students` 为参排人数，`stats.excludedStudents` 为不参排人数，前者等于后两者之和。不参排者仍写入学生资料，但不要求补齐导师和校区，也不会仅因其导师姓名而新建外院专家。当前真实批次应为316份资料、301位参排、15位不参排，43位软件学院教师加68位参排学生所需外院导师。

教师按姓名关联，学生按学号关联；同学号内容相同合并来源，冲突拒绝。软件学院名单保留明确角色；名单外导师补入为 `isExternal=true`、`isSoftwareTeacher=false`、`expertOnly=true`、`roles=["普通专家"]`，缺失职称为“外院导师（职称待确认）”，已有职称、停用状态、不可用时间保留。教师资源增加 `expertOnly` 布尔字段；为真时 Serializer 拒绝其他角色，算法输入与资格校验也拒绝主席／组长／秘书。旧记录迁移默认 false，旧外院教师不被整体改写。

## 排期写入保护

- 新生成请求提供 `request_key`，重复键的重试遵守幂等语义；同键不同规则返回冲突。正式答辩随机种子保存到规则快照，响应提供 `randomSeed`；未指定种子的重试复用原方案，改变显式 `random_seed` 必须使用新请求键。联合生成的来源、日期与原子性见架构说明。
- 编辑请求携带当前版本的 `expected_revision`。旧 revision 返回 409；手调缺少 revision 返回 428，并回滚操作。发布缺少或不匹配 revision 按发布接口当前实现返回 409。
- `version_id` 标识排期版本实体，`revision` 表示该版本的修改序号，不能互换。
- 已发布、已归档或跨版本编辑受到保护；出现 409 应刷新并重新确认修改，不能盲目覆盖或自动循环重试。
- 发布时重验，仍有错误级冲突或空排期时拒绝发布。草稿和历史版本的读取、导出都必须确认所选版本。
- 缺失、停用或不适用于本类型的导师资料在生成前阻止创建版本；预检通过不替代生成时重新检查。2026-10-19 整合版在导出 Excel／Word／PDF 前复核硬冲突，有错误 HTTP 400 拒绝；无硬冲突草稿可导出，历史版本使用所选快照。

学生列表支持 `defense_type=pre|formal|mid` 及可选 `version_id`，返回只读 `currentGroup`。指定版本须属于所选类型且有查看权限；普通用户只使用可查看的已发布版本。操作日志增加只读 `details` 和 `authoritative`，客户端不能伪造服务端权威记录。

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
