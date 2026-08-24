import { useCallback, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ImagePlus, Upload, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type ImageUploadZoneProps = {
  images: string[];
  required: number;
  onAdd: (files: FileList) => void;
  onRemove: (index: number) => void;
  onBrowse?: () => void;
  disabled?: boolean;
  className?: string;
};

export function ImageUploadZone({
  images,
  required,
  onAdd,
  onRemove,
  onBrowse,
  disabled,
  className,
}: ImageUploadZoneProps) {
  const [dragOver, setDragOver] = useState(false);
  const complete = images.length >= required;

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (disabled || complete || !e.dataTransfer.files?.length) return;
      onAdd(e.dataTransfer.files);
    },
    [disabled, complete, onAdd],
  );

  return (
    <div className={cn("space-y-4", className)}>
      <motion.div
        role="button"
        tabIndex={0}
        onClick={() => !disabled && !complete && onBrowse?.()}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && !disabled && !complete) onBrowse?.();
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled && !complete) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        animate={{
          borderColor: dragOver ? "hsl(var(--primary))" : "hsl(var(--border))",
          scale: dragOver ? 1.01 : 1,
        }}
        className={cn(
          "relative overflow-hidden rounded-2xl border-2 border-dashed p-8 text-center transition-colors",
          dragOver ? "bg-primary/5" : "bg-muted/20",
          disabled && "opacity-50 pointer-events-none",
        )}
      >
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,hsl(var(--primary)/0.06),transparent_70%)]" />
        <div className="relative">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            {dragOver ? <Upload className="h-7 w-7" /> : <ImagePlus className="h-7 w-7" />}
          </div>
          <p className="text-sm font-medium text-foreground">
            {complete ? "All samples uploaded" : "Drop images here or click to browse"}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {images.length}/{required} required · JPG, PNG, WebP
          </p>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-muted">
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-primary to-violet-500"
              initial={{ width: 0 }}
              animate={{ width: `${Math.min(100, (images.length / required) * 100)}%` }}
              transition={{ type: "spring", stiffness: 120, damping: 20 }}
            />
          </div>
        </div>
      </motion.div>

      <AnimatePresence>
        {images.length > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            className="flex flex-wrap gap-2"
          >
            {images.map((src, idx) => (
              <motion.div
                key={`${src.slice(-24)}-${idx}`}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                className="group relative"
              >
                <img
                  src={src}
                  alt=""
                  className="h-16 w-16 rounded-xl border border-border/60 object-cover shadow-sm"
                />
                <button
                  type="button"
                  onClick={() => onRemove(idx)}
                  className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-destructive text-destructive-foreground opacity-0 shadow transition-opacity group-hover:opacity-100"
                >
                  <X className="h-3 w-3" />
                </button>
              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function ImageUploadTrigger({
  onClick,
  count,
  required,
  complete,
}: {
  onClick: () => void;
  count: number;
  required: number;
  complete: boolean;
}) {
  if (count === 0) {
    return (
      <Button type="button" variant="outline" onClick={onClick} className="gap-2 border-primary/30 bg-primary/5">
        <ImagePlus className="h-4 w-4" />
        Upload samples ({required})
      </Button>
    );
  }
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={complete}
      className="flex items-center gap-2 rounded-full border border-primary/25 bg-primary/8 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/12 disabled:opacity-60"
    >
      <span className={complete ? "text-emerald-600" : ""}>
        {count}/{required}
        {complete && " ✓"}
      </span>
      {!complete && <ImagePlus className="h-3.5 w-3.5" />}
    </button>
  );
}
