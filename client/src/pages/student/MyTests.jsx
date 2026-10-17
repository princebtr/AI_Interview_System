import { Link } from "react-router-dom";
import { CalendarDaysIcon, VideoCameraIcon } from "@heroicons/react/24/outline";
import { useAuth } from "../../context/AuthContext";
import { useApi } from "../../hooks/useApi";
import { useServerClock } from "../../hooks/useServerClock";
import { Card, PageHeader } from "../../components/ui";
import { EmptyState, LoadError, LoadingBlock } from "../../components/data";
import { StudentTestCard } from "../../components/tests";
import { buttonStyles } from "../../components/styles";

const Section = ({ title, tests, now }) =>
  tests.length > 0 && (
    <section className="space-y-3" aria-label={title}>
      <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
      {tests.map((t) => (
        <StudentTestCard key={t.id} test={t} now={now} />
      ))}
    </section>
  );

const MyTests = () => {
  const { user } = useAuth();
  const { data, error, reload } = useApi("/me/tests");
  const now = useServerClock(data?.serverTime);
  const tests = data?.tests ?? [];

  const startOf = (t) => new Date(t.startsAt).getTime();
  const endOf = (t) => new Date(t.endsAt).getTime();
  const live = tests.filter((t) => startOf(t) <= now && now < endOf(t) && t.attempt.status !== "submitted");
  const upcoming = tests.filter((t) => now < startOf(t));
  const done = tests
    .filter((t) => !live.includes(t) && !upcoming.includes(t))
    .sort((a, b) => startOf(b) - startOf(a));

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={user?.cohort?.name}
        title="My tests"
        description="Tests your educators have assigned to your cohort. Each one opens at its start time and closes when its time is up."
        actions={
          <Link to="/tests/setup-check" className={buttonStyles({ variant: "secondary" })}>
            <VideoCameraIcon className="size-4" />
            Check my setup
          </Link>
        }
      />

      {error && !data ? (
        <LoadError onRetry={reload} />
      ) : !data ? (
        <div className="space-y-3">
          {[0, 1].map((i) => <LoadingBlock key={i} className="h-24" />)}
        </div>
      ) : tests.length === 0 ? (
        <Card>
          <EmptyState
            icon={CalendarDaysIcon}
            title="No tests yet"
            description="When an educator assigns a test to your cohort, it shows up here with its start time and duration."
          />
        </Card>
      ) : (
        <>
          <Section title="Live now" tests={live} now={now} />
          <Section title="Upcoming" tests={upcoming} now={now} />
          <Section title="Completed" tests={done} now={now} />
        </>
      )}
    </div>
  );
};

export default MyTests;
