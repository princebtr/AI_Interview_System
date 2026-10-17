import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import {
  AcademicCapIcon,
  ArrowRightStartOnRectangleIcon,
  Bars3Icon,
  BuildingLibraryIcon,
  CalendarDaysIcon,
  ChartBarIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ClipboardDocumentCheckIcon,
  ClipboardDocumentListIcon,
  Cog6ToothIcon,
  DocumentChartBarIcon,
  HomeIcon,
  RectangleStackIcon,
  SparklesIcon,
  Squares2X2Icon,
  UserCircleIcon,
  UserGroupIcon,
  UsersIcon,
  VideoCameraIcon,
} from "@heroicons/react/24/outline";
import { useAuth } from "../../context/AuthContext";
import { InstitutionLogo, LogoMark } from "../ui";
import { cx, initials } from "../../utils/helpers";
import { roleMeta } from "../../utils/roles";

// One design system, three purpose-built navigations (see the UX wireframes).
// Settings sits at the foot of the sidebar; the profile menu (top right) opens it too.
const NAVIGATION = {
  admin: {
    label: "Admin Console",
    items: [
      { to: "/dashboard", label: "Dashboard", icon: Squares2X2Icon },
      { to: "/users", label: "Users", icon: UsersIcon },
      { to: "/cohorts", label: "Cohorts", icon: UserGroupIcon },
      { label: "Departments", icon: BuildingLibraryIcon, soon: true },
      { label: "Programs", icon: AcademicCapIcon, soon: true },
      { to: "/assessments", label: "Tests", icon: ClipboardDocumentListIcon },
      { label: "AI Interviews", icon: VideoCameraIcon, soon: true },
      { label: "Reports", icon: DocumentChartBarIcon, soon: true },
    ],
  },
  educator: {
    label: "Educator Portal",
    items: [
      { to: "/dashboard", label: "Dashboard", icon: Squares2X2Icon },
      { to: "/generator", label: "AI Generator", icon: SparklesIcon },
      { to: "/questions", label: "Question Bank", icon: RectangleStackIcon },
      { to: "/students", label: "My Students", icon: AcademicCapIcon },
      { to: "/assessments", label: "Tests", icon: ClipboardDocumentListIcon },
      { label: "Reports", icon: DocumentChartBarIcon, soon: true },
    ],
  },
  student: {
    label: "Student Portal",
    items: [
      { to: "/dashboard", label: "Home", icon: HomeIcon },
      { to: "/tests", label: "My Tests", icon: CalendarDaysIcon },
      { to: "/interview", label: "AI Interview", icon: VideoCameraIcon },
      { to: "/assessment", label: "Practice Test", icon: ClipboardDocumentCheckIcon },
      { to: "/performance", label: "My Performance", icon: ChartBarIcon },
    ],
  },
};

const focusRing = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-on-primary";

const itemBase =
  "flex flex-col items-center justify-center gap-1 rounded-lg px-1 py-2.5 text-center text-[11px] leading-tight transition-colors";

// A compact rail in the primary colour: icon over a short label; the active item is a white tile.
const NavItem = ({ item, onNavigate }) => {
  const { to, label, icon: Icon, soon, end } = item;

  if (soon) {
    return (
      <div aria-disabled="true" title={`${label} (coming soon)`} className={cx(itemBase, "cursor-default font-medium text-on-primary/40")}>
        <Icon className="size-5 shrink-0" />
        <span>{label}</span>
      </div>
    );
  }

  return (
    <NavLink
      to={to}
      end={end}
      onClick={onNavigate}
      className={({ isActive }) =>
        cx(
          itemBase,
          focusRing,
          isActive
            ? "bg-surface font-semibold text-accent-700 shadow-sm"
            : "font-medium text-on-primary/80 hover:bg-on-primary/10 hover:text-on-primary"
        )
      }
    >
      {({ isActive }) => (
        <>
          <Icon className={cx("size-5 shrink-0", isActive && "text-accent-600")} />
          <span>{label}</span>
        </>
      )}
    </NavLink>
  );
};

const SidebarContent = ({ onNavigate }) => {
  const { user } = useAuth();
  const navigation = NAVIGATION[user?.role] ?? NAVIGATION.student;
  const institution = user?.institution;

  return (
    <div className="flex h-full flex-col bg-primary">
      {/* The institution's own brand leads; Cohortix stays in the background. */}
      <Link
        to="/dashboard"
        onClick={onNavigate}
        aria-label={`${institution?.name ?? "Cohortix"}, home`}
        title={institution?.name}
        className={cx("mx-auto mt-4 mb-5 shrink-0 rounded-xl", focusRing)}
      >
        <InstitutionLogo institution={institution} className="size-11 rounded-xl" />
      </Link>

      <nav className="flex-1 overflow-y-auto px-2" aria-label="Main">
        <ul className="space-y-1">
          {navigation.items.map((item) => (
            <li key={item.label}>
              <NavItem item={item} onNavigate={onNavigate} />
            </li>
          ))}
        </ul>
      </nav>

      <div className="shrink-0 space-y-3 px-2 pt-2 pb-4">
        <NavItem item={{ to: "/settings", label: "Settings", icon: Cog6ToothIcon }} onNavigate={onNavigate} />
        <div className="flex flex-col items-center gap-1 text-[10px] text-on-primary/70">
          Powered by
          <span className="flex items-center gap-1 font-semibold text-on-primary">
            <LogoMark className="size-3.5 rounded-[3px]" />
            Cohortix
          </span>
        </div>
      </div>
    </div>
  );
};

