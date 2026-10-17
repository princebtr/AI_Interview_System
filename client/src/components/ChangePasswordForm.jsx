import { useForm } from "react-hook-form";
import { useAuth } from "../context/AuthContext";
import { Button, CardFooter, Input, PasswordStrength } from "./ui";

/**
 * Current + new + confirm password form.
 * `variant="card"` renders inside a Card with a footer; `"page"` is a standalone form.
 */
const ChangePasswordForm = ({
  variant = "card",
  currentLabel = "Current password",
  submitLabel = "Update password",
  note = "You'll stay signed in on this device.",
  onSuccess,
}) => {
  const { updatePassword } = useAuth();
  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors, isSubmitting },
  } = useForm();
  const currentPassword = watch("currentPassword", "");
  const newPassword = watch("newPassword", "");

  const onSubmit = async ({ currentPassword, newPassword }) => {
    const result = await updatePassword({ currentPassword, newPassword });
    if (result.success) {
      reset();
      onSuccess?.();
    }
  };

  const fields = (
    <>
      <Input
        id="currentPassword"
        label={currentLabel}
        type="password"
        autoComplete="current-password"
        error={errors.currentPassword?.message}
        {...register("currentPassword", { required: `Enter your ${currentLabel.toLowerCase()}` })}
      />
      <div>
        <Input
          id="newPassword"
          label="New password"
          type="password"
          autoComplete="new-password"
          error={errors.newPassword?.message}
          {...register("newPassword", {
            required: "Enter a new password",
            minLength: { value: 6, message: "Use at least 6 characters" },
            pattern: {
              value: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/,
              message: "Include a lowercase letter, an uppercase letter and a number",
            },
            validate: (v) => v !== currentPassword || "Choose a password different from the current one",
          })}
        />
        <PasswordStrength password={newPassword} />
      </div>
      <Input
        id="confirmNewPassword"
        label="Confirm new password"
        type="password"
        autoComplete="new-password"
        error={errors.confirmNewPassword?.message}
        {...register("confirmNewPassword", {
          required: "Confirm your new password",
          validate: (v) => v === newPassword || "Passwords don't match",
        })}
      />
    </>
  );

  if (variant === "page") {
    return (
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
        {fields}
        <Button type="submit" size="lg" loading={isSubmitting} className="w-full">
          {submitLabel}
        </Button>
      </form>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate>
      <div className="space-y-5 p-5">{fields}</div>
      <CardFooter>
        <p className="text-[13px] text-slate-500">{note}</p>
        <Button type="submit" loading={isSubmitting}>
          {submitLabel}
        </Button>
      </CardFooter>
    </form>
  );
};

export default ChangePasswordForm;
