import { STATE_COLORS, STATE_LABELS } from "@/lib/colors";
import type { StateColor } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Props {
  color: StateColor;
  label?: string;
  showDot?: boolean;
  className?: string;
}

// תווית צבעונית עם נקודה — שפה ויזואלית עקבית בכל המערכת.
export function StateBadge({ color, label, showDot = true, className }: Props) {
  const cls = STATE_COLORS[color];
  const text = label ?? STATE_LABELS[color];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border",
        cls.badge,
        className,
      )}
    >
      {showDot && (
        <span
          className={cn("inline-block w-1.5 h-1.5 rounded-full", cls.dot)}
          aria-hidden
        />
      )}
      {text}
    </span>
  );
}

export function StateDot({ color, className }: { color: StateColor; className?: string }) {
  return (
    <span
      className={cn(
        "inline-block w-2 h-2 rounded-full",
        STATE_COLORS[color].dot,
        className,
      )}
      aria-hidden
    />
  );
}
