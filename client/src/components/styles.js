// Class-name recipes shared by components and by pages that style other elements
// (links, bare inputs) to match them. Kept apart from ui.jsx so that file only
// exports components (React Fast Refresh).
import { cx } from "../utils/helpers";

const buttonVariants = {
  // The solid primary colour with a tinted shadow; darkens and lifts slightly on hover.
  primary:
    "bg-primary text-on-primary shadow-button hover:bg-primary-hover hover:shadow-button-hover motion-safe:hover:-translate-y-0.5 active:translate-y-0",
  secondary:
    "border border-slate-200 bg-white text-slate-700 shadow-xs hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900",
  ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
  danger:
    "border border-slate-200 bg-white text-red-700 shadow-xs hover:border-red-300 hover:bg-red-50",
  // Leaving an exam (Quit test, End session).
  quit: "border border-red-200 bg-red-50 text-red-700 hover:border-red-300 hover:bg-red-100 hover:text-red-800",
};

const buttonSizes = {
  sm: "h-8 px-3 text-[13px]",
  md: "h-9 px-4 text-sm",
  lg: "h-11 px-5 text-sm",
};

/** Button classes, for links and other elements that should look like a <Button>. */
export const buttonStyles = ({ variant = "primary", size = "md", className } = {}) =>
  cx(
    "group/button inline-flex shrink-0 items-center justify-center gap-2 rounded-md font-semibold whitespace-nowrap transition-all duration-200 ease-out",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500",
    "disabled:pointer-events-none disabled:opacity-50 aria-disabled:cursor-wait aria-disabled:opacity-70",
    buttonVariants[variant],
    buttonSizes[size],
    className
  );

/** Text-control classes (border, focus ring, error state), for inputs built outside <Input>. */
export const inputStyles = (error) =>
  cx(
    "block w-full rounded-md border bg-white text-sm text-slate-900 shadow-xs transition-[border-color,box-shadow] duration-200",
    "placeholder:text-slate-400 focus:ring-2 focus:ring-offset-1 focus:outline-none",
    "disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-500",
    error
      ? "border-red-400 focus:border-red-500 focus:ring-red-500"
      : "border-slate-200 hover:border-slate-300 focus:border-accent-500 focus:ring-accent-500"
  );
