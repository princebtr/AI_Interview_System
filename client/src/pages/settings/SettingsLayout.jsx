import { NavLink, Outlet } from "react-router-dom";
import {
  BuildingLibraryIcon,
  IdentificationIcon,
  KeyIcon,
  UserCircleIcon,
} from "@heroicons/react/24/outline";
import { useAuth } from "../../context/AuthContext";
import { Badge, Card, PageHeader } from "../../components/ui";
import { cx, initials } from "../../utils/helpers";
import { roleMeta } from "../../utils/roles";

// Each tab is its own route (/settings/<tab>), so tabs can be linked to and the
// browser's back button moves between them.
const TABS = [
  { to: "profile", label: "Profile", icon: UserCircleIcon },
  { to: "account", label: "Account", icon: IdentificationIcon },
  { to: "password", label: "Password", icon: KeyIcon },
  { to: "institution", label: "Institution", icon: BuildingLibraryIcon, roles: ["admin"] },
];

const TabLink = ({ to, label, icon: Icon }) => (
  <NavLink
    to={to}
    className={({ isActive }) =>
      cx(
        "group relative flex h-12 shrink-0 items-center gap-2 px-1 text-sm whitespace-nowrap transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500",
        isActive ? "font-semibold text-slate-900" : "font-medium text-slate-500 hover:text-slate-800"
      )
    }
  >
    {({ isActive }) => (
      <>
        {Icon && (
          <Icon
            className={cx(
              "hidden size-[18px] transition-colors sm:block",
              isActive ? "text-accent-600" : "text-slate-400 group-hover:text-slate-500"
            )}
          />
        )}
        {label}
        {isActive && <span aria-hidden="true" className="bg-primary absolute inset-x-0 bottom-0 h-0.5 rounded-full" />}
      </>
    )}
  </NavLink>
);

const SettingsLayout = () => {
  const { user } = useAuth();
  const role = roleMeta(user?.role);
  const tabs = TABS.filter((tab) => !tab.roles || tab.roles.includes(user?.role));
  const place = [user?.institution?.name, user?.cohort?.name].filter(Boolean).join(" · ");

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Settings"
        title="Your account"
        description={
          user?.role === "admin"
            ? "Manage your profile, sign-in and password, and your institution's branding."
            : "Manage your profile, sign-in and password."
        }
      />

      <Card className="overflow-hidden">
        {/* Identity strip: who these settings belong to. The avatar overlaps the band. */}
        <div aria-hidden="true" className="h-16 bg-accent-100" />
        <div className="flex flex-col gap-3 px-5 pb-4 sm:flex-row sm:items-start sm:gap-4">
          <span className="bg-primary -mt-8 flex size-16 shrink-0 items-center justify-center rounded-full text-xl font-bold text-on-primary shadow-button ring-4 ring-white">
            {initials(user?.name)}
          </span>
          <div className="min-w-0 sm:pt-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <p className="truncate text-lg font-bold tracking-[-0.01em] text-slate-900">{user?.name}</p>
              <Badge tone="secondary">{role.label}</Badge>
            </div>
            <p className="mt-0.5 truncate text-[13px] text-slate-500">
              {user?.email}
              {place && ` · ${place}`}
            </p>
          </div>
        </div>
        <nav
          aria-label="Settings sections"
          className="flex gap-5 overflow-x-auto border-t border-slate-100 px-5 [scrollbar-width:none] sm:gap-6"
        >
          {tabs.map((tab) => (
            <TabLink key={tab.to} {...tab} />
          ))}
        </nav>
      </Card>

      <Outlet />
    </div>
  );
};

export default SettingsLayout;
