import { useForm } from "react-hook-form";
import { useAuth } from "../../context/AuthContext";
import { Button, Card, CardFooter, CardHeader, Input } from "../../components/ui";
import { initials } from "../../utils/helpers";
import { roleMeta } from "../../utils/roles";

/** How the name reads in the sidebar and in other people's lists, updated as you type. */
const NamePreview = ({ name, email, role }) => (
  <Card className="p-5">
    <h2 className="text-[15px] font-semibold text-slate-900">Preview</h2>
    <p className="mt-1 text-[13px] leading-relaxed text-slate-500">
      How you appear in the sidebar and in your institution's lists.
    </p>
    <div className="mt-4 flex items-center gap-3 rounded-lg border border-slate-200/70 bg-slate-50/70 p-3">
      <span className="bg-primary flex size-9 shrink-0 items-center justify-center rounded-full text-[13px] font-bold text-on-primary">
        {initials(name || "?")}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold text-slate-900">{name || "Your name"}</span>
        <span className="block truncate text-[12px] text-slate-500">{email || "you@example.com"}</span>
      </span>
      <span className="ml-auto shrink-0 text-[12px] text-slate-400">{roleMeta(role).label}</span>
    </div>
  </Card>
);

const ProfileTab = () => {
  const { user, updateUser } = useAuth();
  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isDirty, isSubmitting },
  } = useForm({ defaultValues: { name: user?.name ?? "", email: user?.email ?? "" } });

  const onSubmit = async (data) => {
    const result = await updateUser(data);
    if (result.success) reset(data);
  };

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <Card>
        <CardHeader
          title="Personal details"
          description="Your name appears across Cohortix. Your email is how you sign in."
        />
        <form onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="grid gap-5 p-5 sm:grid-cols-2">
            <Input
              id="settings-name"
              label="Full name"
              autoComplete="name"
              error={errors.name?.message}
              {...register("name", {
                required: "Name is required",
                minLength: { value: 2, message: "Name must be at least 2 characters" },
                maxLength: { value: 50, message: "Name cannot exceed 50 characters" },
              })}
            />
            <Input
              id="settings-email"
              label="Email address"
              type="email"
              autoComplete="email"
              hint="Changing it changes how you sign in."
              error={errors.email?.message}
              {...register("email", {
                required: "Email is required",
                pattern: { value: /^\S+@\S+\.\S+$/, message: "Enter a valid email address" },
              })}
            />
          </div>
          <CardFooter>
            <p className="text-[13px] text-slate-500">
              {isDirty ? "You have unsaved changes." : "All changes saved."}
            </p>
            <div className="flex gap-2">
              {isDirty && (
                <Button variant="ghost" onClick={() => reset()} disabled={isSubmitting}>
                  Discard
                </Button>
              )}
              <Button type="submit" loading={isSubmitting} disabled={!isDirty}>
                Save changes
              </Button>
            </div>
          </CardFooter>
        </form>
      </Card>

      <NamePreview name={watch("name").trim()} email={watch("email").trim()} role={user?.role} />
    </div>
  );
};

export default ProfileTab;
