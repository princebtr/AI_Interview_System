import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRightStartOnRectangleIcon,
  ComputerDesktopIcon,
  DevicePhoneMobileIcon,
} from "@heroicons/react/24/outline";
import { useAuth } from "../../context/AuthContext";
import { Badge, Button, Card, CardHeader, InstitutionLogo } from "../../components/ui";
import { formatDate } from "../../utils/helpers";
import { roleMeta } from "../../utils/roles";
import { timeAgo } from "../../utils/time";

const longDate = (value) => (value ? formatDate(value, { day: "numeric", month: "long", year: "numeric" }) : "—");

const Row = ({ label, children }) => (
  <div className="flex flex-col gap-1 px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
    <dt className="text-[13px] text-slate-500">{label}</dt>
    <dd className="text-sm text-slate-900">{children}</dd>
  </div>
);

const SessionsCard = () => {
  const { logout, logoutEverywhere } = useAuth();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  const signOutEverywhere = async () => {
    setBusy(true);
    const { success } = await logoutEverywhere();
    if (!success) setBusy(false); // on success the app returns to the sign-in page
  };

  return (
    <Card>
      <CardHeader title="Sign-in sessions" description="Where you're signed in to Cohortix." />
      <div className="divide-y divide-slate-100">
        <div className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent-50 text-accent-700 ring-1 ring-accent-100">
              <ComputerDesktopIcon className="size-5" />
            </span>
            <div>
              <p className="text-sm font-semibold text-slate-900">This device</p>
              <p className="mt-0.5 text-[13px] text-slate-500">Sign out here only. Other devices stay signed in.</p>
            </div>
          </div>
          <Button variant="secondary" onClick={logout}>
            <ArrowRightStartOnRectangleIcon className="size-4" />
            Sign out
          </Button>
        </div>

        <div className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-red-50 text-red-600 ring-1 ring-red-100">
              <DevicePhoneMobileIcon className="size-5" />
            </span>
            <div>
              <p className="text-sm font-semibold text-slate-900">All devices</p>
              <p className="mt-0.5 max-w-md text-[13px] leading-relaxed text-slate-500">
                {confirming
                  ? "Every browser and phone signed in to your account, including this one, will need your password again."
                  : "Use this if you signed in on a shared computer or lost a device."}
              </p>
            </div>
          </div>
          {confirming ? (
            <div className="flex shrink-0 gap-2">
              <Button variant="ghost" onClick={() => setConfirming(false)} disabled={busy}>
                Cancel
              </Button>
              <Button variant="danger" onClick={signOutEverywhere} loading={busy} autoFocus>
                Sign out everywhere
              </Button>
            </div>
          ) : (
            <Button variant="danger" onClick={() => setConfirming(true)}>
              Sign out of all devices
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
};

const AccountTab = () => {
  const { user } = useAuth();
  const role = roleMeta(user?.role);
  const isAdmin = user?.role === "admin";

  return (
    <div className="grid items-start gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader
          title="Account details"
          description={
            isAdmin
              ? "You can change roles and placements for everyone from Users."
              : "Your institution, role and placement are managed by your administrator."
          }
          action={
            isAdmin && (
              <Link to="/users" className="shrink-0 text-[13px] font-semibold text-accent-700 hover:text-accent-800">
                Manage users
              </Link>
            )
          }
        />
        <dl className="divide-y divide-slate-100">
          <Row label="Institution">
            <span className="flex items-center gap-2">
              <InstitutionLogo institution={user?.institution} className="size-6" initialsClassName="text-[9px]" />
              {user?.institution?.name ?? "—"}
            </span>
          </Row>
          <Row label="Role">
            <Badge tone={role.tone}>{role.label}</Badge>
          </Row>
          {user?.role === "student" && (
            <Row label="Batch · Department · Section · Cohort">{user?.placement?.label ?? "Not assigned yet"}</Row>
          )}
          <Row label="Email">
            <span className="flex items-center gap-2">
              <span className="truncate">{user?.email}</span>
              {user?.isEmailVerified ? (
                <Badge tone="success">Verified</Badge>
              ) : (
                <Badge tone="warning">Not verified</Badge>
              )}
            </span>
          </Row>
          <Row label="Member since">{longDate(user?.createdAt)}</Row>
          <Row label="Last sign-in">
            {user?.lastLogin ? (
              <span title={longDate(user.lastLogin)}>{timeAgo(user.lastLogin)}</span>
            ) : (
              "—"
            )}
          </Row>
        </dl>
      </Card>

      <SessionsCard />
    </div>
  );
};

export default AccountTab;
