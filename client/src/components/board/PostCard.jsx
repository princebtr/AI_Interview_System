import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import {
  ArrowDownTrayIcon,
  ChatBubbleLeftIcon,
  EyeIcon,
  PaperClipIcon,
  PencilSquareIcon,
  TrashIcon,
} from "@heroicons/react/20/solid";
import { MapPinIcon } from "@heroicons/react/24/solid";
import { Badge, Card } from "../ui";
import { apiError, cx } from "../../utils/helpers";
import { timeAgo } from "../../utils/time";
import { KIND_META, READ_EVENT, downloadAttachment, formatBytes } from "../../utils/board";
import CommentThread from "./CommentThread";
import Reactions from "./Reactions";

const PREVIEW_CHARS = 280;

const IconButton = ({ label, onClick, danger, active, children }) => (
  <button
    type="button"
    onClick={onClick}
    aria-label={label}
    title={label}
    aria-pressed={active}
    className={cx(
      "rounded-md p-1.5 transition-colors",
      active ? "text-accent-700" : "text-slate-400",
      danger ? "hover:bg-red-50 hover:text-red-600" : "hover:bg-slate-100 hover:text-slate-700"
    )}
  >
    {children}
  </button>
);

/**
 * One note or message. Students: a short post counts as read once it has been
 * on screen; a long one when they open it with "Read more" or download a file
 * (`onRead`). Staff: pin, edit and delete when
 * they're allowed to (`post.canEdit`), plus how many students have opened it.
 */
const PostCard = ({ post, staff, onRead, onUpdate, onEdit, onDelete, onTogglePin }) => {
  const long = post.body.length > PREVIEW_CHARS;
  const [open, setOpen] = useState(!long);
  const [downloading, setDownloading] = useState(null);
  const meta = KIND_META[post.kind];
  const unread = !staff && !post.read;

  const markRead = () => unread && onRead(post);
  const [discussing, setDiscussing] = useState(false);
  // Reacting or commenting marks the post read on the server; mirror that here.
  const readLocally = () => {
    if (!unread) return;
    onUpdate(post.id, { read: true });
    window.dispatchEvent(new Event(READ_EVENT));
  };
  const cardRef = useRef(null);

  // A short post is read in full just by being on screen.
  useEffect(() => {
    if (!unread || long || !cardRef.current || typeof IntersectionObserver === "undefined") return undefined;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          observer.disconnect();
          onRead(post);
        }
      },
      { threshold: 0.6 }
    );
    observer.observe(cardRef.current);
    return () => observer.disconnect();
  }, [unread, long, post, onRead]);

  const expand = () => {
    setOpen(true);
    markRead();
  };

  const download = async (attachment) => {
    setDownloading(attachment.id);
    try {
      await downloadAttachment(post.id, attachment);
      markRead();
    } catch (err) {
      toast.error(apiError(err, "Couldn't download the file."));
    } finally {
      setDownloading(null);
    }
  };

  return (
    <Card className={cx("p-5", unread && "ring-1 ring-accent-600/30")}>
      <article ref={cardRef} aria-labelledby={`post-${post.id}`} className="space-y-3">
        <header className="flex items-start gap-3">
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={meta.tone}>{meta.label}</Badge>
              {post.pinned && (
                <span className="inline-flex items-center gap-1 text-[12px] font-medium text-amber-700">
                  <MapPinIcon className="size-3.5" />
                  Pinned
                </span>
              )}
              {unread && (
                <span className="inline-flex items-center gap-1.5 text-[12px] font-medium text-accent-700">
                  <span className="size-1.5 rounded-full bg-accent-600" />
                  New
                </span>
              )}
            </div>
            <h2 id={`post-${post.id}`} className="text-base font-semibold text-slate-900">
              {post.title}
            </h2>
            <p className="text-[12px] text-slate-500">
              {post.author?.name ?? "Former staff member"} · {timeAgo(post.createdAt)}
              {post.editedAt && " · edited"} · <span className="text-slate-600">{post.audience.label}</span>
            </p>
          </div>
          {staff && post.canEdit && (
            <div className="flex shrink-0 gap-0.5">
              <IconButton
                label={post.pinned ? "Unpin" : "Pin to the top"}
                active={post.pinned}
                onClick={() => onTogglePin(post)}
              >
                <MapPinIcon className="size-4" />
              </IconButton>
              <IconButton label="Edit" onClick={() => onEdit(post)}>
                <PencilSquareIcon className="size-4" />
              </IconButton>
              <IconButton label="Delete" danger onClick={() => onDelete(post)}>
                <TrashIcon className="size-4" />
              </IconButton>
            </div>
          )}
        </header>

        {post.body && (
          <div className="text-sm leading-relaxed whitespace-pre-wrap text-slate-700 [overflow-wrap:anywhere]">
            {open ? post.body : `${post.body.slice(0, PREVIEW_CHARS).trimEnd()}…`}
            {!open && (
              <button
                type="button"
                onClick={expand}
                className="ml-1 font-medium text-accent-700 hover:text-accent-800"
              >
                Read more
              </button>
            )}
          </div>
        )}

        {post.attachments.length > 0 && (
          <ul className="flex flex-wrap gap-2">
            {post.attachments.map((a) => (
              <li key={a.id}>
                <button
                  type="button"
                  onClick={() => download(a)}
                  disabled={downloading === a.id}
                  className="flex max-w-xs items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[13px] text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50 disabled:opacity-60"
                >
                  <PaperClipIcon className="size-4 shrink-0 text-slate-400" />
                  <span className="truncate">{a.name}</span>
                  <span className="shrink-0 text-[12px] text-slate-400 tabular-nums">{formatBytes(a.size)}</span>
                  <ArrowDownTrayIcon className="size-4 shrink-0 text-slate-400" />
                </button>
              </li>
            ))}
          </ul>
        )}

        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
          <div className="flex flex-wrap items-center gap-2">
            {/* Only an explicit "off" hides commenting; older posts have no setting yet. */}
            {(post.commentsEnabled !== false || post.commentCount > 0) && (
              <button
                type="button"
                onClick={() => setDiscussing((d) => !d)}
                aria-expanded={discussing}
                className={cx(
                  "flex h-7 items-center gap-1.5 rounded-full px-2.5 text-[13px] font-medium ring-1 transition-colors",
                  discussing
                    ? "bg-accent-50 text-accent-800 ring-accent-600/40"
                    : "bg-white text-slate-700 ring-slate-200 hover:bg-slate-50"
                )}
              >
                <ChatBubbleLeftIcon className="size-4" />
                {post.commentCount
                  ? `${post.commentCount} comment${post.commentCount === 1 ? "" : "s"}`
                  : "Comment"}
              </button>
            )}
            <Reactions
              postId={post.id}
              reactions={post.reactions ?? []}
              onChange={(reactions) => onUpdate(post.id, { reactions })}
              onReacted={readLocally}
            />
          </div>
          {staff && (
            <span className="flex items-center gap-1.5 text-[12px] text-slate-500">
              <EyeIcon className="size-3.5" />
              Seen by {post.readers} of {post.audienceSize}
            </span>
          )}
        </footer>

        {discussing && (
          <CommentThread
            post={post}
            onCountChange={(delta) => onUpdate(post.id, { commentCount: post.commentCount + delta })}
            onCommented={readLocally}
          />
        )}
      </article>
    </Card>
  );
};

export default PostCard;
