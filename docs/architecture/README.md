# 架构入口

当前预答辩与正式答辩使用 policy 3，见[三阶段排期算法与优化](三阶段排期算法与优化.md)。[V2 架构升级说明](架构升级说明.md)保留旧版本边界和历史验证。开发边界见 [CONTRIBUTING.md](../../CONTRIBUTING.md)。

```mermaid
flowchart TD
    UI[Vue 页面与状态] --> HTTP[API 请求适配]
    HTTP --> DRF[Django 接口与权限]
    DRF --> Services[应用服务与输入适配]
    Services --> DB[模型与数据库事务]
    Services --> Algorithm[algorithm.py]
    Algorithm --> Domain[scheduling 领域规则]
    UI --> FrontDomain[前端领域转换与打印]
    FrontDomain --> Shared[shared 政策与配色]
    Domain --> Shared
    DRF --> Integrity[写一致性 revision 冻结 审计]
```

新增复杂业务优先放入 `api/services/`；算法领域保持独立于 ORM。`algorithm.py` 按规则版本分流，policy 3 三阶段流程位于 `scheduling/personnel_first.py`，硬约束校验位于 `scheduling/current.py`。旧 policy 1/2 继续使用原路径。

全局写锁与同步生成是现有一致性取舍；吞吐、任务队列和数据库切换需要依据容量测试另作决策。

## 架构决策记录

- [ADR-0001 分层与共享规则](adr/0001-分层与共享规则.md)

新增决策记录包含状态、背景、决定、后果和替代方案；PR 关联相关决定。现有历史文档保留原日期和版本，当前边界改变时同步更新本目录。
