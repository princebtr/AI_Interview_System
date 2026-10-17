import { CheckCircleIcon, ShieldCheckIcon } from "@heroicons/react/24/outline";
import ChangePasswordForm from "../../components/ChangePasswordForm";
import { Card, CardHeader } from "../../components/ui";

const RULES = [
  "At least 6 characters; longer is stronger",
  "Upper and lowercase letters",
  "At least one number",
  "Different from your current password",
];

const PasswordTab = () => (
  <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
    <Card>
      <CardHeader title="Change password" description="Enter your current password, then choose a new one." />
      <ChangePasswordForm note="You stay signed in here; other devices are signed out." />
    </Card>

    <Card className="p-5">
      <span className="flex size-10 items-center justify-center rounded-lg bg-accent-50 text-accent-700 ring-1 ring-accent-100">
        <ShieldCheckIcon className="size-5" />
      </span>
      <h2 className="mt-4 text-[15px] font-semibold text-slate-900">A strong password</h2>
      <ul className="mt-3 space-y-2.5">
        {RULES.map((rule) => (
          <li key={rule} className="flex items-start gap-2 text-[13px] leading-snug text-slate-600">
            <CheckCircleIcon className="mt-px size-4 shrink-0 text-accent-600" />
            {rule}
          </li>
        ))}
      </ul>
      <p className="mt-4 border-t border-slate-100 pt-4 text-[12px] leading-relaxed text-slate-500">
        Forgot it? Ask your institution's administrator to reset it from Users.
      </p>
    </Card>
  </div>
);

export default PasswordTab;
