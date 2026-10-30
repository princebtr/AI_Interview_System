import api from "./axios";

// Limits mirror the server (board/views.py).
export const MAX_FILES = 5;
export const MAX_FILE_BYTES = 10 * 1024 * 1024;
export const MAX_BODY = 10000;
export const FILE_ACCEPT = ".pdf,.png,.jpg,.jpeg,.gif,.webp,.txt,.csv,.md,.doc,.docx,.ppt,.pptx,.xls,.xlsx";
const EXTENSIONS = FILE_ACCEPT.split(",");

export const KIND_META = {
  message: { label: "Message", plural: "Messages", tone: "blue" },
  note: { label: "Note", plural: "Notes", tone: "violet" },
};

/** Fired after a student opens a post, so the unread badge can refresh. */
export const READ_EVENT = "cohortix:board-read";

export const formatBytes = (bytes) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

/** Why `file` can't be attached, or null. */
export const fileProblem = (file) => {
  const dot = file.name.lastIndexOf(".");
  const extension = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
  if (!EXTENSIONS.includes(extension)) return `"${file.name}" isn't a supported file`;
  if (file.size === 0) return `"${file.name}" is empty`;
  if (file.size > MAX_FILE_BYTES) return `"${file.name}" is larger than 10 MB`;
  return null;
};

/**
 * Downloads need the Bearer token, so a plain <a href> won't do: fetch the file,
 * then hand the browser a temporary object URL to save.
 */
export const downloadAttachment = async (postId, attachment) => {
  const { data } = await api.get(`/board/posts/${postId}/attachments/${attachment.id}`, {
    responseType: "blob",
    timeout: 120000,
  });
  const url = URL.createObjectURL(data);
  const link = Object.assign(document.createElement("a"), { href: url, download: attachment.name });
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

// The fixed set of reactions (same keys and order as board.models.Reaction.KINDS).
export const REACTIONS = [
  { kind: "like", emoji: "👍", label: "Like" },
  { kind: "love", emoji: "❤️", label: "Love" },
  { kind: "celebrate", emoji: "🎉", label: "Celebrate" },
  { kind: "insightful", emoji: "💡", label: "Insightful" },
  { kind: "curious", emoji: "🤔", label: "Curious" },
  { kind: "thanks", emoji: "🙏", label: "Thanks" },
];
export const MAX_COMMENT = 2000;
