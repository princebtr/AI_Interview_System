import { useRef, useState } from "react";
import toast from "react-hot-toast";
import { DocumentArrowUpIcon, PaperClipIcon, XMarkIcon } from "@heroicons/react/20/solid";
import api from "../../utils/axios";
import { Button, Input, SlideOver, Textarea } from "../ui";
import GroupPicker from "../GroupPicker";
import { apiError, cx } from "../../utils/helpers";
import { EMPTY_SELECTION, LEVEL_META, deepest, selectedNode, selectionFromPath } from "../../utils/structure";
import { FILE_ACCEPT, KIND_META, MAX_BODY, MAX_FILES, fileProblem, formatBytes } from "../../utils/board";

const FORM_ID = "post-form";
const FIELDS = ["kind", "title", "body", "audience", "files"];
// The axios instance defaults to JSON, which would turn FormData into JSON.
const MULTIPART = { headers: { "Content-Type": "multipart/form-data" }, timeout: 120000 };

/**
 * Share a message or note with a batch, department, section or cohort, or edit
 * one (`post`). New files go up with a new post; when editing, they're
 * uploaded and removed straight away.
 */
const PostComposer = ({ post, tree, onClose, onSaved }) => {
  const editing = Boolean(post);
  const [kind, setKind] = useState(post?.kind ?? "message");
  const [title, setTitle] = useState(post?.title ?? "");
  const [body, setBody] = useState(post?.body ?? "");
  const [pinned, setPinned] = useState(post?.pinned ?? false);
  const [commentsEnabled, setCommentsEnabled] = useState(post?.commentsEnabled !== false);
  const [audience, setAudience] = useState(() => (post ? selectionFromPath(post.audience.path) : EMPTY_SELECTION));
  const [files, setFiles] = useState([]); // new files (create mode)
  const [attachments, setAttachments] = useState(post?.attachments ?? []); // saved files (edit mode)
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef(null);

  const target = deepest(audience);
  const node = selectedNode(tree, audience);
  const fileCount = editing ? attachments.length : files.length;
  const dirty =
    title !== (post?.title ?? "") || body !== (post?.body ?? "") || files.length > 0 || (!editing && target);

  const clearError = (field) => setErrors((e) => ({ ...e, [field]: undefined }));

  const pickFiles = async (list) => {
    const chosen = [...(list ?? [])];
    if (fileInput.current) fileInput.current.value = "";
    if (!chosen.length) return;
    const problem = chosen.map(fileProblem).find(Boolean);
    if (problem) {
      setErrors((e) => ({ ...e, files: problem }));
      return;
    }
    if (fileCount + chosen.length > MAX_FILES) {
      setErrors((e) => ({ ...e, files: `Attach at most ${MAX_FILES} files` }));
      return;
    }
    clearError("files");
    if (!editing) {
      setFiles((prev) => [...prev, ...chosen]);
      return;
    }
    setUploading(true);
    try {
      const form = new FormData();
      chosen.forEach((f) => form.append("files", f));
      const { data } = await api.post(`/board/posts/${post.id}/attachments`, form, MULTIPART);
      setAttachments(data.post.attachments);
      onSaved(data.post, { keepOpen: true });
    } catch (err) {
      setErrors((e) => ({ ...e, files: apiError(err, "Couldn't upload the file. Try again.") }));
    } finally {
      setUploading(false);
    }
  };

  const removeAttachment = async (attachment) => {
    if (!window.confirm(`Remove "${attachment.name}"? Students will no longer be able to download it.`)) return;
    try {
      await api.delete(`/board/posts/${post.id}/attachments/${attachment.id}`);
      const remaining = attachments.filter((a) => a.id !== attachment.id);
      setAttachments(remaining);
      onSaved({ ...post, attachments: remaining }, { keepOpen: true });
    } catch (err) {
      toast.error(apiError(err, "Couldn't remove the file."));
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    const problems = {};
    if (!title.trim()) problems.title = "Add a title";
    if (!target) problems.audience = "Choose who can see this";
    if (!editing && kind === "message" && !body.trim() && files.length === 0) {
      problems.body = "Write a message or attach a file";
    }
    if (Object.keys(problems).length) {
      setErrors(problems);
      return;
    }

    setSaving(true);
    setErrors({});
    try {
      let saved;
      if (editing) {
        ({ data: { post: saved } } = await api.patch(`/board/posts/${post.id}`, {
          title: title.trim(),
          body: body.trim(),
          pinned,
          commentsEnabled,
          audience: target,
        }));
      } else {
        const form = new FormData();
        form.append("kind", kind);
        form.append("title", title.trim());
        form.append("body", body.trim());
        form.append("pinned", pinned ? "true" : "false");
        form.append("commentsEnabled", commentsEnabled ? "true" : "false");
        form.append("audienceLevel", target.level);
        form.append("audienceId", target.id);
        files.forEach((f) => form.append("files", f));
        ({ data: { post: saved } } = await api.post("/board/posts", form, MULTIPART));
      }
      toast.success(editing ? "Saved" : `Shared with ${saved.audience.label}`);
      onSaved(saved);
    } catch (err) {
      const fieldErrors = (err.response?.data?.errors ?? []).filter((x) => FIELDS.includes(x.field));
      if (fieldErrors.length) setErrors(Object.fromEntries(fieldErrors.map((x) => [x.field, x.message])));
      else toast.error(apiError(err, "Couldn't save. Try again."));
      setSaving(false);
    }
  };

  const dismiss = () => {
    if (dirty && !window.confirm("Discard this post? What you've written will be lost.")) return;
    onClose();
  };

  const fileList = editing ? attachments : files.map((f, i) => ({ id: `new-${i}`, name: f.name, size: f.size }));

  return (
    <SlideOver
      open
      onClose={onClose}
      onDismiss={dismiss}
      title={editing ? `Edit ${KIND_META[post.kind].label.toLowerCase()}` : "New post"}
      description="Students see it in Notes & Messages. Everyone under the group you choose can read it."
      footer={
        <>
          <Button variant="secondary" onClick={dismiss}>
            Cancel
          </Button>
          <Button type="submit" form={FORM_ID} loading={saving} disabled={uploading}>
            {editing ? "Save changes" : "Share"}
          </Button>
        </>
      }
    >
      <form id={FORM_ID} onSubmit={submit} noValidate className="space-y-6 p-5">
        {!editing && (
          <fieldset>
            <legend className="mb-2 text-sm font-medium text-slate-800">Type</legend>
            <div className="grid grid-cols-2 gap-2">
              {[
                ["message", "An announcement or reminder"],
                ["note", "Study material, with files if you like"],
              ].map(([value, description]) => (
                <label
                  key={value}
                  className={cx(
                    "flex cursor-pointer items-start gap-2.5 rounded-md border px-3 py-2.5 transition-colors",
                    kind === value
                      ? "border-accent-600 bg-accent-50/60"
                      : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                  )}
                >
                  <input
                    type="radio"
                    name="kind"
                    value={value}
                    checked={kind === value}
                    onChange={() => {
                      setKind(value);
                      clearError("body");
                    }}
                    className="mt-0.5 size-4 accent-accent-700"
                  />
                  <span>
                    <span className="block text-sm font-medium text-slate-900">{KIND_META[value].label}</span>
                    <span className="block text-[12px] text-slate-500">{description}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        )}

        <fieldset className="space-y-2">
          <legend className="text-sm font-medium text-slate-800">Share with</legend>
          <p className="text-[13px] text-slate-500">
            Stop at any level: a whole batch, a department, a section or one cohort.
          </p>
          <GroupPicker
            idPrefix="post-audience"
            tree={tree}
            value={audience}
            showCounts
            error={errors.audience}
            onChange={(next) => {
              setAudience(next);
              clearError("audience");
            }}
          />
          {node && (
            <p className="text-[13px] text-slate-600">
              {LEVEL_META[node.level].label} <span className="font-medium text-slate-900">{node.label}</span> ·{" "}
              {node.studentCount} student{node.studentCount === 1 ? "" : "s"}
            </p>
          )}
        </fieldset>

        <Input
          id="post-title"
          label="Title"
          maxLength={200}
          placeholder={kind === "note" ? "e.g. Unit 3 notes: Linked lists" : "e.g. Lab moved to Thursday"}
          value={title}
          error={errors.title}
          onChange={(e) => {
            setTitle(e.target.value);
            clearError("title");
          }}
        />
        <Textarea
          id="post-body"
          label={kind === "note" ? "Notes (optional)" : "Message"}
          rows={8}
          maxLength={MAX_BODY}
          placeholder={kind === "note" ? "Summary, key points or reading instructions." : "Write your message."}
          hint={`${body.length.toLocaleString()} / ${MAX_BODY.toLocaleString()} characters`}
          value={body}
          error={errors.body}
          onChange={(e) => {
            setBody(e.target.value);
            clearError("body");
          }}
        />

        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-sm font-semibold text-slate-700">Files</span>
            <span className="text-[12px] text-slate-500">
              {fileCount} / {MAX_FILES} · PDF, Office, images or text, up to 10 MB each
            </span>
          </div>
          {fileList.length > 0 && (
            <ul className="mb-2 divide-y divide-slate-100 rounded-md border border-slate-200">
              {fileList.map((file, i) => (
                <li key={file.id} className="flex items-center gap-2 px-3 py-2 text-sm">
                  <PaperClipIcon className="size-4 shrink-0 text-slate-400" />
                  <span className="min-w-0 flex-1 truncate text-slate-800">{file.name}</span>
                  <span className="text-[12px] text-slate-500 tabular-nums">{formatBytes(file.size)}</span>
                  <button
                    type="button"
                    aria-label={`Remove ${file.name}`}
                    onClick={() =>
                      editing ? removeAttachment(file) : setFiles((prev) => prev.filter((_, j) => j !== i))
                    }
                    className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600"
                  >
                    <XMarkIcon className="size-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          {fileCount < MAX_FILES && (
            <label
              htmlFor="post-files"
              className={cx(
                "flex cursor-pointer items-center justify-center gap-2 rounded-md border border-dashed px-3 py-4 text-[13px] font-medium transition-colors",
                errors.files ? "border-red-400 text-red-700" : "border-slate-300 text-slate-600 hover:bg-slate-50"
              )}
            >
              <DocumentArrowUpIcon className="size-4" />
              {uploading ? "Uploading…" : "Attach files"}
              <input
                ref={fileInput}
                id="post-files"
                type="file"
                multiple
                accept={FILE_ACCEPT}
                className="sr-only"
                disabled={uploading}
                onChange={(e) => pickFiles(e.target.files)}
              />
            </label>
          )}
          {errors.files && <p className="mt-1.5 text-[13px] text-red-600">{errors.files}</p>}
        </div>

        <label className="flex items-start gap-2.5 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={pinned}
            onChange={(e) => setPinned(e.target.checked)}
            className="mt-0.5 size-4 rounded border-slate-300 accent-accent-700"
          />
          <span>
            Pin to the top
            <span className="block text-[13px] text-slate-500">Pinned posts stay above newer ones.</span>
          </span>
        </label>

        <label className="flex items-start gap-2.5 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={commentsEnabled}
            onChange={(e) => setCommentsEnabled(e.target.checked)}
            className="mt-0.5 size-4 rounded border-slate-300 accent-accent-700"
          />
          <span>
            Allow comments
            <span className="block text-[13px] text-slate-500">
              Students can ask questions and discuss. Everyone can still react.
            </span>
          </span>
        </label>
      </form>
    </SlideOver>
  );
};

export default PostComposer;
