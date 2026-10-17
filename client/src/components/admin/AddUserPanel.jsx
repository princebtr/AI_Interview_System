import { useState } from "react";
import { useForm } from "react-hook-form";
import toast from "react-hot-toast";
import { CheckCircleIcon, PlusIcon } from "@heroicons/react/20/solid";
import api from "../../utils/axios";
import { useAuth } from "../../context/AuthContext";
import { Button, Field, Input, PasswordStrength, Select, SlideOver } from "../ui";
import CredentialList from "./CredentialList";
import { apiError, cx, generatePassword } from "../../utils/helpers";
import { ROLES, roleMeta } from "../../utils/roles";

const FORM_ID = "add-user-form";
const SERVER_FIELDS = ["name", "email", "role", "password", "cohortId", "requirePasswordChange"];
const DEFAULTS = {
  role: "student",
  name: "",
  email: "",
  cohortId: "",
  password: "",
  requirePasswordChange: true,
};

/** Inline "new cohort" field, so admins can create a student's cohort without leaving the form. */
const NewCohort = ({ name, onNameChange, onCreated, onCancel, canCancel, error: formError }) => {
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const shownError = error || formError;

  const create = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Enter a cohort name");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const { data } = await api.post("/institution/cohorts", { name: trimmed });
      toast.success(`Cohort "${data.cohort.name}" created`);
      onCreated(data.cohort);
    } catch (err) {
      setError(apiError(err, "Couldn't create the cohort. Try again."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Field
      id="new-cohort-name"
      label="New cohort"
      error={shownError}
      hint="Group students who study together, e.g. CSE-2027."
      action={
        canCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="text-[13px] font-medium text-slate-500 hover:text-slate-800"
          >
            Choose existing
          </button>
        )
      }
    >
      <div className="flex gap-2">
        <input
          id="new-cohort-name"
          value={name}
          maxLength={60}
          autoFocus={canCancel}
          placeholder="Cohort name"
          aria-invalid={shownError ? true : undefined}
          aria-describedby={shownError ? "new-cohort-name-error" : "new-cohort-name-hint"}
          onChange={(e) => {
            setError("");
            onNameChange(e.target.value);
          }}
          onKeyDown={(e) => {
            // Enter would otherwise submit the whole add-user form.
            if (e.key === "Enter") {
              e.preventDefault();
              create();
            }
          }}
          className={cx(
            "block h-10 w-full rounded-md border bg-white px-3 text-sm text-slate-900 shadow-xs placeholder:text-slate-400 focus:ring-3 focus:outline-none",
            shownError
              ? "border-red-400 focus:border-red-500 focus:ring-red-500/15"
              : "border-slate-300 focus:border-accent-600 focus:ring-accent-600/15"
          )}
        />
        <Button variant="secondary" onClick={create} loading={saving} className="h-10">
          Create
        </Button>
      </div>
    </Field>
  );
};

