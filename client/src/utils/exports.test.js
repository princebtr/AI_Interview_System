// Run with `npm test` (node --test).
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { fileSlug, resultsCsv, testCalendarEvent, toCsv } from "./exports.js";

describe("CSV", () => {
  it("quotes commas, quotes and line breaks", () => {
    assert.equal(toCsv([["a,b", 'say "hi"', "two\nlines", 3, null]]), '"a,b","say ""hi""","two\nlines",3,\r\n');
  });

  it("stops spreadsheets running cells as formulas", () => {
    assert.equal(toCsv([["=HYPERLINK(1)", "+1", "-2", "@x", "fine"]]), "'=HYPERLINK(1),'+1,'-2,'@x,fine\r\n");
  });

  it("writes one row per student", () => {
    const test = { questionCount: 10, totalMarks: 20 };
    const csv = resultsCsv(test, [
      {
        student: { name: "Asha Rao", email: "asha@x.edu" },
        status: "submitted",
        correct: 8,
        rawScore: 16,
        totalPenalty: 5,
        score: 11,
        percentage: 55,
        submittedAt: "2026-10-17T10:00:00Z",
        submissionReason: "FACE_VIOLATION_LIMIT",
        violations: { screen_switch: 1, voice: 0, face: 5, phone: 0 },
      },
      { student: { name: "Ravi", email: "ravi@x.edu" }, status: "missed", violations: null },
    ]);
    const [header, asha, ravi] = csv.trim().split("\r\n");
    assert.ok(header.startsWith("Student,Email,Status,Correct"));
    assert.equal(asha, "Asha Rao,asha@x.edu,Submitted,8,10,16,5,11,20,55,2026-10-17T10:00:00.000Z,Camera limit,1,0,5,0");
    assert.equal(ravi, "Ravi,ravi@x.edu,Missed,,10,,0,,20,,,,,,,");
  });

  it("makes safe file names", () => {
    assert.equal(fileSlug("Java: Unit 3 / Mid-term!"), "java-unit-3-mid-term");
    assert.equal(fileSlug(""), "test");
  });
});

describe("calendar event", () => {
  it("has the test's times, a link and a reminder", () => {
    const ics = testCalendarEvent(
      { id: "abc", title: "DSA; Unit 2, trees", subject: "DSA", startsAt: "2026-10-20T04:30:00Z", endsAt: "2026-10-20T05:15:00Z" },
      "https://app.example/tests/abc",
      new Date("2026-10-17T00:00:00Z")
    );
    const lines = ics.split("\r\n");
    assert.ok(lines.includes("DTSTART:20261020T043000Z"));
    assert.ok(lines.includes("DTEND:20261020T051500Z"));
    assert.ok(lines.includes("SUMMARY:Test: DSA\\; Unit 2\\, trees"));
    assert.ok(lines.includes("UID:test-abc@cohortix"));
    assert.ok(lines.includes("TRIGGER:-PT30M"));
    assert.ok(lines.includes("URL:https://app.example/tests/abc"));
    assert.equal(lines[0], "BEGIN:VCALENDAR");
  });
});
