import { forwardRef, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ArrowRightIcon,
  CheckIcon,
  ChevronUpDownIcon,
  DocumentDuplicateIcon,
  EyeIcon,
  EyeSlashIcon,
  MagnifyingGlassIcon,
} from "@heroicons/react/20/solid";
import { XMarkIcon } from "@heroicons/react/24/outline";
import { apiAsset } from "../config/api";
import { cx, initials } from "../utils/helpers";
import { buttonStyles, inputStyles } from "./styles";

export const Spinner = ({ className = "size-4" }) => (
  <svg
    className={cx("animate-spin", className)}
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
  >
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" />
    <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
  </svg>
);

/* ------------------------------------------------------------------ */
/* Buttons                                                             */
/* ------------------------------------------------------------------ */

/** A trailing arrow that nudges forward when its button or link is hovered. */
export const ArrowIcon = ({ className }) => (
  <ArrowRightIcon
    className={cx(
      "size-4 transition-transform duration-200 motion-safe:group-hover/button:translate-x-0.5",
      className
    )}
    aria-hidden="true"
  />
);

export const Button = forwardRef(function Button(
  {
    variant = "primary",
    size = "md",
    type = "button",
    loading = false,
    disabled,
    className,
    children,
    onClick,
    ...props
  },
  ref
) {
  // While loading the button stays focusable (aria-disabled) so keyboard and
  // screen-reader users don't lose their place; clicks and submits are ignored.
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled}
      aria-disabled={loading || undefined}
      aria-busy={loading || undefined}
      onClick={(e) => {
        if (loading) {
          e.preventDefault();
          return;
        }
        onClick?.(e);
      }}
      className={buttonStyles({ variant, size, className })}
      {...props}
    >
      {loading && <Spinner />}
      {children}
    </button>
  );
});

/* ------------------------------------------------------------------ */
/* Form fields                                                         */
/* ------------------------------------------------------------------ */

export const Field = ({ id, label, hint, error, action, children }) => (
  <div>
    {(label || action) && (
      <div className="mb-1.5 flex items-center justify-between gap-3">
        {label && (
          <label htmlFor={id} className="text-sm font-semibold text-slate-700">
            {label}
          </label>
        )}
        {action}
      </div>
    )}
    {children}
    {error ? (
      <p id={`${id}-error`} className="mt-1.5 text-[13px] text-red-600">
        {error}
      </p>
    ) : (
      hint && (
        <p id={`${id}-hint`} className="mt-1.5 text-[13px] text-slate-500">
          {hint}
        </p>
      )
    )}
  </div>
);

/** aria-describedby for a control rendered inside <Field>. */
const describedBy = (id, { error, hint }) =>
  error ? `${id}-error` : hint ? `${id}-hint` : undefined;

/** A search box with a leading magnifier and a visually hidden label. */
export const SearchInput = ({ id, label, className, inputClassName, ...props }) => (
  <div className={cx("relative", className)}>
    <label htmlFor={id} className="sr-only">
      {label}
    </label>
    <MagnifyingGlassIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
    <input id={id} type="search" className={cx(inputStyles(), "h-9 pr-3 pl-9", inputClassName)} {...props} />
  </div>
);

export const Input = forwardRef(function Input(
  {
    id,
    label,
    hint,
    error,
    action,
    type = "text",
    className,
    revealed: revealedProp,
    onRevealedChange,
    ...props
  },
  ref
) {
  // Password visibility is internal unless the parent controls it (e.g. to show a generated password).
  const [revealedState, setRevealedState] = useState(false);
  const revealed = revealedProp ?? revealedState;
  const setRevealed = (next) => (onRevealedChange ? onRevealedChange(next) : setRevealedState(next));
  const isPassword = type === "password";

  return (
    <Field id={id} label={label} hint={hint} error={error} action={action}>
      <div className="relative">
        <input
          id={id}
          ref={ref}
          type={isPassword && revealed ? "text" : type}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(id, { error, hint })}
          className={cx(inputStyles(error), "h-10 px-3", isPassword && "pr-10", className)}
          {...props}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setRevealed(!revealed)}
            aria-label={revealed ? "Hide password" : "Show password"}
            className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-md text-slate-400 transition-colors hover:text-slate-700"
          >
            {revealed ? <EyeSlashIcon className="size-4" /> : <EyeIcon className="size-4" />}
          </button>
        )}
      </div>
    </Field>
  );
});

