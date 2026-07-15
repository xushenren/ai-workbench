# kb_core — 知识库三池 + 置信晋升

建在 org_core 之上(复用其鉴权与审计)。落地了逐轮敲定的设计。

## 三池
私有(仅本人) / 公有低置信(用户同意共享) / 公有高置信(专家拍板入库)

## 链路(已自测 14/14)
- 普通用户上传 → 私有;同意共享 → 公有低置信
- 专家(can_promote_kb)晋升 → AI 体检(claim 级,非余弦)→ 专家拍板(可推翻AI·留痕)→ 公有高置信
- 检索按身份过滤:本人私有 + 全部公有;匿名/外部只见 external_ok 的高置信
- 答复置信标注(高/低 + 风险提示);全程审计 + 一键回滚

## 关键点
- AI 是副手不是法官:只产出冲突/异常报告,不自动封人、不定真伪;专家可推翻,留痕。
- 置信由"专家背书"定,不由群体投票。私有不评级。
- external_ok 独立于内部 public,专门控制"对外可公开"(供匿名 bot)。

## 用法
```python
from org_core import SqliteRepos
from kb_core import KBService, SqliteKBRepo
kb = KBService(SqliteRepos("org.db"), SqliteKBRepo("kb.db"),
               model_inspector=None)  # 生产可传走网关的强体检
kb.upload(T, grant_id, title=..., content=..., share=False)
entry, report = kb.promote_to_high(T, expert_grant, title=..., claims={...},
                                   decision_override=False)  # 冲突时 True 拍板
hits = kb.retrieve(T, current_grant_id, "查询")   # None=匿名
```
依赖:org_core(同仓)。
