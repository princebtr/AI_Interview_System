// Shared display pieces for scheduled tests.
import { Link } from "react-router-dom";
import { ArrowRightIcon, CalendarDaysIcon } from "@heroicons/react/20/solid";
import { ArrowIcon, Badge, Button, Card, LiveDot } from "./ui";
import { buttonStyles } from "./styles";
import { downloadFile, fileSlug, testCalendarEvent } from "../utils/exports";
import { countdown, formatDateTime, formatDuration, timeUntil } from "../utils/time";

/** Downloads an .ics event (with a 30-minute reminder) for an upcoming test. */
export const AddToCalendar = ({ test }) => (
  <Button
    variant="secondary"
    onClick={() =>
      downloadFile(
        `${fileSlug(test.title)}.ics`,
        testCalendarEvent(test, `${window.location.origin}/tests/${test.id}`),
        "text/calendar;charset=utf-8"
      )
    }
  >
    <CalendarDaysIcon className="size-4" />
    Add to calendar
  </Button>
);

export const TestStatusBadge = ({ status }) => {
  if (status === "live") {
    return (
      <Badge tone="danger">
        <LiveDot />
        Live
      </Badge>
    );
  }
  if (status === "scheduled") return <Badge tone="info">Scheduled</Badge>;
  return <Badge>Closed</Badge>;
};

const ATTEMPT = {
  not_started: ["Not started", "neutral"],
  in_progress: ["In progress", "warning"],
  submitted: ["Submitted", "success"],
  missed: ["Missed", "danger"],
};

export const AttemptBadge = ({ status, auto = false }) => {
  const [label, tone] = ATTEMPT[status] ?? [status, "neutral"];
  return <Badge tone={tone}>{auto && status === "submitted" ? "Auto-submitted" : label}</Badge>;
};

const statusAt = (test, now) => {
  const start = new Date(test.startsAt).getTime();
  const end = new Date(test.endsAt).getTime();
  return now < start ? "scheduled" : now < end ? "live" : "closed";
};

/** A test as a student sees it in "My tests" and on their home page. */
export const StudentTestCard = ({ test, now }) => {
  const status = statusAt(test, now);
  const attempt = test.attempt ?? { status: "not_started" };
  const meta = `${formatDuration(test.durationMinutes)} · ${test.questionCount} questions · ${test.totalMarks} marks`;
  // Closed while this list was open: the server submits it on the next read.
  const timedOut = status === "closed" && attempt.status === "in_progress";

  let action = null;
  if (timedOut) {
    action = (
      <Link
        to={`/tests/${test.id}`}
        className={buttonStyles({ variant: "secondary" })}
      >
        View result
      </Link>
    );
  } else if (status === "live" && attempt.status !== "submitted") {
    action = (
      <Link
        to={`/tests/${test.id}`}
        className={buttonStyles()}
      >
        {attempt.status === "in_progress" ? "Resume" : "Start test"}
        <ArrowIcon />
      </Link>
    );
  } else if (status === "scheduled" || attempt.status === "submitted") {
    action = (
      <Link
        to={`/tests/${test.id}`}
        className={buttonStyles({ variant: "secondary" })}
      >
        {attempt.status === "submitted" ? "View result" : "Details"}
      </Link>
    );
  }

  return (
    <Card className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          {timedOut ? (
            <AttemptBadge status="submitted" auto />
          ) : status === "closed" || attempt.status === "submitted" ? (
            <AttemptBadge
              status={attempt.status === "not_started" ? "missed" : attempt.status}
              auto={attempt.autoSubmitted}
            />
          ) : (
            <TestStatusBadge status={status} />
          )}
          <span className="text-[12px] text-slate-500">
            {status === "scheduled" && `Opens ${timeUntil(test.startsAt, now)}`}
            {status === "live" &&
              `${attempt.status === "submitted" ? "Answers revealed in" : "Closes in"} ${countdown(new Date(test.endsAt).getTime() - now)}`}
          </span>
        </div>
        <p className="mt-1.5 truncate text-base font-semibold text-slate-900">{test.title}</p>
        <p className="mt-0.5 text-[13px] text-slate-500">
          {formatDateTime(test.startsAt)} · {meta}
        </p>
        {attempt.status === "submitted" && (
          <p className="mt-1 text-[13px] font-medium text-slate-700">
            {attempt.score} / {test.totalMarks} marks ({Math.round(attempt.percentage)}%)
          </p>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        {status === "scheduled" && <AddToCalendar test={test} />}
        {action}
      </div>
    </Card>
  );
};

/** Weak subjects as links that open a practice test on that subject. */
export const PracticeTopicLinks = ({ subjects }) => (
  <div className="flex flex-wrap gap-2">
    {subjects.map((subject) => (
      <Link
        key={subject}
        to={`/assessment?subject=${encodeURIComponent(subject)}`}
        title={`Start a practice test on ${subject}`}
        className="group inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-[12px] font-medium text-amber-800 ring-1 ring-amber-600/20 ring-inset transition-colors hover:bg-amber-100"
      >
        {subject}
        <span className="text-amber-700/80 group-hover:text-amber-900">Practise</span>
        <ArrowRightIcon className="size-3.5" />
      </Link>
    ))}
  </div>
);