export const Textarea = forwardRef(function Textarea(
  { id, label, hint, error, action, className, ...props },
  ref
) {
  return (
    <Field id={id} label={label} hint={hint} error={error} action={action}>
      <textarea
        id={id}
        ref={ref}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, { error, hint })}
        className={cx(inputStyles(error), "min-h-32 resize-y px-3 py-2.5 leading-relaxed", className)}
        {...props}
      />
    </Field>
  );
});

/** `compact` matches the 36px search boxes and filter bars. */
export const Select = forwardRef(function Select(
  { id, label, hint, error, action, compact = false, className, children, ...props },
  ref
) {
  return (
    <Field id={id} label={label} hint={hint} error={error} action={action}>
      <div className="relative">
        <select
          id={id}
          ref={ref}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(id, { error, hint })}
          className={cx(inputStyles(error), compact ? "h-9" : "h-10", "appearance-none pr-9 pl-3", className)}
          {...props}
        >
          {children}
        </select>
        <ChevronUpDownIcon className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-slate-400" />
      </div>
    </Field>
  );
});

export const ChoiceChips = ({ options, value, onChange }) => (
  <div className="flex flex-wrap gap-1.5">
    {options.map((option) => (
      <button
        key={option}
        type="button"
        onClick={() => onChange(option)}
        aria-pressed={value === option}
        className={cx(
          "rounded-full border px-3 py-1 text-[13px] transition-colors",
          value === option
            ? "border-accent-600 bg-accent-50 text-accent-800"
            : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900"
        )}
      >
        {option}
      </button>
    ))}
  </div>
);

const strengthLevels = [
  { label: "Too weak", color: "bg-red-500" },
  { label: "Weak", color: "bg-red-500" },
  { label: "Fair", color: "bg-amber-500" },
  { label: "Good", color: "bg-emerald-600" },
  { label: "Strong", color: "bg-emerald-600" },
];

