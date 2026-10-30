import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { FaceSmileIcon } from "@heroicons/react/24/outline";
import api from "../../utils/axios";
import { apiError, cx } from "../../utils/helpers";
import { REACTIONS } from "../../utils/board";

const META = Object.fromEntries(REACTIONS.map((r) => [r.kind, r]));

/** The reactions after the viewer toggles `kind`, kept in REACTIONS order. */
const toggled = (reactions, kind) => {
  const current = reactions.find((r) => r.kind === kind);
  const next = current
    ? reactions
        .map((r) => (r.kind === kind ? { ...r, mine: !r.mine, count: r.count + (r.mine ? -1 : 1) } : r))
        .filter((r) => r.count > 0)
    : [...reactions, { kind, count: 1, mine: true }];
  const order = REACTIONS.map((r) => r.kind);
  return next.sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind));
};

/**
 * Reaction chips (emoji + count; the viewer's own are highlighted) and a picker.
 * Updates optimistically and settles on the server's counts.
 */
const Reactions = ({ postId, reactions, onChange, onReacted }) => {
  const [open, setOpen] = useState(false);
  const pickerRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => {
      if (e.type === "keydown" ? e.key === "Escape" : !pickerRef.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const toggle = async (kind) => {
    setOpen(false);
    const adding = !reactions.find((r) => r.kind === kind)?.mine;
    const before = reactions;
    onChange(toggled(reactions, kind));
    try {
      const { data } = await (adding
        ? api.put(`/board/posts/${postId}/reactions/${kind}`)
        : api.delete(`/board/posts/${postId}/reactions/${kind}`));
      onChange(data.reactions);
      if (adding) onReacted?.();
    } catch (err) {
      onChange(before);
      toast.error(apiError(err, "Couldn't save your reaction."));
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {reactions.map((r) => (
        <button
          key={r.kind}
          type="button"
          onClick={() => toggle(r.kind)}
          aria-pressed={r.mine}
          aria-label={`${META[r.kind].label}: ${r.count}${r.mine ? ", including you" : ""}`}
          title={r.mine ? `You reacted ${META[r.kind].label.toLowerCase()}` : META[r.kind].label}
          className={cx(
            "flex h-7 items-center gap-1 rounded-full px-2 text-[13px] ring-1 transition-colors",
            r.mine
              ? "bg-accent-50 text-accent-800 ring-accent-600/40"
              : "bg-white text-slate-700 ring-slate-200 hover:bg-slate-50"
          )}
        >
          <span aria-hidden="true">{META[r.kind].emoji}</span>
          <span className="font-medium tabular-nums">{r.count}</span>
        </button>
      ))}
      <div ref={pickerRef} className="relative">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-haspopup="true"
          aria-label="Add a reaction"
          title="Add a reaction"
          className="flex h-7 items-center gap-1 rounded-full px-2 text-[13px] text-slate-500 ring-1 ring-slate-200 transition-colors hover:bg-slate-50 hover:text-slate-800"
        >
          <FaceSmileIcon className="size-4" />
          {reactions.length === 0 && <span>React</span>}
        </button>
        {open && (
          <div
            role="menu"
            aria-label="Reactions"
            className="absolute bottom-full left-0 z-20 mb-1.5 flex gap-0.5 rounded-full bg-white p-1 shadow-lg ring-1 ring-slate-900/10"
          >
            {REACTIONS.map((r) => {
              const mine = reactions.find((x) => x.kind === r.kind)?.mine;
              return (
                <button
                  key={r.kind}
                  type="button"
                  role="menuitemcheckbox"
                  aria-checked={Boolean(mine)}
                  aria-label={r.label}
                  title={r.label}
                  onClick={() => toggle(r.kind)}
                  className={cx(
                    "flex size-9 items-center justify-center rounded-full text-lg transition-transform motion-safe:hover:scale-125",
                    mine ? "bg-accent-50" : "hover:bg-slate-100"
                  )}
                >
                  {r.emoji}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default Reactions;
