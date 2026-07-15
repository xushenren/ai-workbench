#!/bin/bash
# fix-migration.sh — 解码迁移中损坏的 base64 文件 + 修复配置
# 幂等安全：重复跑不会二次破坏

set -e
echo "============================================"
echo " AI Workbench — Migration Fix"
echo "============================================"

# ── 1. 解码所有 base64 文件 ──
echo ""
echo "═══ Step 1: Decoding base64 files ═══"

python3 -c "
import base64, os

repo = '.'
text_exts = {'.json', '.tsx', '.ts', '.jsx', '.js', '.md', '.yaml', '.yml',
             '.sh', '.html', '.css', '.txt', '.bak', '.bak2', '.bak3', '.bak5',
             '.bak-v090'}
decoded = 0
skipped = 0

for root, dirs, files in os.walk(repo):
    if '.git' in dirs:
        dirs.remove('.git')
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if ext not in text_exts and not f.endswith('.bak'):
            skipped += 1
            continue
        if f.endswith('.db') or f.endswith('.db-wal') or f.endswith('.db-shm'):
            skipped += 1
            continue
        
        path = os.path.join(root, f)
        try:
            with open(path, 'rb') as fh:
                raw = fh.read().strip()
            if not raw:
                continue
            try:
                decoded_bytes = base64.b64decode(raw, validate=True)
            except:
                continue
            
            # Check if decoded is readable text
            try:
                text = decoded_bytes.decode('utf-8')
            except UnicodeDecodeError:
                if decoded_bytes[:3] == b'\xef\xbb\xbf':
                    text = decoded_bytes[3:].decode('utf-8')
                else:
                    continue
            
            printable = sum(1 for c in text if c.isprintable() or c in '\n\r\t ')
            if len(text) <= 20 or printable / len(text) < 0.7:
                skipped += 1
                continue
            
            # Write decoded content
            # Strip any BOM from decoded output
            if text.startswith('\ufeff'):
                text = text[1:]
            # Convert .sh files to LF
            if f.endswith('.sh') or f.endswith('.bash'):
                text = text.replace('\r\n', '\n').replace('\r', '\n')
            
            rel = os.path.relpath(path, repo)
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(text)
            decoded += 1
            print(f'  ✅ {rel}')
        except Exception as e:
            print(f'  ❌ {rel}: {e}')

print(f'\nDecoded: {decoded}, Skipped (already text/binary): {skipped}')
"

# ── 2. 修复 devcontainer 配置 ──
echo ""
echo "═══ Step 2: Fixing devcontainer config ═══"

# Fix postCreateCommand path
python3 -c "
import json
with open('.devcontainer/devcontainer.json', 'r') as f:
    d = json.load(f)
old = d.get('postCreateCommand', '')
d['postCreateCommand'] = 'bash .devcontainer/setup.sh'
with open('.devcontainer/devcontainer.json', 'w') as f:
    json.dump(d, f, indent=2)
print(f'  postCreateCommand: {old} → bash .devcontainer/setup.sh')
"

# Fix setup.sh: pnpm → npm (pnpm-lock.yaml doesn't exist)
if grep -q 'pnpm install' .devcontainer/setup.sh; then
  sed -i 's/pnpm install/npm install/' .devcontainer/setup.sh
  echo '  setup.sh: pnpm install → npm install'
fi

# ── 3. 创建 .env.example ──
echo ""
echo "═══ Step 3: Creating .env.example ═══"

if [ ! -f .env ] && [ ! -f backend/secureguard-deploy/.env ]; then
  cat > .env << 'EOF'
# AI Workbench — 环境变量

# 模型后端（OpenAI 兼容 API）
# 生产部署时改为你的实际端点
MODEL_BASE_URL=https://api.deepseek.com/v1
MODEL_API_KEY=sk-your-key-here
MODEL_NAME=deepseek-chat

# 数据库路径（默认使用 data/ 目录下的 SQLite）
ORG_DB_PATH=backend/secureguard-deploy/data/org_core.db
KB_DB_PATH=backend/secureguard-deploy/data/kb_vectors.db
SESSIONS_DB_PATH=backend/secureguard-deploy/data/sessions.db
EOF
  echo '  ✅ Created .env.example (copy to .env and fill in your keys)'
else
  echo '  ⏭️  .env already exists'
fi

# ── 4. Git 清理建议 ──
echo ""
echo "═══ Step 4: Git cleanup (suggested) ═══"

echo ""
echo "  ⚠️  Unwanted files tracked in git:"
git ls-files data/ backup_20260622/ .env 2>/dev/null || true
echo ""
echo "  To remove them:"
echo "    git rm -r --cached data/ backup_20260622/"
echo "    git rm -r --cached backend/secureguard-deploy/data/"
echo "    echo '.env' >> .gitignore"
echo "    git add .gitignore"
echo "    git commit -m 'chore: cleanup tracked artifacts'"

# ── 5. 验收集成挂载 ├─
echo ""
echo "═══ Step 5: Verify shangan_integration mount ═══"

if grep -q 'shangan_integration\|shangan' backend/secureguard-deploy/backend/app.py 2>/dev/null; then
  echo '  ✅ shangan_integration 已挂载'
  grep -n 'shangan' backend/secureguard-deploy/backend/app.py 2>/dev/null
else
  echo '  ⚠️  shangan_integration 未挂载到 app.py'
fi

# ── 6. 验证 npm setup ──
echo ""
echo "═══ Step 6: Verify npm setup ═══"

if [ -f frontend_src/package.json ]; then
  npm_pkg=$(python3 -c "
import json
d = json.load(open('frontend_src/package.json'))
s = d.get('scripts', {})
print(f'  Scripts: {json.dumps(s, indent=4)}')
print(f'  Dependencies: {len(d.get(\"dependencies\", {}))}')
print(f'  DevDependencies: {len(d.get(\"devDependencies\", {}))}')
" 2>/dev/null)
  echo "$npm_pkg"
else
  echo '  ❌ frontend_src/package.json not found!'
fi

echo ""
echo "============================================"
echo " ✅ Fix complete! Commit and push:"
echo "============================================"
echo ""
echo "  git add -A"
echo "  git commit -m 'fix: decode base64 files, fix devcontainer setup'"
echo "  git push"
echo ""

# Also show current state for verification
echo "═══ Quick verification ═══"
head -3 frontend_src/App.tsx 2>/dev/null
echo "..."
head -3 .devcontainer/devcontainer.json 2>/dev/null
echo "..."
head -3 frontend_src/vite.config.ts 2>/dev/null