const passwordScore = (pw) => {
  let score = 0;
  if (pw.length >= 6) score++;
  if (pw.length >= 10) score++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score++;
  if (/\d/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  return Math.min(score, 4);
};

export const PasswordStrength = ({ password }) => {
  if (!password) return null;
  const level = passwordScore(password);
  const { label, color } = strengthLevels[level];
  return (
    <div className="mt-2 flex items-center gap-3" aria-live="polite">
      <div className="flex flex-1 gap-1">
        {[0, 1, 2, 3].map((i) => (
          <span
            key={i}
            className={cx(
              "h-1 flex-1 rounded-full transition-colors",
              i < Math.max(1, level) ? color : "bg-slate-200"
            )}
          />
        ))}
      </div>
      <span className="w-14 text-right text-[12px] text-slate-500">{label}</span>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/* Layout                                                              */
/* ------------------------------------------------------------------ */

/** White surface with a soft tinted shadow. `interactive` adds the hover lift for clickable cards. */
export const Card = ({ className, interactive = false, children, ...props }) => (
  <section
    className={cx(
      "rounded-lg border border-slate-200/70 bg-white shadow-soft",
      interactive && "transition-all duration-200 ease-out hover:shadow-lift motion-safe:hover:-translate-y-1",
      className
    )}
    {...props}
  >
    {children}
  </section>
);

export const CardHeader = ({ title, description, action }) => (
  <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
    <div className="min-w-0">
      <h2 className="text-[15px] font-semibold text-slate-900">{title}</h2>
      {description && <p className="mt-0.5 text-[13px] text-slate-500">{description}</p>}
    </div>
    {action}
  </div>
);

export const CardFooter = ({ className, children }) => (
  <div
    className={cx(
      "flex flex-col-reverse gap-3 rounded-b-lg border-t border-slate-100 bg-slate-50/70 px-5 py-3 sm:flex-row sm:items-center sm:justify-between",
      className
    )}
  >
    {children}
  </div>
);

export const PageHeader = ({ eyebrow, title, description, actions }) => (
  <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
    <div className="min-w-0">
      {eyebrow && <p className="text-[13px] font-semibold text-accent-700">{eyebrow}</p>}
      <h1 className="mt-1 text-2xl leading-tight font-bold tracking-[-0.02em] text-balance text-slate-900 sm:text-[1.75rem]">
        {title}
      </h1>
      {description && (
        <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-slate-500">{description}</p>
      )}
    </div>
    {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
  </div>
);

const badgeTones = {
  neutral: "bg-slate-100 text-slate-600 ring-slate-200",
  brand: "bg-accent-50 text-accent-800 ring-accent-600/20",
  secondary: "bg-accent2-50 text-accent2-700 ring-accent2-600/20",
  success: "bg-emerald-50 text-emerald-800 ring-emerald-600/20",
  blue: "bg-blue-50 text-blue-800 ring-blue-600/20",
  violet: "bg-violet-50 text-violet-800 ring-violet-600/20",
  ai: "bg-fuchsia-50 text-fuchsia-800 ring-fuchsia-600/20",
  info: "bg-sky-50 text-sky-800 ring-sky-600/20",
  warning: "bg-amber-50 text-amber-800 ring-amber-600/20",
  danger: "bg-red-50 text-red-700 ring-red-600/15",
};

export const Badge = ({ tone = "neutral", className, children }) => (
  <span
    className={cx(
      "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[12px] font-medium whitespace-nowrap ring-1 ring-inset",
      badgeTones[tone],
      className
    )}
  >
    {children}
  </span>
);

export const LiveDot = () => (
  <span className="relative flex size-1.5">
    <span className="absolute inline-flex size-full animate-ping rounded-full bg-red-400 opacity-75" />
    <span className="relative inline-flex size-1.5 rounded-full bg-red-500" />
  </span>
);

/**
 * Two blurred orbs in the role's colours behind a hero area. Decorative only: place it
 * first inside a `relative isolate` wrapper and size it with `className`.
 */
export const GlowBackdrop = ({ className }) => (
  <div
    aria-hidden="true"
    className={cx(
      // A radial mask fades the orbs out before every box edge, so clipping never shows a hard line.
      "pointer-events-none absolute -z-10 overflow-hidden [mask-image:radial-gradient(ellipse_at_top,black_35%,transparent_75%)]",
      className
    )}
  >
    <div className="animate-drift absolute -top-32 left-[6%] size-[26rem] rounded-full bg-accent-300/35 blur-3xl" />
    <div className="animate-drift absolute -top-20 right-[2%] size-[22rem] rounded-full bg-accent2-300/30 blur-3xl [animation-delay:-4.5s]" />
  </div>
);

export const Kbd = ({ children }) => (
  <kbd className="inline-flex min-w-5 items-center justify-center rounded border border-slate-200 bg-white px-1 font-mono text-[11px] text-slate-500">
    {children}
  </kbd>
);

// The Cohortix mark keeps the platform's indigo → violet in every role (it's the
// product's signature, not the role's), unlike everything else that uses accent tokens.
export const LogoMark = ({ className = "size-7" }) => (
  <span
    className={cx(
      "flex shrink-0 items-center justify-center rounded-md bg-linear-to-br from-indigo-600 to-violet-600 text-white shadow-[0_2px_8px_-1px_rgb(79_70_229/0.45)]",
      className
    )}
  >
    {/* Cohortix: a group ("C") gathered around a shared centre. */}
    <svg viewBox="0 0 20 20" className="size-[66%]" fill="none" aria-hidden="true">
      <path
        d="M14.6 6.2A6 6 0 1 0 14.6 13.8"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <circle cx="10" cy="10" r="2" fill="currentColor" />
    </svg>
  </span>
);

export const Logo = ({ collapsed = false }) => (
  <span className="flex items-center gap-2.5">
    <LogoMark />
    {!collapsed && (
      <span className="text-[15px] font-semibold tracking-tight text-slate-900">Cohortix</span>
    )}
  </span>
);

export const PoweredBy = ({ className }) => (
  <span className={cx("flex items-center gap-1 text-[11px] text-slate-400", className)}>
    Powered by
    <LogoMark className="size-3 rounded-[3px]" />
    <span className="font-medium text-slate-500">Cohortix</span>
  </span>
);

/** The institution's uploaded logo, or its initials when there isn't one. */
export const InstitutionLogo = ({ institution, className = "size-9", initialsClassName = "text-[12px]" }) => {
  const [failedUrl, setFailedUrl] = useState(null);
  const url = institution?.logoUrl;
  if (url && url !== failedUrl) {
    return (
      <span
        className={cx(
          "flex shrink-0 items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-white",
          className
        )}
      >
        <img src={apiAsset(url)} alt="" className="size-full object-contain p-0.5" onError={() => setFailedUrl(url)} />
      </span>
    );
  }
  return (
    <span
      aria-hidden="true"
      className={cx(
        "flex shrink-0 items-center justify-center rounded-lg bg-accent-100 font-bold text-accent-800",
        initialsClassName,
        className
      )}
    >
      {initials(institution?.name ?? "Cohortix")}
    </span>
  );
};

export const CopyButton = ({ value, label = "Copy" }) => {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(timer);
  }, [copied]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      // Clipboard blocked (insecure context or permissions); the value stays visible to copy by hand.
    }
  };

  return (
    <button
      type="button"
      onClick={copy}
      aria-label={copied ? "Copied" : label}
      title={copied ? "Copied" : label}
      className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
    >
      {copied ? (
        <CheckIcon className="size-4 text-emerald-600" />
      ) : (
        <DocumentDuplicateIcon className="size-4" />
      )}
    </button>
  );
};

const FOCUSABLE =
  "input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href]";

/**
 * Right-hand panel for focused tasks (e.g. creating a record).
 * - `onClose`: the close button. `onDismiss` (defaults to onClose): Escape and
 *   backdrop clicks. Pass a no-op to ignore accidental dismissal.
 * - `view`: change it when the panel swaps content to move focus into the new view.
 * While open, the app behind it is `inert`, so focus can't wander under the backdrop.
 */
export const SlideOver = ({ open, onClose, onDismiss, title, description, footer, view, children }) => {
  const panelRef = useRef(null);
  const bodyRef = useRef(null);
  // Latest handler without re-running the open/close effect on every parent render.
  // A layout effect updates it before paint, so a native keydown can never hit a
  // stale handler (e.g. Escape right after the panel switches views).
  const dismissRef = useRef(onDismiss ?? onClose);
  useLayoutEffect(() => {
    dismissRef.current = onDismiss ?? onClose;
  }, [onDismiss, onClose]);

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement;
    const app = document.getElementById("root");
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    app?.setAttribute("inert", "");
    const onKey = (e) => e.key === "Escape" && dismissRef.current();
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      app?.removeAttribute("inert");
      document.body.style.overflow = overflow;
      previouslyFocused?.focus?.();
    };
  }, [open]);

  // Start keyboard users on the first control of each view, not the close button.
  useEffect(() => {
    if (!open) return;
    const target = bodyRef.current?.querySelector("[data-autofocus]") ?? bodyRef.current?.querySelector(FOCUSABLE);
    (target ?? panelRef.current)?.focus();
  }, [open, view]);

  if (!open) return null;

  // Portal to <body> so no transformed/animated ancestor becomes the containing block.
  return createPortal(
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-labelledby="slide-over-title">
      <div className="fade-in absolute inset-0 bg-slate-900/30" onClick={() => dismissRef.current()} />
      <div
        ref={panelRef}
        tabIndex={-1}
        className="slide-in-right absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-xl focus:outline-none"
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div className="min-w-0">
            <h2 id="slide-over-title" className="text-base font-semibold text-slate-900">
              {title}
            </h2>
            {description && <p className="mt-0.5 text-[13px] text-slate-500">{description}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="-mr-1.5 rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
          >
            <XMarkIcon className="size-5" />
          </button>
        </div>
        <div ref={bodyRef} className="flex-1 overflow-y-auto">
          {children}
        </div>
        {footer && (
          <div className="flex items-center justify-end gap-2 border-t border-slate-200 bg-slate-50/70 px-5 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body
  );
};
