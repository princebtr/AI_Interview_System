import { CheckCircleIcon, CheckIcon } from "@heroicons/react/20/solid";
import { GlowBackdrop, InstitutionLogo, Logo, PoweredBy } from "../ui";

const PREVIEW_CHECKS = ["1 person", "No phone", "0 tab switches"];

// A static rendering of the product, so new users see what they get. The interview
// card sits in a slight isometric tilt that relaxes on hover.
const ProductPreview = () => (
  <div className="relative w-full max-w-md">
    <span className="inline-flex items-center gap-2 rounded-full bg-white/80 py-1 pr-3 pl-1 text-[12px] font-medium text-slate-700 shadow-soft ring-1 ring-accent-200 backdrop-blur">
      <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px] font-bold tracking-wide text-on-secondary">NEW</span>
      Timed tests for every cohort
    </span>
    <h2 className="mt-5 text-4xl leading-[1.1] font-extrabold tracking-[-0.02em] text-balance text-slate-900">
      Rehearse the interview <span className="text-accent-600">before it counts.</span>
    </h2>
    <p className="mt-4 max-w-sm text-[15px] leading-relaxed text-slate-600">
      Answer AI-generated questions out loud, get a score on every answer, and practise
      under the same proctoring rules as the real thing.
    </p>

    <div className="relative mt-12 perspective-[2000px]" aria-hidden="true">
      <div className="rotate-x-[5deg] rotate-y-[-12deg] rounded-xl border border-slate-200/70 bg-white shadow-lift transition-transform duration-500 ease-out hover:rotate-x-[2deg] hover:rotate-y-[-8deg] motion-reduce:transition-none">
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5 text-[12px]">
          <span className="text-slate-500">
            <span className="font-semibold text-slate-900">Question 2</span>
            <span className="mx-1.5 text-slate-300">/</span>System design
          </span>
          <span className="flex items-center gap-1.5 font-semibold text-red-600">
            <span className="size-1.5 rounded-full bg-red-500" />
            Live
          </span>
        </div>
        <div className="space-y-3 p-4">
          <p className="text-[15px] leading-snug font-medium text-slate-900">
            How would you design a rate limiter for a public API?
          </p>
          <p className="rounded-md border border-slate-100 bg-slate-50 p-3 text-[13px] leading-relaxed text-slate-600">
            I'd use a token bucket per API key and keep the counts in Redis, so every server
            enforces the same limit…
          </p>
        </div>
        <div className="flex items-center gap-3 border-t border-slate-100 px-4 py-3">
          <span className="text-[12px] text-slate-500">Score</span>
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
            <div className="bg-primary h-full w-4/5 rounded-full" />
          </div>
          <span className="text-[13px] font-bold text-slate-900 tabular-nums">8 / 10</span>
        </div>
      </div>

      <div className="animate-drift absolute -top-6 -right-5 flex items-center gap-2.5 rounded-lg border border-slate-200/70 bg-white py-2 pr-4 pl-2.5 shadow-lift">
        <span className="flex size-7 items-center justify-center rounded-full bg-secondary text-on-secondary">
          <CheckIcon className="size-4" />
        </span>
        <span>
          <span className="block text-[11px] text-slate-500">Unit test submitted</span>
          <span className="block text-[13px] font-bold text-slate-900 tabular-nums">18 / 20 marks</span>
        </span>
      </div>
    </div>

    <ul className="mt-6 grid grid-cols-3 gap-3" aria-hidden="true">
      {PREVIEW_CHECKS.map((check) => (
        <li
          key={check}
          className="flex items-center gap-2 rounded-lg border border-slate-200/70 bg-white/90 px-3 py-2.5 text-[12px] font-medium text-slate-700 shadow-soft"
        >
          <CheckCircleIcon className="size-4 shrink-0 text-emerald-600" />
          {check}
        </li>
      ))}
    </ul>
  </div>
);

/** `brand` ({ name, logoUrl }) shows an institution's identity instead of Cohortix's. */
const AuthLayout = ({ title, subtitle, footer, brand, children }) => (
  <div className="grid min-h-screen bg-white lg:grid-cols-2">
    <div className="relative isolate flex flex-col overflow-hidden px-6 py-8 sm:px-10">
      <GlowBackdrop className="inset-x-0 top-0 h-80 opacity-70 lg:hidden" />
      {brand ? (
        <div className="flex items-center gap-3">
          <InstitutionLogo institution={brand} className="size-10" />
          <div className="min-w-0">
            <p className="truncate text-[15px] font-semibold text-slate-900">{brand.name}</p>
            <PoweredBy className="mt-0.5" />
          </div>
        </div>
      ) : (
        <Logo />
      )}
      <div className="fade-in mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-12">
        <h1 className="text-[1.75rem] leading-tight font-bold tracking-[-0.02em] text-slate-900">{title}</h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-500">{subtitle}</p>
        <div className="mt-8">{children}</div>
        <p className="mt-8 text-sm text-slate-500">{footer}</p>
      </div>
      <p className="text-[12px] text-slate-400">© {new Date().getFullYear()} Cohortix</p>
    </div>

    <aside className="relative isolate hidden items-center justify-center overflow-hidden border-l border-slate-200/70 bg-accent-50 p-12 lg:flex">
      <GlowBackdrop className="inset-0" />
      <ProductPreview />
    </aside>
  </div>
);

export default AuthLayout;
