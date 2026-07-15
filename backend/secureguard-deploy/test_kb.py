"""自测:三池 + AI体检 + 专家拍板 + 身份过滤检索 + 回滚。可直接 python 运行。"""
import sys
sys.path.insert(0, ".")

from org_core import (
    OrgService, SqliteRepos, NodeType, User, UserKind, UserStatus, Role,
    DEFAULT_ROLE_TEMPLATES, PermissionDenied,
)
import uuid
from org_core import OrgNode
from kb_core import (
    KBService, SqliteKBRepo, KBEntry, Pool, KBConflict, annotate_sources, confidence_label,
)

ok = 0; fail = 0
def ck(name, cond):
    global ok, fail; print(("✓ " if cond else "✗ ") + name); ok += cond; fail += (not cond)

# --- 组织 + 两个人:专家(can_promote_kb) 与 普通成员 ---
org = SqliteRepos(":memory:")
svc_org = OrgService(org)
t, root = svc_org.bootstrap_tenant("示范建工", "集团")
T = t.id
proj = OrgNode(uuid.uuid4().hex, T, root.id, NodeType.PROJECT, "项目部A")
org.add_node(proj)

admin_role = Role(uuid.uuid4().hex, T, "组织管理员", DEFAULT_ROLE_TEMPLATES["组织管理员"])
admin = User(uuid.uuid4().hex, T, UserKind.INTERNAL, UserStatus.ACTIVE, "管理员")
g_admin, _ = svc_org.seed_admin(T, user=admin, role=admin_role, node_id=root.id)

expert_role = Role(uuid.uuid4().hex, T, "专家/总工", DEFAULT_ROLE_TEMPLATES["专家/总工"]); org.add_role(expert_role)
member_role = Role(uuid.uuid4().hex, T, "成员", DEFAULT_ROLE_TEMPLATES["成员"]); org.add_role(member_role)

expert = svc_org.add_user(T, g_admin.id, home_node_id=proj.id, display_name="张总工")
g_expert = svc_org.grant_role(T, g_admin.id, user_id=expert.id, role_id=expert_role.id, org_node_id=proj.id, label="张总工@A")
member = svc_org.add_user(T, g_admin.id, home_node_id=proj.id, display_name="小王")
g_member = svc_org.grant_role(T, g_admin.id, user_id=member.id, role_id=member_role.id, org_node_id=proj.id, label="小王@A")

kb = KBService(org, SqliteKBRepo(":memory:"))

# ===== 普通用户上传 → 默认私有 =====
e1 = kb.upload(T, g_member.id, title="我的现场笔记", content="A区回填注意事项", claims={"回填压实度": "0.95"})
ck("普通用户上传默认进私有池", e1.pool == Pool.PRIVATE)

# ===== 同意共享 → 公有低置信 =====
e2 = kb.upload(T, g_member.id, title="临时支模经验", content="高支模要点", share=True)
ck("同意共享进公有低置信池", e2.pool == Pool.PUBLIC_LOW)

# ===== 普通成员无权晋升高置信 =====
try:
    kb.promote_to_high(T, g_member.id, title="规范X", content="...", claims={"强度": "C30"})
    ck("普通成员不能晋升高置信", False)
except PermissionError:
    ck("普通成员被拒(无 can_promote_kb)", True)

# ===== 专家晋升 → AI体检无冲突 → 入高置信 =====
e3, rep3 = kb.promote_to_high(T, g_expert.id, title="混凝土强度标准", content="基础C30",
                              claims={"基础混凝土强度": "C30"}, external_ok=True)
ck("专家晋升进高置信池", e3.pool == Pool.PUBLIC_HIGH and not rep3.has_conflict)

# ===== AI体检命中冲突(同键不同值)→ 阻断,需拍板 =====
try:
    kb.promote_to_high(T, g_expert.id, title="强度修正", content="基础C35",
                       claims={"基础混凝土强度": "C35"})
    ck("冲突应被AI体检阻断", False)
except KBConflict as e:
    ck("AI体检发现claim冲突并阻断", e.inspection.has_conflict)

# ===== 专家拍板推翻AI → 入库且留痕 =====
e4, rep4 = kb.promote_to_high(T, g_expert.id, title="强度修正", content="现场实测改 C35",
                              claims={"基础混凝土强度": "C35"}, decision_override=True)
ck("专家可推翻AI入库", e4.pool == Pool.PUBLIC_HIGH)
ck("推翻AI有留痕", "专家推翻AI" in e4.ai_verdict)

# ===== 身份过滤检索 =====
# 小王检索:看得到自己的私有 + 公有
r_member = kb.retrieve(T, g_member.id, "")
ck("成员能看到自己的私有条目", any(x.id == e1.id for x in r_member))
# 专家检索:看不到小王的私有(按 owner 隔离)
r_expert = kb.retrieve(T, g_expert.id, "")
ck("专家看不到他人私有(在A看不到他人私有)", not any(x.id == e1.id for x in r_expert))
ck("专家能看到公有低/高", any(x.id == e2.id for x in r_expert) and any(x.id == e3.id for x in r_expert))
# 匿名/外部:只见 external_ok 的高置信
r_anon = kb.retrieve(T, None, "")
ck("匿名只见 external_ok 的高置信", all(x.pool == Pool.PUBLIC_HIGH and x.external_ok for x in r_anon))
ck("匿名看不到私有/低置信", not any(x.pool != Pool.PUBLIC_HIGH for x in r_anon))

# ===== 答复置信标注 =====
ann = annotate_sources(r_expert)
ck("答复能分高/低置信并给风险提示", "high" in ann and (ann["risk_hint"] != "" if ann["low"] else True))

# ===== 回滚 =====
kb.rollback(T, g_expert.id, e4.id)
r_after = kb.retrieve(T, g_expert.id, "")
ck("高置信条目回滚后不再可见", not any(x.id == e4.id for x in r_after))

print(f"\n结果:{ok} 通过 / {fail} 失败")
sys.exit(1 if fail else 0)
