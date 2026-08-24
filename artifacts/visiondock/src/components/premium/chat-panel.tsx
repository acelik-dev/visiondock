import { useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Brain, Send, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type ChatBubble = {
  role: "user" | "assistant";
  content: string;
  images?: string[];
  timestamp?: Date;
};

function TypingIndicator() {
  return (
    <div className="flex gap-1">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="h-2 w-2 rounded-full bg-primary"
          animate={{ y: [0, -4, 0] }}
          transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.15 }}
        />
      ))}
    </div>
  );
}

export function PremiumChatPanel({
  messages,
  isLoading,
  loadingLabel = "Assistant is thinking…",
  empty,
  endRef,
}: {
  messages: ChatBubble[];
  isLoading?: boolean;
  loadingLabel?: string;
  empty?: React.ReactNode;
  endRef?: React.RefObject<HTMLDivElement | null>;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = scrollRef.current;
    if (!root) return;
    root.scrollTo({ top: root.scrollHeight, behavior: "smooth" });
  }, [messages, isLoading, endRef]);

  if (messages.length === 0 && empty) {
    return <div className="flex h-full flex-col">{empty}</div>;
  }

  return (
    <div ref={scrollRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-6">
      <AnimatePresence initial={false}>
        {messages.filter((msg) => Boolean(msg.content?.trim()) || (msg.images && msg.images.length > 0)).map((msg, idx) => (
          <motion.div
            key={idx}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}
          >
            <div className={cn("flex max-w-[85%] gap-3", msg.role === "user" && "flex-row-reverse")}>
              <div
                className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-full shadow-sm",
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-gradient-to-br from-primary to-violet-600 text-white",
                )}
              >
                {msg.role === "user" ? (
                  <span className="text-[10px] font-bold">You</span>
                ) : (
                  <Brain className="h-4 w-4" />
                )}
              </div>
              <div
                className={cn(
                  "rounded-2xl px-4 py-3 shadow-sm",
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "border border-border/50 bg-card/95 text-foreground backdrop-blur-sm",
                )}
              >
                {msg.images && msg.images.length > 0 && (
                  <div className="mb-2 flex gap-2">
                    {msg.images.map((img, i) => (
                      <img key={i} src={img} alt="" className="h-14 w-14 rounded-lg border border-border/40 object-cover" />
                    ))}
                  </div>
                )}
                {msg.content?.trim() ? (
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">{msg.content}</p>
                ) : null}
                {msg.timestamp && (
                  <p
                    className={cn(
                      "mt-2 text-[10px]",
                      msg.role === "user" ? "text-primary-foreground/60" : "text-muted-foreground",
                    )}
                  >
                    {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </p>
                )}
              </div>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>

      {isLoading && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-start">
          <div className="flex gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-primary to-violet-600">
              <Sparkles className="h-4 w-4 text-white" />
            </div>
            <div className="flex items-center gap-3 rounded-2xl border border-border/50 bg-card px-4 py-3 shadow-sm">
              <TypingIndicator />
              <span className="text-sm text-muted-foreground">{loadingLabel}</span>
            </div>
          </div>
        </motion.div>
      )}
      <div ref={endRef as React.RefObject<HTMLDivElement>} />
    </div>
  );
}

export function PremiumChatInput({
  value,
  onChange,
  onSend,
  disabled,
  placeholder,
  sendLabel = "Send",
  isLoading,
  extra,
  trailing,
  bare = false,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled?: boolean;
  placeholder?: string;
  sendLabel?: string;
  isLoading?: boolean;
  extra?: React.ReactNode;
  trailing?: React.ReactNode;
  bare?: boolean;
}) {
  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!disabled && value.trim()) onSend();
    }
  };

  return (
    <div className={bare ? "space-y-3" : "border-t border-border/50 bg-card/80 p-4 backdrop-blur-xl"}>
      {extra}
      <div className="flex min-w-0 items-end gap-2">
        <div className="relative min-w-0 flex-1">
          <textarea
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKey}
            disabled={disabled}
            placeholder={placeholder}
            rows={1}
            className="w-full resize-none rounded-xl border border-border/60 bg-muted/30 px-4 py-3 text-sm outline-none transition-all placeholder:text-muted-foreground focus:border-primary/50 focus:bg-card focus:ring-2 focus:ring-primary/15 disabled:opacity-50"
            style={{ minHeight: 48, maxHeight: 120 }}
          />
        </div>
        <Button
          onClick={onSend}
          disabled={disabled || !value.trim() || isLoading}
          aria-label={isLoading ? "Analyzing" : sendLabel}
          className="h-12 w-12 shrink-0 rounded-xl p-0 shadow-md shadow-primary/15"
        >
          {isLoading ? (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary-foreground/30 border-t-primary-foreground" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
        {trailing}
      </div>
    </div>
  );
}
