# context-gap-checklist.md  (Plane-1 · Refiner 可追加)

> C2 缺口检查项的载体。命中任一项 → gate 返回 ASK，向人类补全后从本门重入。
> 本文件可由进化流程追加新项（走 L3 五道门 + git），但不得删改 Plane-0。

## 默认缺口项
- [ ] 目标环境未指明（prod / staging / dev）
- [ ] 端口 / 超时 / 区域等关键配置使用了“默认值假设”
- [ ] 数据来源缺少 provenance（§2.2 血缘门）
- [ ] 不可逆操作缺少“已确认”标记
- [ ] 缺少回滚方案 / 已测逆向脚本
- [ ] staging 与 prod 配置一致性未核对

## 进化追加区（Refiner append-only）
<!-- 新增缺口项写在此行以下，每项注明来源失败用例 id -->
