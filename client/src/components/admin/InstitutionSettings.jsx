import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import toast from "react-hot-toast";
import { ArrowUpTrayIcon } from "@heroicons/react/20/solid";
import api from "../../utils/axios";
import { useAuth } from "../../context/AuthContext";
import { Button, CardFooter, InstitutionLogo, Input, PoweredBy } from "../ui";
import { apiError } from "../../utils/helpers";

const ACCEPT = "image/png,image/jpeg,image/webp";

/** Admin-only: the logo and details everyone in the institution sees. */
const InstitutionSettings = () => {
  const { user, updateInstitution } = useAuth();
  const institution = user?.institution;
  const fileRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [removing, setRemoving] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isDirty, isSubmitting },
  } = useForm({
    defaultValues: {
      name: institution?.name ?? "",
      academicYear: institution?.academicYear ?? "",
      website: institution?.website ?? "",
    },
  });

  const upload = async (file) => {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      toast.error("The logo must be 2 MB or smaller.");
      return;
    }
    setUploading(true);
    try {
      const form = new FormData();
      form.append("logo", file);
      const { data } = await api.post("/institution/logo", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      updateInstitution(data.institution);
      toast.success("Logo updated");
    } catch (error) {
      toast.error(apiError(error, "Couldn't upload the logo. Try another image."));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const removeLogo = async () => {
    if (!window.confirm("Remove the logo? Your institution's initials will be shown instead.")) return;
    setRemoving(true);
    try {
      const { data } = await api.delete("/institution/logo");
      updateInstitution(data.institution);
      toast.success("Logo removed");
    } catch (error) {
      toast.error(apiError(error, "Couldn't remove the logo."));
    } finally {
      setRemoving(false);
    }
  };

  const onSubmit = async (values) => {
    try {
      const { data } = await api.patch("/institution", {
        name: values.name.trim(),
        academicYear: values.academicYear.trim(),
        website: values.website.trim(),
      });
      updateInstitution(data.institution);
      reset({
        name: data.institution.name,
        academicYear: data.institution.academicYear,
        website: data.institution.website,
      });
      toast.success("Institution details saved");
    } catch (error) {
      const fields = { name: "name", academicYear: "academicYear", website: "website" };
      const known = (error.response?.data?.errors ?? []).filter((e) => fields[e.field]);
      known.forEach(({ field, message }, i) => setError(fields[field], { message }, { shouldFocus: i === 0 }));
      if (!known.length) toast.error(apiError(error, "Couldn't save the details."));
    }
  };

  return (
    <>
      <div className="flex flex-col gap-5 border-b border-slate-100 p-5 sm:flex-row sm:items-center">
        <InstitutionLogo institution={institution} className="size-20" initialsClassName="text-xl" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-slate-900">Logo</p>
          <p className="mt-0.5 text-[13px] leading-relaxed text-slate-500">
            Shown at the top of Cohortix for everyone in your institution, and on your sign-in page.
            PNG, JPG or WebP, up to 2 MB. Square images look best.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <input
              ref={fileRef}
              id="institution-logo"
              type="file"
              accept={ACCEPT}
              className="sr-only"
              onChange={(e) => upload(e.target.files?.[0])}
            />
            <Button variant="secondary" loading={uploading} onClick={() => fileRef.current?.click()}>
              {!uploading && <ArrowUpTrayIcon className="size-4" />}
              {institution?.logoUrl ? "Replace logo" : "Upload logo"}
            </Button>
            {institution?.logoUrl && (
              <Button variant="ghost" loading={removing} onClick={removeLogo}>
                Remove
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Live preview of the sidebar header. */}
      <div className="border-b border-slate-100 bg-slate-50/60 px-5 py-4">
        <p className="mb-2 text-[12px] font-medium tracking-wide text-slate-400 uppercase">Preview</p>
        <div className="flex max-w-xs items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2.5">
          <InstitutionLogo institution={institution} className="size-9" />
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold text-slate-900">{institution?.name}</span>
            <PoweredBy className="mt-1" />
          </span>
        </div>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <div className="grid gap-5 p-5 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Input
              id="institution-name"
              label="Institution name"
              error={errors.name?.message}
              {...register("name", {
                validate: (v) => (v.trim().length >= 2 && v.trim().length <= 150) || "Use 2-150 characters",
              })}
            />
          </div>
          <Input
            id="institution-year"
            label="Academic year"
            placeholder="2026-27"
            error={errors.academicYear?.message}
            {...register("academicYear", {
              pattern: { value: /^\s*\d{4}-(\d{2}|\d{4})\s*$/, message: "Use the format 2026-27" },
            })}
          />
          <Input
            id="institution-website"
            label="Website (optional)"
            placeholder="example.edu"
            error={errors.website?.message}
            {...register("website")}
          />
        </div>
        <CardFooter>
          <p className="text-[13px] text-slate-500">Your sign-in page: /login?school={institution?.slug}</p>
          <Button type="submit" loading={isSubmitting} disabled={!isDirty}>
            Save details
          </Button>
        </CardFooter>
      </form>
    </>
  );
};

export default InstitutionSettings;