const menuItem =
  "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 hover:text-slate-900 focus-visible:bg-slate-50 focus-visible:outline-none";

const ProfileMenu = () => {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const buttonRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (e) => !rootRef.current?.contains(e.target) && setOpen(false);
    const onKey = (e) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      buttonRef.current?.focus();
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${user?.name ?? "your account"}`}
        className="flex items-center gap-2 rounded-full p-1 transition-colors hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500 sm:pr-2.5"
      >
        <span className="bg-primary flex size-8 shrink-0 items-center justify-center rounded-full text-[12px] font-bold text-on-primary">
          {initials(user?.name)}
        </span>
        <span className="hidden max-w-40 truncate text-sm font-semibold text-slate-800 sm:block">{user?.name}</span>
        <ChevronDownIcon
          aria-hidden="true"
          className={cx("hidden size-4 text-slate-400 transition-transform sm:block", open && "rotate-180")}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="fade-in absolute right-0 z-40 mt-2 w-60 rounded-lg border border-border bg-surface p-1.5 shadow-lift"
        >
          <div className="px-2.5 pt-1.5 pb-2.5">
            <p className="truncate text-sm font-semibold text-slate-900">{user?.name}</p>
            <p className="truncate text-[12px] text-slate-500">{user?.email ?? roleMeta(user?.role).label}</p>
          </div>
          <div className="border-t border-slate-100 pt-1.5">
            <Link role="menuitem" to="/settings/profile" onClick={() => setOpen(false)} className={menuItem}>
              <UserCircleIcon className="size-[18px] text-slate-400" />
              Profile
            </Link>
            <button role="menuitem" onClick={logout} className={menuItem}>
              <ArrowRightStartOnRectangleIcon className="size-[18px] text-slate-400" />
              Log out
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

// Breadcrumb labels by path; a path not listed here (an id) takes its parent's detail label.
const CRUMB_LABELS = {
  "/settings": "Settings",
  "/settings/profile": "Profile",
  "/settings/account": "Account",
  "/settings/password": "Password",
  "/settings/institution": "Institution",
  "/users": "Users",
  "/users/import": "Import users",
  "/cohorts": "Cohorts",
  "/generator": "AI Generator",
  "/questions": "Question Bank",
  "/students": "My Students",
  "/assessments": "Tests",
  "/assessments/new": "New test",
  "/interview": "AI Interview",
  "/assessment": "Practice Test",
  "/tests": "My Tests",
  "/tests/setup-check": "Check my setup",
  "/performance": "My Performance",
};
const DETAIL_LABELS = { "/cohorts": "Cohort details", "/assessments": "Test details", "/tests": "Test" };

const Breadcrumbs = () => {
  const { pathname } = useLocation();
  const crumbs = [{ to: "/dashboard", label: "Home" }];
  let path = "";
  for (const segment of pathname.split("/").filter(Boolean)) {
    const parent = path;
    path += `/${segment}`;
    if (path === "/dashboard") continue;
    const label = CRUMB_LABELS[path] ?? DETAIL_LABELS[parent];
    if (label) crumbs.push({ to: path, label });
  }

  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1.5 text-sm">
        {crumbs.map((crumb, i) => {
          const last = i === crumbs.length - 1;
          return (
            <li key={crumb.to} className={cx("flex min-w-0 items-center gap-1.5", !last && "hidden sm:flex")}>
              {i > 0 && <ChevronRightIcon aria-hidden="true" className="size-4 shrink-0 text-slate-400" />}
              {last ? (
                <span aria-current="page" className="truncate font-semibold text-foreground">
                  {crumb.label}
                </span>
              ) : (
                <Link to={crumb.to} className="truncate text-muted transition-colors hover:text-accent-600">
                  {crumb.label}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
};

const AppShell = () => {
  const { user } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const { pathname } = useLocation();
  // Replay the page fade on navigation, but not when switching settings tabs:
  // the settings header and tab bar should stay put.
  const animationKey = pathname.startsWith("/settings/") ? "/settings" : pathname;
  const contentRef = useRef(null);
  const drawerRef = useRef(null);
  const menuButtonRef = useRef(null);

  const institutionName = user?.institution?.name;
  useEffect(() => {
    document.title = institutionName ? `${institutionName} · Cohortix` : "Cohortix";
  }, [institutionName]);

  useEffect(() => {
    if (!mobileOpen) return;
    const content = contentRef.current;
    const menuButton = menuButtonRef.current;
    content?.setAttribute("inert", "");
    drawerRef.current?.querySelector("a, button")?.focus();
    const onKey = (e) => e.key === "Escape" && setMobileOpen(false);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      content?.removeAttribute("inert");
      menuButton?.focus();
    };
  }, [mobileOpen]);

  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar: a narrow full-height rail. */}
      <aside className="sticky top-0 hidden h-screen w-[88px] shrink-0 lg:block">
        <SidebarContent />
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Main menu">
          <div className="fade-in absolute inset-0 bg-slate-900/40" onClick={() => setMobileOpen(false)} />
          <aside ref={drawerRef} className="slide-in absolute inset-y-0 left-0 w-[88px] shadow-xl">
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      <div ref={contentRef} className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-surface px-4 sm:px-6">
          <button
            ref={menuButtonRef}
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
            aria-expanded={mobileOpen}
            className="-ml-1.5 rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800 lg:hidden"
          >
            <Bars3Icon className="size-5" />
          </button>
          <Breadcrumbs />
          <div className="ml-auto">
            <ProfileMenu />
          </div>
        </header>

        <main
          key={animationKey}
          className="fade-in mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 lg:px-10"
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default AppShell;
