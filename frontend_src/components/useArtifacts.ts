// useArtifacts.ts — 从 /v2 响应里取出 artifacts，喂给 ArtifactPanel。
// /v2 实际字段为 x_shangan_artifacts（老名）。把它单独抽成 hook，
// 这样 ChatView 只需两行就能接上，互不污染。

import { useState, useCallback } from "react";

export interface Artifact {
  id: string;
  type: string;        // code | table | markdown | calc | mermaid | ...
  title: string;
  lang?: string;
  content: string;
}

/** 从一条 /v2 chat 响应里读 artifacts（兼容缺字段 / 老字段名）。 */
export function extractArtifacts(resp: any): Artifact[] {
  const raw = resp?.x_shangan_artifacts ?? resp?.x_platform_artifacts ?? [];
  return Array.isArray(raw) ? (raw as Artifact[]) : [];
}

/** ChatView 里用：拿到响应后调用 setFromResponse(resp) 即可驱动面板。 */
export function useArtifacts() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const setFromResponse = useCallback((resp: any) => {
    const arts = extractArtifacts(resp);
    if (arts.length) setArtifacts(arts);   // 只有这条消息真有 artifact 才更新，保留上一条
  }, []);
  const clear = useCallback(() => setArtifacts([]), []);
  return { artifacts, setFromResponse, clear };
}
