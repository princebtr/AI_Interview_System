import { Link, useNavigate } from "react-router-dom";
import {
  AcademicCapIcon,
  ArrowUpTrayIcon,
  BoltIcon,
  BuildingLibraryIcon,
  ClipboardDocumentListIcon,
  KeyIcon,
  PhotoIcon,
  UserGroupIcon,
  UserPlusIcon,
  UsersIcon,
} from "@heroicons/react/24/outline";
import { CheckIcon } from "@heroicons/react/20/solid";
import { useAuth } from "../../context/AuthContext";
import { useApi } from "../../hooks/useApi";
import { Badge, Button, Card, CardHeader, GlowBackdrop, PageHeader } from "../../components/ui";
import {
  CardLink,
  DailyBars,
  EmptyState,
  LoadError,
  LoadingBlock,
  ScoreBar,
  StatCard,
  StatGrid,
} from "../../components/data";
import { cx } from "../../utils/helpers";
import { formatPercent } from "../../utils/scores";
import { firstName, greeting, timeAgo, todayLabel } from "../../utils/time";

const ACTIVITY_ICONS = {
  "user.created": UserPlusIcon,
  "users.imported": ArrowUpTrayIcon,
  "cohort.created": UserGroupIcon,
  "cohort.deleted": UserGroupIcon,
  "institution.onboarded": BuildingLibraryIcon,
  "user.password_reset": KeyIcon,
  "institution.updated": BuildingLibraryIcon,
  "institution.logo_updated": PhotoIcon,
  "institution.logo_removed": PhotoIcon,
  "assessment.created": ClipboardDocumentListIcon,
  "assessment.deleted": ClipboardDocumentListIcon,
};

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

const SetupChecklist = ({ counts, institution }) => {
  const steps = [
    {
      done: counts.cohorts > 0,
      title: "Create your first cohort",
      detail: "Cohorts group students who study together, e.g. CSE-2027.",
      to: "/cohorts?new=1",
      action: "Create cohort",
    },
    {
      done: counts.educators > 0,
      title: "Add an educator",
      detail: "Educators build question sets and follow their students' progress.",
      to: "/users?add=educator",
      action: "Add educator",
    },
    {
      done: counts.students > 0,
      title: "Add your students",
      detail: "Add them one at a time or import a CSV file.",
      to: "/users/import",
      action: "Import students",
    },
  ];
  const completed = steps.filter((s) => s.done).length;
  if (completed === steps.length) return null;

  return (
    <Card>
      <CardHeader
        title={`Finish setting up ${institution}`}
        description={`${completed} of ${steps.length} steps done`}
        action={
          <div className="hidden h-1.5 w-32 overflow-hidden rounded-full bg-slate-100 sm:block">
            <div
              className="h-full rounded-full bg-accent-600"
              style={{ width: `${(completed / steps.length) * 100}%` }}
            />
          </div>
        }
      />
      <ol className="divide-y divide-slate-100">
        {steps.map((step) => (
          <li key={step.title} className="flex items-center gap-4 px-5 py-3.5">
            <span
              className={cx(
                "flex size-6 shrink-0 items-center justify-center rounded-full",
                step.done ? "bg-accent-600 text-white" : "border border-slate-300 bg-white"
              )}
            >
              {step.done && <CheckIcon className="size-4" />}
            </span>
            <div className="min-w-0 flex-1">
              <p className={cx("text-sm font-medium", step.done ? "text-slate-400 line-through" : "text-slate-900")}>
                {step.title}
              </p>
              {!step.done && <p className="text-[13px] text-slate-500">{step.detail}</p>}
            </div>
            {!step.done && (
              <Link
                to={step.to}
                className="shrink-0 text-[13px] font-medium text-accent-700 hover:text-accent-800"
              >
                {step.action}
              </Link>
            )}
          </li>
        ))}
      </ol>
    </Card>
  );
};

