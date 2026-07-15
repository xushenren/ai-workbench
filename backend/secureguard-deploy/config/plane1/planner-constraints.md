# planner-constraints.md  (Plane-1 · Refiner 可追加)

> Harness 层边界约束的载体。规划阶段必须满足的硬约束。
> 可追加，不可删改 Plane-0（红线/阶梯/护栏定义）。

## 默认约束
- 任何 R2 动作必须显式 ESCALATE，等人类批准，口头同意 ≠ 授权
- 速度永不能买安全：velocity 与 L0–L4 冲突时 velocity 必输
- 多规则冲突一律送 arbitrate，永不静默二选一
- 凭据仅经保险库，禁止任何形式明文落盘

## 进化追加区（Refiner append-only）
<!-- 新增约束写在此行以下 -->