const AddUserPanel = ({
  onClose,
  cohorts,
  onCohortCreated,
  onCreated,
  initialRole = "student",
  initialCohortId = "",
}) => {
  const { user: admin } = useAuth();
  const [created, setCreated] = useState(null);
  const [showPassword, setShowPassword] = useState(false);
  const [addingCohort, setAddingCohort] = useState(false);
  const [newCohortName, setNewCohortName] = useState("");
  const [previousCohort, setPreviousCohort] = useState("");
  const [focusCohortSelect, setFocusCohortSelect] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    reset,
    getValues,
    setError,
    setValue,
    clearErrors,
    formState: { errors, isSubmitting, isDirty },
  } = useForm({
    defaultValues: {
      ...DEFAULTS,
      role: ROLES.some((r) => r.value === initialRole) ? initialRole : "student",
      cohortId: cohorts.some((c) => c.id === initialCohortId) ? initialCohortId : "",
    },
  });

  const role = watch("role");
  const password = watch("password");
  const showCohortCreator = addingCohort || cohorts.length === 0;

  const fillGeneratedPassword = () => {
    setValue("password", generatePassword(), { shouldDirty: true, shouldValidate: true });
    setShowPassword(true);
  };

  // Never keep a cohort selected that the admin can no longer see.
  const startNewCohort = () => {
    setPreviousCohort(getValues("cohortId"));
    setValue("cohortId", "");
    clearErrors("cohortId");
    setAddingCohort(true);
  };

  const cancelNewCohort = () => {
    setValue("cohortId", previousCohort);
    setNewCohortName("");
    setAddingCohort(false);
    setFocusCohortSelect(true);
  };

  const handleCohortCreated = (cohort) => {
    onCohortCreated(cohort);
    setValue("cohortId", cohort.id, { shouldDirty: true });
    clearErrors("cohortId");
    setNewCohortName("");
    setAddingCohort(false);
    setFocusCohortSelect(true);
  };

  const onSubmit = async (values) => {
    if (values.role === "student") {
      if (showCohortCreator) {
        const pending = newCohortName.trim();
        setError("cohortId", {
          message: pending
            ? `Press Create to add "${pending}" first, or choose an existing cohort.`
            : "Create a cohort for this student first.",
        });
        document.getElementById("new-cohort-name")?.focus();
        return;
      }
      if (!values.cohortId) {
        setError("cohortId", { message: "Choose a cohort for this student" }, { shouldFocus: true });
        return;
      }
    }

    const body = {
      name: values.name.trim(),
      email: values.email.trim(),
      role: values.role,
      password: values.password,
      requirePasswordChange: values.requirePasswordChange,
      ...(values.role === "student" && { cohortId: values.cohortId }),
    };

    try {
      const { data } = await api.post("/institution/users", body);
      setCreated({
        user: data.user,
        password: values.password,
        requirePasswordChange: values.requirePasswordChange,
      });
      onCreated(data.user);
    } catch (error) {
      const fieldErrors = error.response?.data?.errors;
      const known = Array.isArray(fieldErrors)
        ? fieldErrors.filter((e) => SERVER_FIELDS.includes(e.field))
        : [];
      known.forEach(({ field, message }, i) => setError(field, { message }, { shouldFocus: i === 0 }));
      if (!known.length) toast.error(apiError(error, "Couldn't add the user. Try again."));
    }
  };

  const addAnother = () => {
    // Keep role and cohort: admins usually add several people of the same kind in a row.
    reset({ ...DEFAULTS, role: created.user.role, cohortId: created.user.cohort?.id ?? "" });
    setShowPassword(false);
    setFocusCohortSelect(false);
    setCreated(null);
  };

  // Escape / backdrop: confirm before discarding what the admin typed.
  const dismissForm = () => {
    if ((isDirty || newCohortName) && !window.confirm("Discard this user? What you've entered will be lost.")) {
      return;
    }
    onClose();
  };

  const institution = admin?.institution?.name ?? "your institution";

  if (created) {
    const meta = roleMeta(created.user.role);
    return (
      <SlideOver
        open
        view="created"
        onClose={onClose}
        // The password is shown only here, so ignore Escape and stray backdrop clicks.
        onDismiss={() => {}}
        title="User added"
        description={`They can sign in to ${institution} now.`}
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>
              Done
            </Button>
            <Button onClick={addAnother}>
              <PlusIcon className="size-4" />
              Add another
            </Button>
          </>
        }
      >
        <div className="space-y-6 p-5">
          <div
            role="status"
            tabIndex={-1}
            data-autofocus
            className="flex items-start gap-3 rounded-md focus:outline-none"
          >
            <CheckCircleIcon className="mt-0.5 size-6 shrink-0 text-emerald-600" />
            <div>
              <p className="text-sm font-medium text-slate-900">{created.user.name} was added</p>
              <p className="text-[13px] text-slate-500">
                {meta.label}
                {created.user.cohort && ` · ${created.user.cohort.name}`}
              </p>
            </div>
          </div>
          <CredentialList
            email={created.user.email}
            password={created.password}
            requirePasswordChange={created.requirePasswordChange}
          />
        </div>
      </SlideOver>
    );
  }

  return (
    <SlideOver
      open
      view="form"
      onClose={onClose}
      onDismiss={dismissForm}
      title="Add user"
      description={`Create an account in ${institution}.`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form={FORM_ID} loading={isSubmitting}>
            Add user
          </Button>
        </>
      }
    >
      <form id={FORM_ID} onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-6 p-5">
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-slate-800">Role</legend>
          <div className="space-y-2">
            {ROLES.map((option) => (
              <label
                key={option.value}
                className={cx(
                  "flex cursor-pointer items-start gap-3 rounded-md border px-3.5 py-3 transition-colors",
                  role === option.value
                    ? "border-accent-600 bg-accent-50/60"
                    : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                )}
              >
                <input
                  type="radio"
                  value={option.value}
                  className="mt-0.5 size-4 accent-accent-700"
                  {...register("role", { onChange: () => clearErrors("cohortId") })}
                />
                <span>
                  <span className="block text-sm font-medium text-slate-900">{option.label}</span>
                  <span className="block text-[13px] text-slate-500">{option.description}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="space-y-4">
          <Input
            id="new-user-name"
            label="Full name"
            autoComplete="off"
            placeholder="e.g. Rahul Sharma"
            error={errors.name?.message}
            {...register("name", {
              required: "Enter their full name",
              validate: (v) => {
                const length = v.trim().length;
                if (length < 2) return "Name must be at least 2 characters";
                if (length > 50) return "Name cannot exceed 50 characters";
                return true;
              },
            })}
          />
          <Input
            id="new-user-email"
            label="Email"
            type="email"
            autoComplete="off"
            placeholder="name@example.com"
            hint="They'll sign in with this email."
            error={errors.email?.message}
            {...register("email", {
              required: "Enter their email",
              pattern: { value: /^\s*\S+@\S+\.\S+\s*$/, message: "Enter a valid email address" },
            })}
          />

          {role === "student" &&
            (showCohortCreator ? (
              <NewCohort
                name={newCohortName}
                onNameChange={setNewCohortName}
                canCancel={cohorts.length > 0}
                onCancel={cancelNewCohort}
                onCreated={handleCohortCreated}
                error={errors.cohortId?.message}
              />
            ) : (
              <Select
                id="new-user-cohort"
                label="Cohort"
                autoFocus={focusCohortSelect}
                error={errors.cohortId?.message}
                action={
                  <button
                    type="button"
                    onClick={startNewCohort}
                    className="text-[13px] font-medium text-accent-700 hover:text-accent-800"
                  >
                    New cohort
                  </button>
                }
                {...register("cohortId", { onChange: () => clearErrors("cohortId") })}
              >
                <option value="">Choose a cohort</option>
                {cohorts.map((cohort) => (
                  <option key={cohort.id} value={cohort.id}>
                    {cohort.name}
                  </option>
                ))}
              </Select>
            ))}
        </div>

        <div className="space-y-4">
          <div>
            <Input
              id="new-user-password"
              label="Password"
              type="password"
              autoComplete="new-password"
              revealed={showPassword}
              onRevealedChange={setShowPassword}
              hint={password ? undefined : "At least 6 characters, with upper and lowercase letters and a number."}
              error={errors.password?.message}
              action={
                <button
                  type="button"
                  onClick={fillGeneratedPassword}
                  className="text-[13px] font-medium text-accent-700 hover:text-accent-800"
                >
                  Generate
                </button>
              }
              {...register("password", {
                required: "Set a password",
                minLength: { value: 6, message: "Use at least 6 characters" },
                maxLength: { value: 72, message: "Use at most 72 characters" },
                pattern: {
                  value: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/,
                  message: "Include a lowercase letter, an uppercase letter and a number",
                },
              })}
            />
            <PasswordStrength password={password} />
          </div>

          <label className="flex items-start gap-2.5 text-sm text-slate-700">
            <input
              type="checkbox"
              className="mt-0.5 size-4 rounded border-slate-300 accent-accent-700"
              {...register("requirePasswordChange")}
            />
            <span>
              Ask them to choose a new password at first sign-in
              <span className="block text-[13px] text-slate-500">
                Recommended, so only they know their password.
              </span>
            </span>
          </label>
        </div>
      </form>
    </SlideOver>
  );
};

export default AddUserPanel;
