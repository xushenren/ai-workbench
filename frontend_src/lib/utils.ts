import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** 合并 Tailwind 类名，解决冲突。 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** 千分位格式化 token 计数。 */
export function fmt(n: number): string {
  return n.toLocaleString("en-US");
}

/** 生成短随机 id（仅前端本地用，非安全用途）。 */
export function uid(prefix = ""): string {
  return prefix + Math.random().toString(36).slice(2, 10);
}
