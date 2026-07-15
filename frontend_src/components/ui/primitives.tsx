// 轻量 UI 原语（shadcn 约定，本地实现，保证 npm install 后即可跑）。
import { forwardRef } from "react";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

/* ---------------- Button ---------------- */
type Variant = "primary" | "ghost" | "outline" | "subtle";
type Size = "sm" | "md" | "icon";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const variants: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-accent-hover shadow-soft",
  ghost: "text-text hover:bg-surface-2",
  outline: "border border-border text-text hover:bg-surface-2 bg-surface",
  subtle: "bg-surface-2 text-text hover:bg-border/60",
};
const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-sm",
  icon: "h-9 w-9 p-0",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-btn font-medium transition-colors",
        "disabled:opacity-50 disabled:pointer-events-none",
        variants[variant],
        sizes[size],
        className
      )}
      {...props}
    />
  )
);
Button.displayName = "Button";

/* ---------------- Card ---------------- */
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-card border border-border bg-surface shadow-soft", className)}
      {...props}
    />
  );
}

/* ---------------- Badge ---------------- */
export function Badge({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs text-muted",
        className
      )}
    >
      {children}
    </span>
  );
}

/* ---------------- Tabs (受控) ---------------- */
export function Tabs<T extends string>({
  tabs, value, onChange,
}: {
  tabs: { id: T; label: string }[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <div className="inline-flex items-center gap-1 rounded-btn bg-surface-2 p-1">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={cn(
            "rounded-md px-3 py-1.5 text-sm transition-colors",
            value === t.id ? "bg-surface text-text shadow-soft" : "text-muted hover:text-text"
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
