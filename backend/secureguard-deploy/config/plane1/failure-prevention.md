# failure-prevention.md  (Plane-1 · Refiner 可追加)

> Loop 层预防规则的载体。由历史失败（C/D 类）反向提炼的“下次别再犯”。
> 自省触发器库（§3）的扩展素材来源于此。

## 默认预防规则
- 出现“这个测试明显没问题，先 skip”内部独白 → BLOCK（L4 正确性门）
- 出现“先 --force / --no-verify 压下去” → BLOCK（绕过门信号）
- 出现“先 hardcode 这个 key” → BLOCK（R-07）
- 出现“staging 应该和 prod 一样” → ASK（强制核对）

## 进化追加区（Refiner append-only）
<!-- 新增预防规则写在此行以下，注明触发它的失败用例 -->
