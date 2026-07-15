// ParserMappingPanel.tsx — 管理:文件类型↔解析器映射 + 入库限制/OCR 开关。仅管理员。
import { useEffect, useState } from "react";
import { Plus, Loader2 } from "lucide-react";
import { Card, Button, Badge } from "@/components/ui/primitives";
import { api } from "@/lib/api";

export function ParserMappingPanel() {
  const [maps, setMaps] = useState<any[]>([]);
  const [cfg, setCfg] = useState<any>({ max_files: 50, max_file_mb: 20, max_total_mb: 100, ocr_enabled: false, ocr_lang: "ch" });
  const [nf, setNf] = useState({ ext: "", external_cmd: "", note: "" });
  const [busy, setBusy] = useState(false);

  const refresh = () => api.listParsers().then(setMaps).catch(() => {});
  useEffect(() => { refresh(); api.getIngestConfig().then(setCfg).catch(() => {}); }, []);

  const addMap = async () => {
    if (!nf.ext.trim()) return;
    setBusy(true);
    try { await api.addParser({ ext: nf.ext.trim(), external_cmd: nf.external_cmd.trim(), note: nf.note.trim() }); setNf({ ext: "", external_cmd: "", note: "" }); refresh(); }
    finally { setBusy(false); }
  };
  const saveCfg = async () => { setBusy(true); try { await api.setIngestConfig(cfg); } finally { setBusy(false); } };

  return (
    <div className="space-y-5">
      <Card className="p-5">
        <div className="mb-3 text-sm font-medium">入库限制 / OCR</div>
        <div className="grid grid-cols-3 gap-3 text-sm">
          <L label="单次文件数"><input type="number" value={cfg.max_files} onChange={(e) => setCfg({ ...cfg, max_files: +e.target.value })} className={inp} /></L>
          <L label="单文件 MB"><input type="number" value={cfg.max_file_mb} onChange={(e) => setCfg({ ...cfg, max_file_mb: +e.target.value })} className={inp} /></L>
          <L label="单次总 MB"><input type="number" value={cfg.max_total_mb} onChange={(e) => setCfg({ ...cfg, max_total_mb: +e.target.value })} className={inp} /></L>
        </div>
        <div className="mt-3 flex items-center gap-4 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={cfg.ocr_enabled} onChange={(e) => setCfg({ ...cfg, ocr_enabled: e.target.checked })} /> 启用 OCR(扫描件/图片)</label>
          <span className="text-xs text-muted">本机紧张可关,迁服务器再开</span>
          <Button size="sm" onClick={saveCfg} disabled={busy} className="ml-auto">保存配置</Button>
        </div>
      </Card>

      <Card className="p-5">
        <div className="mb-3 text-sm font-medium">文件类型 ↔ 解析器映射</div>
        <div className="mb-3 flex flex-wrap gap-1.5">
          {maps.map((m) => (
            <Badge key={m.ext}>{m.ext} → {m.parser || m.external_cmd || "?"}</Badge>
          ))}
        </div>
        <div className="flex items-center gap-2 text-sm">
          <Plus size={15} className="text-accent" />
          <input value={nf.ext} onChange={(e) => setNf({ ...nf, ext: e.target.value })} placeholder=".dwg" className={`${inp} w-24`} />
          <input value={nf.external_cmd} onChange={(e) => setNf({ ...nf, external_cmd: e.target.value })} placeholder="外部命令 dwg2txt {input} {output}" className={inp} />
          <Button size="sm" onClick={addMap} disabled={busy}>{busy ? <Loader2 size={14} className="animate-spin" /> : "添加"}</Button>
        </div>
        <p className="mt-2 text-xs text-muted">专有格式(如 .dwg)指定外部解析工具即可支持,无需改代码;也可在后台用 md/excel 批量导入映射。</p>
      </Card>
    </div>
  );
}

function L({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><div className="mb-1 text-xs text-muted">{label}</div>{children}</div>;
}
const inp = "w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm";
