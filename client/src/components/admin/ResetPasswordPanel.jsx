import { useState } from "react";
import toast from "react-hot-toast";
import { CheckCircleIcon } from "@heroicons/react/20/solid";
import api from "../../utils/axios";
import { Button, SlideOver } from "../ui";
import CredentialList from "./CredentialList";
import { apiError } from "../../utils/helpers";

/** Admin action: give someone a new temporary password and sign them out everywhere. */
const ResetPasswordPanel = ({ user, onClose, onReset }) => {
  const [result, setResult] = useState(null);
  const [saving, setSaving] = useState(false);

  const reset = async () => {
    setSaving(true);
    try {
      const { data } = await api.post(`/institution/users/${user.id}/reset-password`, {});
      setResult(data);
      onReset?.(data.user);
    } catch (error) {
      toast.error(apiError(error, "Couldn't reset the password. Try again."));
    } finally {
      setSaving(false);
    }
  };

  if (result) {
    return (
      <SlideOver
        open
        view="done"
        onClose={onClose}
        onDismiss={() => {}}
        title="Password reset"
        description={`${user.name} has been signed out everywhere.`}
        footer={<Button onClick={onClose}>Done</Button>}
      >
        <div className="space-y-6 p-5">
          <div role="status" tabIndex={-1} data-autofocus className="flex items-start gap-3 focus:outline-none">
            <CheckCircleIcon className="mt-0.5 size-6 shrink-0 text-emerald-600" />
            <p className="text-sm text-slate-700">
              Share the new temporary password with {user.name}. They'll choose their own at their next sign-in.
            </p>
          </div>
          <CredentialList email={result.user.email} password={result.password} />
        </div>
      </SlideOver>
    );
  }

  return (
    <SlideOver
      open
      view="confirm"
      onClose={onClose}
      title="Reset password"
      description={`${user.name} · ${user.email}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={reset} loading={saving}>
            Reset password
          </Button>
        </>
      }
    >
      <div className="space-y-3 p-5 text-sm leading-relaxed text-slate-700">
        <p>We'll generate a new temporary password for {user.name}.</p>
        <ul className="list-disc space-y-1 pl-5 text-[13px] text-slate-600">
          <li>Their current password stops working right away.</li>
          <li>They're signed out on every device.</li>
          <li>They choose a new password the next time they sign in.</li>
        </ul>
      </div>
    </SlideOver>
  );
};

export default ResetPasswordPanel;