const ActivityFeed = ({ items }) => {
  if (!items.length) {
    return (
      <EmptyState
        title="No activity yet"
        description="Users you add, cohorts you create and imports will show up here."
      />
    );
  }
  return (
    <ol className="space-y-4 px-5 py-4">
      {items.map((item) => {
        const Icon = ACTIVITY_ICONS[item.action] ?? BoltIcon;
        return (
          <li key={item.id} className="flex gap-3">
            <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500">
              <Icon className="size-3.5" />
            </span>
            <div className="min-w-0">
              <p className="text-sm text-slate-800">{item.summary}</p>
              <p className="text-[12px] text-slate-500">
                {item.actor ? item.actor.name : "Cohortix"} · {timeAgo(item.createdAt)}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
};

const AdminDashboard = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const overview = useApi("/institution/overview");
  const activity = useApi("/institution/activity", { limit: 8 });
  const institution = user?.institution?.name ?? "your institution";

  const header = (
    <PageHeader
      eyebrow={todayLabel()}
      title={
        <>
          {greeting()}, <span className="text-accent-600">{firstName(user?.name)}</span>
        </>
      }
      description={`Here's what's happening across ${institution}.`}
      actions={
        <>
          <Button variant="secondary" onClick={() => navigate("/users/import")}>
            <ArrowUpTrayIcon className="size-4" />
            Import users
          </Button>
          <Button onClick={() => navigate("/users?add=student")}>
            <UserPlusIcon className="size-4" />
            Add user
          </Button>
        </>
      }
    />
  );

  if (overview.error && !overview.data) {
    return (
      <div className="relative isolate space-y-8">
        <GlowBackdrop className="-inset-x-4 -top-8 h-96 sm:-inset-x-6 lg:-inset-x-10 lg:-top-10" />
        {header}
        <LoadError onRetry={overview.reload} />
      </div>
    );
  }

  const data = overview.data;
  const counts = data?.counts;
  const practice = data?.practice;
  const trend = practice ? practice.last7Days - practice.previous7Days : 0;

  return (
    <div className="relative isolate space-y-8">
      <GlowBackdrop className="-inset-x-4 -top-8 h-96 sm:-inset-x-6 lg:-inset-x-10 lg:-top-10" />
      {header}

      {counts && <SetupChecklist counts={counts} institution={institution} />}

      <section aria-label="Institution overview">
        {data ? (
          <StatGrid>
            <StatCard
              label="Students"
              value={counts.students}
              sub={`${data.activatedStudents} of ${counts.students} signed in`}
              icon={AcademicCapIcon}
              to="/users?role=student"
            />
            <StatCard
              label="Educators"
              value={counts.educators}
              sub={plural(counts.admins, "admin")}
              icon={UsersIcon}
              to="/users?role=educator"
            />
            <StatCard
              label="Cohorts"
              value={counts.cohorts}
              sub="Groups of students"
              icon={UserGroupIcon}
              to="/cohorts"
            />
            <StatCard
              label="Practice sessions"
              value={practice.last7Days}
              sub={
                practice.previous7Days || practice.last7Days
                  ? `${trend >= 0 ? "+" : ""}${trend} vs previous 7 days`
                  : "Last 7 days"
              }
              icon={BoltIcon}
            />
          </StatGrid>
        ) : (
          <StatGrid>
            {[0, 1, 2, 3].map((i) => (
              <LoadingBlock key={i} className="h-28" />
            ))}
          </StatGrid>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Student practice"
            description="Practice tests and AI interview answers per day, last 14 days"
            action={
              practice?.averageScore != null && (
                <Badge tone="brand">Avg score {formatPercent(practice.averageScore)}</Badge>
              )
            }
          />
          <div className="p-5">
            {!data ? (
              <LoadingBlock className="h-36" />
            ) : practice.daily.some((d) => d.count) ? (
              <DailyBars data={practice.daily} label="Student practice sessions per day" />
            ) : (
              <EmptyState
                icon={BoltIcon}
                title="No practice yet"
                description="When students take practice tests or answer AI interview questions, their activity appears here."
                className="py-6"
              />
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Recent activity" description="Changes made in your institution" />
          {activity.data ? (
            <ActivityFeed items={activity.data.activity} />
          ) : (
            <div className="space-y-3 p-5">
              {[0, 1, 2].map((i) => (
                <LoadingBlock key={i} className="h-10" />
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Cohorts"
          description="Students, sign-ins and average practice score per cohort"
          action={<CardLink to="/cohorts">All cohorts</CardLink>}
        />
        {!data ? (
          <div className="p-5">
            <LoadingBlock className="h-32" />
          </div>
        ) : data.cohorts.length === 0 ? (
          <EmptyState
            icon={UserGroupIcon}
            title="No cohorts yet"
            description="Create a cohort before adding students."
            action={
              <Button onClick={() => navigate("/cohorts?new=1")}>Create cohort</Button>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-[12px] text-slate-500">
                  <th className="px-5 py-2.5 font-medium">Cohort</th>
                  <th className="px-5 py-2.5 text-right font-medium">Students</th>
                  <th className="hidden px-5 py-2.5 text-right font-medium sm:table-cell">Signed in</th>
                  <th className="px-5 py-2.5 font-medium">Avg practice score</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.cohorts.map((c) => (
                  <tr key={c.id} className="transition-colors hover:bg-slate-50">
                    <td className="px-5 py-3">
                      <Link to={`/cohorts/${c.id}`} className="font-medium text-slate-900 hover:text-accent-700">
                        {c.name}
                      </Link>
                    </td>
                    <td className="px-5 py-3 text-right text-slate-700 tabular-nums">{c.students}</td>
                    <td className="hidden px-5 py-3 text-right text-slate-500 tabular-nums sm:table-cell">
                      {c.activated} / {c.students}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-3">
                        <ScoreBar value={c.averageScore} className="w-24 sm:w-40" />
                        <span className="w-10 text-right text-slate-700 tabular-nums">
                          {formatPercent(c.averageScore)}
                        </span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};

export default AdminDashboard;
