import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { TrashIcon } from "@heroicons/react/20/solid";
import api from "../../utils/axios";
import { Badge, Button } from "../ui";
import { apiError, cx, initials } from "../../utils/helpers";
import { timeAgo } from "../../utils/time";
import { MAX_COMMENT } from "../../utils/board";

const PAGE = 50;
const STAFF_LABEL = { admin: "Admin", educator: "Educator" };

/**
 * The discussion under a post: oldest first, with a box to add to it. Staff
 * comments carry a role badge so students can tell an answer from a classmate's.
 */
const CommentThread = ({ post, onCountChange, onCommented }) => {
  const [comments, setComments] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  const load = async (offset = 0) => {
    setLoading(true);
    setFailed(false);
    try {
      const { data } = await api.get(`/board/posts/${post.id}/comments`, { params: { offset, limit: PAGE } });
      setComments((prev) => (offset ? [...prev, ...data.comments] : data.comments));
      setTotal(data.total);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // Load once per opened thread.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [post.id]);

  const send = async (e) => {
    e?.preventDefault();
    if (!body.trim()) {
      setError("Write a comment first");
      return;
    }
    setSending(true);
    setError("");
    try {
      const { data } = await api.post(`/board/posts/${post.id}/comments`, { body: body.trim() });
      setComments((prev) => [...prev, data.comment]);
      setTotal((t) => t + 1);
      onCountChange(1);
      onCommented?.();
      setBody("");
    } catch (err) {
      setError(apiError(err, "Couldn't post your comment. Try again."));
    } finally {
      setSending(false);
    }
  };

  const remove = async (comment) => {
    const whose = comment.mine ? "your comment" : `${comment.author.name}'s comment`;
    if (!window.confirm(`Delete ${whose}? This can't be undone.`)) return;
    try {
      await api.delete(`/board/posts/${post.id}/comments/${comment.id}`);
      setComments((prev) => prev.filter((c) => c.id !== comment.id));
      setTotal((t) => t - 1);
      onCountChange(-1);
    } catch (err) {
      toast.error(apiError(err, "Couldn't delete the comment."));
    }
  };

  return (
    <div className="space-y-4 border-t border-slate-100 pt-4">
      {failed ? (
        <p className="text-[13px] text-slate-500">
          Couldn't load the comments.{" "}
          <button type="button" onClick={() => load()} className="font-medium text-accent-700 hover:text-accent-800">
            Try again
          </button>
        </p>
      ) : loading && comments.length === 0 ? (
        <div className="h-10 animate-pulse rounded-md bg-slate-100" />
      ) : comments.length === 0 ? (
        <p className="text-[13px] text-slate-500">
          {post.commentsEnabled !== false ? "No comments yet. Start the discussion." : "No comments."}
        </p>
      ) : (
        <ul className="space-y-3">
          {comments.map((c) => (
            <li key={c.id} className="group flex gap-3">
              <span
                className={cx(
                  "flex size-7 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold",
                  STAFF_LABEL[c.author.role] ? "bg-accent-100 text-accent-800" : "bg-slate-100 text-slate-600"
                )}
              >
                {initials(c.author.name)}
              </span>
              <div className="min-w-0 flex-1 rounded-lg bg-slate-50 px-3 py-2">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  <span className="text-[13px] font-semibold text-slate-900">{c.mine ? "You" : c.author.name}</span>
                  {STAFF_LABEL[c.author.role] && <Badge tone="brand">{STAFF_LABEL[c.author.role]}</Badge>}
                  <span className="text-[12px] text-slate-500">{timeAgo(c.createdAt)}</span>
                  {c.canDelete && (
                    <button
                      type="button"
                      onClick={() => remove(c)}
                      aria-label={`Delete ${c.mine ? "your" : `${c.author.name}'s`} comment`}
                      title="Delete comment"
                      className="ml-auto rounded p-0.5 text-slate-400 opacity-100 transition-opacity hover:text-red-600 focus:opacity-100 sm:opacity-0 sm:group-hover:opacity-100"
                    >
                      <TrashIcon className="size-3.5" />
                    </button>
                  )}
                </div>
                <p className="mt-0.5 text-sm leading-relaxed whitespace-pre-wrap text-slate-700 [overflow-wrap:anywhere]">
                  {c.body}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}

      {comments.length < total && !failed && (
        <Button variant="secondary" size="sm" loading={loading} onClick={() => load(comments.length)}>
          Show more comments
        </Button>
      )}

      {post.commentsEnabled !== false ? (
        <form onSubmit={send} noValidate className="space-y-2">
          <label htmlFor={`comment-${post.id}`} className="sr-only">
            Write a comment
          </label>
          <textarea
            id={`comment-${post.id}`}
            rows={2}
            maxLength={MAX_COMMENT}
            value={body}
            placeholder="Write a comment or ask a question…"
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? `comment-${post.id}-error` : undefined}
            onChange={(e) => {
              setBody(e.target.value);
              setError("");
            }}
            onKeyDown={(e) => (e.metaKey || e.ctrlKey) && e.key === "Enter" && send(e)}
            className={cx(
              "block w-full resize-y rounded-md border bg-white px-3 py-2 text-sm text-slate-900 shadow-xs placeholder:text-slate-400 focus:ring-3 focus:outline-none",
              error
                ? "border-red-400 focus:border-red-500 focus:ring-red-500/15"
                : "border-slate-300 focus:border-accent-600 focus:ring-accent-600/15"
            )}
          />
          <div className="flex items-center justify-between gap-3">
            <p id={`comment-${post.id}-error`} className="text-[12px] text-red-600">
              {error}
            </p>
            <Button type="submit" size="sm" loading={sending}>
              Comment
            </Button>
          </div>
        </form>
      ) : (
        <p className="text-[12px] text-slate-500">Comments are turned off for this post.</p>
      )}
    </div>
  );
};

export default CommentThread;
