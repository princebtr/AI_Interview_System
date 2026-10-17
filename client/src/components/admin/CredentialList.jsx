import { useAuth } from "../../context/AuthContext";
import { CopyButton } from "../ui";
import { cx } from "../../utils/helpers";

const Row = ({ label, value, mono = false }) => (
  <div className="flex items-center justify-between gap-3 px-3.5 py-2.5">
    <div className="min-w-0">
      <dt className="text-[12px] text-slate-500">{label}</dt>
      <dd
        className={cx("truncate text-sm text-slate-900", mono && "font-mono")}
      >
        {value}
      </dd>
    </div>
    <CopyButton value={value} label={`Copy ${label.toLowerCase()}`} />
  </div>
);

/** Sign-in details to hand to a person after creating their account or resetting their password. */
const CredentialList = ({ email, password, requirePasswordChange = true }) => {
  const { user } = useAuth();
  const slug = user?.institution?.slug;
  const signIn = `${window.location.origin}/login${slug ? `?school=${encodeURIComponent(slug)}` : ""}`;
  return (
    <div>
      <p className="mb-2 text-sm font-medium text-slate-800">Sign-in details</p>
      <dl className="divide-y divide-slate-100 rounded-md border border-slate-200 bg-slate-50/60">
        <Row label="Email" value={email} />
        <Row label="Password" value={password} mono />
        <Row label="Sign-in link" value={signIn} />
      </dl>
      <p className="mt-2 text-[13px] leading-relaxed text-slate-500">
        Share these over a secure channel. The password isn't shown again.
        {requirePasswordChange &&
          " They'll be asked to choose their own password the first time they sign in."}
      </p>
    </div>
  );
};

export default CredentialList;
