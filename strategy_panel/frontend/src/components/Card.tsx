import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface CardProps {
  title?: string;
  en?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  delay?: number;
  pad?: boolean;
}

export default function Card({
  title,
  en,
  actions,
  children,
  className,
  bodyClassName,
  delay = 0,
  pad = true,
}: CardProps) {
  return (
    <section
      className={cn(
        "reveal card-hover rounded-xl border border-line bg-ink-800 shadow-card",
        className
      )}
      style={{ animationDelay: `${delay}ms` }}
    >
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          <div className="flex items-baseline gap-2.5 whitespace-nowrap">
            <span className="h-3.5 w-[3px] translate-y-[1px] rounded-full bg-accent" />
            <h2 className="text-sm font-semibold tracking-wide text-fg">{title}</h2>
            {en && (
              <span className="text-[10px] font-medium uppercase tracking-[0.2em] text-fg-mute">
                {en}
              </span>
            )}
          </div>
          {actions}
        </header>
      )}
      <div className={cn(pad && "p-5", bodyClassName)}>{children}</div>
    </section>
  );
}
