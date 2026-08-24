import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";

export function FancyEmpty({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      className="relative overflow-hidden rounded-2xl border border-dashed border-border/60 bg-gradient-to-b from-muted/30 to-card px-6 py-16 text-center"
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,hsl(var(--primary)/0.08),transparent_55%)]" />
      <motion.div
        animate={{ y: [0, -6, 0] }}
        transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
        className="relative mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10 text-primary shadow-lg shadow-primary/10"
      >
        <Icon className="h-8 w-8" />
      </motion.div>
      <h3 className="relative text-base font-semibold text-foreground">{title}</h3>
      {description && <p className="relative mt-2 text-sm text-muted-foreground">{description}</p>}
      {action && <div className="relative mt-6">{action}</div>}
    </motion.div>
  );
}
