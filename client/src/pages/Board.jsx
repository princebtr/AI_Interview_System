import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import { PlusIcon } from "@heroicons/react/20/solid";
import { ChatBubbleLeftRightIcon } from "@heroicons/react/24/outline";
import api from "../utils/axios";
import { useApi } from "../hooks/useApi";
import { useAuth } from "../context/AuthContext";
import { Button, Card, PageHeader, SearchInput } from "../components/ui";
import { EmptyState, LoadError, LoadingBlock } from "../components/data";
import GroupPicker from "../components/GroupPicker";
import PostCard from "../components/board/PostCard";
import PostComposer from "../components/board/PostComposer";
import { apiError, cx } from "../utils/helpers";
import { EMPTY_SELECTION, selectionParams } from "../utils/structure";
import { KIND_META, READ_EVENT } from "../utils/board";

const PAGE_SIZE = 20;
const MAX_LIMIT = 100;
const TABS = [{ value: "", label: "All" }, ...Object.entries(KIND_META).map(([value, m]) => ({ value, label: m.plural }))];

/**
 * Notes & messages. Admins and educators share posts with any batch,
 * department, section or cohort; students read what's shared with their groups.
 */
const Board = () => {
  const { user } = useAuth();
  const staff = user?.role === "admin" || user?.role === "educator";
  const [kind, setKind] = useState("");
  const [selection, setSelection] = useState(EMPTY_SELECTION);
  const [mine, setMine] = useState(false);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [pages, setPages] = useState(1);
  const [composer, setComposer] = useState(null); // {post} to edit, {} for a new one
  const [posts, setPosts] = useState([]);
  const structure = useApi(staff ? "/institution/structure" : null);
  const tree = structure.data?.batches ?? [];

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const groupKey = JSON.stringify(staff ? selectionParams(selection) : {});
  // A new filter starts again from the first page.
  useEffect(() => setPages(1), [kind, groupKey, mine, query]);

  const { data, loading, error, reload } = useApi("/board/posts", {
    limit: Math.min(MAX_LIMIT, PAGE_SIZE * pages),
    ...(kind && { kind }),
    ...(query && { q: query }),
    ...(staff && selectionParams(selection)),
    ...(staff && mine && { mine: "true" }),
  });
  useEffect(() => {
    if (data) setPosts(data.posts);
  }, [data]);

  const total = data?.total ?? 0;
  const filtered = Boolean(kind || query || mine || groupKey !== "{}");
  const canLoadMore = posts.length < total && PAGE_SIZE * pages < MAX_LIMIT;

  const markRead = useCallback((post) => {
    setPosts((prev) => prev.map((p) => (p.id === post.id ? { ...p, read: true } : p)));
    api
      .post(`/board/posts/${post.id}/read`)
      .then(() => window.dispatchEvent(new Event(READ_EVENT)))
      .catch(() => {}); // not worth interrupting the student: it'll show as new next time
  }, []);

  const updatePost = useCallback(
    (id, patch) => setPosts((prev) => prev.map((p) => (p.id === id ? { ...p, ...patch } : p))),
    []
  );

  const remove = async (post) => {
    const noun = KIND_META[post.kind].label.toLowerCase();
    if (!window.confirm(`Delete the ${noun} "${post.title}"? Students will no longer see it or its files.`)) return;
    try {
      await api.delete(`/board/posts/${post.id}`);
      setPosts((prev) => prev.filter((p) => p.id !== post.id));
      toast.success(`Deleted "${post.title}"`);
      reload();
    } catch (err) {
      toast.error(apiError(err, `Couldn't delete the ${noun}.`));
    }
  };

  const togglePin = async (post) => {
    try {
      await api.patch(`/board/posts/${post.id}`, { pinned: !post.pinned });
      toast.success(post.pinned ? "Unpinned" : "Pinned to the top");
      reload(); // pinned posts sort first
    } catch (err) {
      toast.error(apiError(err, "Couldn't change the pin."));
    }
  };

  const saved = (post, { keepOpen = false } = {}) => {
    setPosts((prev) => (prev.some((p) => p.id === post.id) ? prev.map((p) => (p.id === post.id ? post : p)) : [post, ...prev]));
    if (!keepOpen) {
      setComposer(null);
      reload();
    }
  };

  const noStructure = staff && structure.data && tree.length === 0;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={staff ? "Teaching" : user?.placement?.label}
        title="Notes & messages"
        description={
          staff
            ? "Share announcements and study material with any batch, department, section or cohort."
            : "Announcements and study material from your educators and admins."
        }
        actions={
          staff && (
            <Button onClick={() => setComposer({})} disabled={!structure.data || noStructure}>
              <PlusIcon className="size-4" />
              New post
            </Button>
          )
        }
      />

      {noStructure && (
        <Card className="p-4 text-[13px] text-slate-600">
          Posts are shared with a batch, department, section or cohort, and there aren't any yet.{" "}
          {user.role === "admin" ? (
            <Link to="/structure" className="font-medium text-accent-700 hover:text-accent-800">
              Set up the academic structure
            </Link>
          ) : (
            "Ask an admin to set up the academic structure."
          )}
        </Card>
      )}

      <Card>
        <div className="flex flex-col gap-3 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
          <div role="tablist" aria-label="Filter by type" className="flex gap-1">
            {TABS.map((tab) => (
              <button
                key={tab.value || "all"}
                type="button"
                role="tab"
                aria-selected={kind === tab.value}
                onClick={() => setKind(tab.value)}
                className={cx(
                  "h-8 rounded-md px-2.5 text-sm font-medium transition-colors",
                  kind === tab.value ? "bg-slate-100 text-slate-900" : "text-slate-500 hover:text-slate-800"
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            {staff && (
              <label className="flex items-center gap-2 text-[13px] text-slate-600">
                <input
                  type="checkbox"
                  checked={mine}
                  onChange={(e) => setMine(e.target.checked)}
                  className="size-4 rounded border-slate-300 accent-accent-600"
                />
                Only my posts
              </label>
            )}
            <SearchInput
              id="board-search"
              label="Search notes and messages"
              className="sm:w-64"
              value={search}
              maxLength={100}
              placeholder="Search titles and text"
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>
        {staff && tree.length > 0 && (
          <div className="border-t border-slate-100 px-4 py-3">
            <GroupPicker mode="filter" idPrefix="board" tree={tree} value={selection} onChange={setSelection} />
          </div>
        )}
      </Card>

      {error && !data ? (
        <LoadError onRetry={reload} />
      ) : loading && !data ? (
        <div className="space-y-4">
          {[0, 1, 2].map((i) => (
            <LoadingBlock key={i} className="h-32" />
          ))}
        </div>
      ) : posts.length === 0 ? (
        <Card>
          <EmptyState
            icon={ChatBubbleLeftRightIcon}
            title={filtered ? "Nothing matches these filters" : "Nothing shared yet"}
            description={
              filtered
                ? "Try a different search or filter."
                : staff
                  ? "Share an announcement or study notes with your students."
                  : "Messages and notes from your educators will show up here."
            }
            action={
              staff &&
              !filtered &&
              !noStructure && (
                <Button onClick={() => setComposer({})}>
                  <PlusIcon className="size-4" />
                  New post
                </Button>
              )
            }
          />
        </Card>
      ) : (
        <div className="space-y-4">
          {posts.map((post) => (
            <PostCard
              key={post.id}
              post={post}
              staff={staff}
              onRead={markRead}
              onUpdate={updatePost}
              onEdit={(p) => setComposer({ post: p })}
              onDelete={remove}
              onTogglePin={togglePin}
            />
          ))}
          <div className="flex items-center justify-between gap-3 text-[13px] text-slate-500">
            <span className="tabular-nums">
              Showing {posts.length} of {total}
            </span>
            {canLoadMore && (
              <Button variant="secondary" size="sm" loading={loading} onClick={() => setPages((p) => p + 1)}>
                Load more
              </Button>
            )}
          </div>
        </div>
      )}

      {composer && (
        <PostComposer post={composer.post} tree={tree} onClose={() => setComposer(null)} onSaved={saved} />
      )}
    </div>
  );
};

export default Board;
