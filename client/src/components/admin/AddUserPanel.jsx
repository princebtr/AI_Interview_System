import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import { CheckCircleIcon, PlusIcon } from "@heroicons/react/20/solid";
import api from "../../utils/axios";
import { useAuth } from "../../context/AuthContext";
import { Button, Input, PasswordStrength, SlideOver } from "../ui";
import GroupPicker from "../GroupPicker";
import CredentialList from "./CredentialList";
import { apiError, cx, generatePassword } from "../../utils/helpers";
import { ROLES, roleMeta } from "../../utils/roles";
import { EMPTY_SELECTION, flatten, selectionFromPath } from "../../utils/structure";

const FORM_ID = "add-user-form";
const SERVER_FIELDS = ["name", "email", "role", "password", "cohortId", "requirePasswordChange"];
const DEFAULTS = {
  role: "student",
  name: "",
  email: "",
  password: "",
  requirePasswordChange: true,
};

/** The selection that puts a student in the cohort with that id (empty if unknown). */
const selectionForCohort = (tree, cohortId) => {
  const cohort = cohortId && flatten(tree).find((n) => n.level === "cohort" && n.id === cohortId);
  return cohort ? selectionFromPath(cohort.path) : EMPTY_SELECTION;
};

/** `tree` is the academic structure (GET /institution/structure → batches). */
const AddUserPanel = ({ onClose, tree, onCreated, initialRole = "student", initialCohortId = "" }) => {
  const { user: admin } = useAuth();
  const [created, setCreated] = useState(null);
  const [showPassword, setShowPassword] = useState(false);
  const [placement, setPlacement] = useState(() => selectionForCohort(tree, initialCohortId));
  const hasCohorts = flatten(tree).some((n) => n.level === "cohort");

  const {
    register,
    handleSubmit,
    watch,
    reset,
    setError,
    setValue,
    clearErrors,
    formState: { errors, isSubmitting, isDirty },
  } = useForm({
    defaultValues: {
      ...DEFAULTS,
      role: ROLES.some((r) => r.value === initialRole) ? initialRole : "student",
    },
  });

  const role = watch("role");
  const password = watch("password");

  const fillGeneratedPassword = () => {
    setValue("password", generatePassword(), { shouldDirty: true, shouldValidate: true });
    setShowPassword(true);
  };

  const choosePlacement = (next) => {
    setPlacement(next);
    clearErrors("cohortId");
  };

  const onSubmit = async (values) => {
    if (values.role === "student" && !placement.cohort) {
      setError("cohortId", {
        message: hasCohorts ? "Choose the student's batch, department, section and cohort" : "Set up a cohort first",
      });
      return;
    }

    const body = {
      name: values.name.trim(),
      email: values.email.trim(),
      role: values.role,
      password: values.password,
      requirePasswordChange: values.requirePasswordChange,
      ...(values.role === "student" && { cohortId: placement.cohort }),
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
    // Keep role and placement: admins usually add several people of the same kind in a row.
    reset({ ...DEFAULTS, role: created.user.role });
    setShowPassword(false);
    setCreated(null);
  };

  // Escape / backdrop: confirm before discarding what the admin typed.
  const dismissForm = () => {
    if (isDirty && !window.confirm("Discard this user? What you've entered will be lost.")) {
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
                {created.user.placement && ` · ${created.user.placement.label}`}
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
            (hasCohorts ? (
              <fieldset className="space-y-2">
                <legend className="text-sm font-medium text-slate-800">Placement</legend>
                <p className="text-[13px] text-slate-500">
                  Every student sits in one cohort. Tests assigned to any group above it reach them too.
                </p>
                <GroupPicker
                  idPrefix="new-user"
                  tree={tree}
                  value={placement}
                  onChange={choosePlacement}
                  requireCohort
                  error={errors.cohortId?.message}
                />
              </fieldset>
            ) : (
              <div className="rounded-md border border-amber-200 bg-amber-50 p-4 text-[13px] text-amber-900">
                <p className="font-medium">Set up a cohort first</p>
                <p className="mt-1 text-amber-800">
                  Students sit in a cohort within a batch, department and section.{" "}
                  <Link to="/structure" className="font-medium underline">
                    Build the academic structure
                  </Link>{" "}
                  and come back.
                </p>
                {errors.cohortId?.message && <p className="mt-1 text-red-700">{errors.cohortId.message}</p>}
              </div>
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
