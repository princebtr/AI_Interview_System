// Files the app hands to the user: a test's results as CSV and calendar events
// (.ics) for scheduled tests. Pure functions, unit-tested with `node --test`.

import { reasonLabel } from "./proctoring.js";

/** One CSV cell. Text a spreadsheet would run as a formula (=, +, -, @) is prefixed with '. */
const cell = (value) => {
  if (value === null || value === undefined) return "";
  let text = String(value);
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};

export const toCsv = (rows) => rows.map((row) => row.map(cell).join(",")).join("\r\n") + "\r\n";

const STATUS = { submitted: "Submitted", in_progress: "In progress", missed: "Missed", not_started: "Not started" };

/** A test's results (from GET /assessments/<id>) as CSV text, one row per student. */
export const resultsCsv = (test, results) =>
  toCsv([
    [
      "Student",
      "Email",
      "Status",
      "Correct",
      "Questions",
      "Raw score",
      "Penalty",
      "Final score",
      "Total marks",
      "Percentage",
      "Submitted at",
      "Submission",
      "Full-screen exits",
      "Speech",
      "Camera",
      "Phone",
    ],
    ...results.map((r) => [
      r.student.name,
      r.student.email,
      STATUS[r.status] ?? r.status,
      r.correct,
      test.questionCount,
      r.rawScore,
      r.totalPenalty || 0,
      r.score,
      test.totalMarks,
      r.percentage,
      r.submittedAt ? new Date(r.submittedAt).toISOString() : "",
      r.submissionReason ? reasonLabel(r.submissionReason) : "",
      r.violations?.screen_switch ?? "",
      r.violations?.voice ?? "",
      r.violations?.face ?? "",
      r.violations?.phone ?? "",
    ]),
  ]);

/** A safe file name from a title, e.g. "Java Unit 3: Results" -> "java-unit-3-results". */
export const fileSlug = (title) =>
  (title || "test")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 60) || "test";

const icsTime = (value) =>
  new Date(value)
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d{3}/, "");
const icsText = (value) => String(value ?? "").replace(/[\\;,]/g, (c) => `\\${c}`).replace(/\r?\n/g, "\\n");

/**
 * A calendar event (.ics) for a scheduled test, with a reminder 30 minutes before.
 * `test`: { id, title, startsAt, endsAt, subject }, `url`: where to take it.
 */
export const testCalendarEvent = (test, url, now = new Date()) =>
  [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Cohortix//Tests//EN",
    "CALSCALE:GREGORIAN",
    "BEGIN:VEVENT",
    `UID:test-${test.id}@cohortix`,
    `DTSTAMP:${icsTime(now)}`,
    `DTSTART:${icsTime(test.startsAt)}`,
    `DTEND:${icsTime(test.endsAt)}`,
    `SUMMARY:${icsText(`Test: ${test.title}`)}`,
    `DESCRIPTION:${icsText(`${test.subject ? `${test.subject}. ` : ""}Proctored test: have your camera and microphone ready. ${url}`)}`,
    `URL:${url}`,
    "BEGIN:VALARM",
    "ACTION:DISPLAY",
    "TRIGGER:-PT30M",
    `DESCRIPTION:${icsText(`${test.title} starts in 30 minutes`)}`,
    "END:VALARM",
    "END:VEVENT",
    "END:VCALENDAR",
    "",
  ].join("\r\n");

/** Hand `text` to the browser as a download. */
export const downloadFile = (name, text, type) => {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
