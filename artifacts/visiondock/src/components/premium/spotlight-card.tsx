import { useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/** 21st-style card with mouse-tracking spotlight border glow. */
export function SpotlightCard({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [hover, setHover] = useState(false);

  const onMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  return (
    <div
      ref={ref}
      onMouseMove={onMove}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className={cn(
        "group relative overflow-hidden rounded-2xl border border-border/50 bg-card/80 p-[1px] backdrop-blur-sm transition-shadow duration-500",
        "hover:shadow-xl hover:shadow-primary/10",
        className,
      )}
      style={{
        background: hover
          ? `radial-gradient(600px circle at ${pos.x}px ${pos.y}px, hsl(var(--primary) / 0.15), transparent 40%)`
          : undefined,
      }}
    >
      <div className="relative h-full rounded-[calc(1rem-1px)] bg-card/95 p-6">{children}</div>
    </div>
  );
}
