"""Reading uploaded CSV files (people imports, question imports)."""
import csv
import io

from .http import BadRequest


# Spreadsheet apps run cells starting with these as formulas ("CSV injection").
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value):
    """A value to write into an exported CSV: formula-like text gets a leading
    apostrophe so spreadsheets show it as text. read_csv removes it again."""
    text = "" if value is None else str(value)
    # Text that already looks escaped ("'=x") is escaped again, or read_csv would strip its apostrophe.
    return f"'{text}" if text.startswith(FORMULA_START) or _escaped(text) else text


def _escaped(text):
    """Whether `text` is one or more apostrophes in front of formula-like text."""
    rest = text.lstrip("'")
    return len(rest) < len(text) and rest.startswith(FORMULA_START)


def _unescape(cell):
    cell = cell.strip()
    return cell[1:] if _escaped(cell) else cell


def header_key(cell):
    """A header cell as a column key: "Option A" / "option-a" -> "option_a"."""
    return "_".join(cell.strip().lower().replace("-", " ").split())


def read_csv(upload, *, columns, required, aliases=None, example, noun, max_rows, max_bytes=1024 * 1024):
    """[(line number, {column: value})] for every non-blank data row.

    `columns` are the keys kept, `required` must be in the header, `aliases`
    maps other header spellings to a column key. Raises BadRequest with a
    message meant for the person who made the file.
    """
    if upload is None:
        raise BadRequest("Choose a CSV file to import")
    if upload.size > max_bytes:
        raise BadRequest(f"The file is larger than {max_bytes // (1024 * 1024)} MB. Split it into smaller files.")
    raw = upload.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")  # Excel on Windows

    reader = csv.reader(io.StringIO(text, newline=""))
    rows = []
    try:
        # Count records, not physical lines: a quoted cell may span lines, and
        # the number should match the row a spreadsheet shows.
        for number, row in enumerate(reader, start=1):
            if any(cell.strip() for cell in row):
                rows.append((number, row))
    except csv.Error:
        raise BadRequest("That file isn't valid CSV. Save it as CSV and try again.")
    if not rows:
        raise BadRequest("The file is empty")

    aliases = aliases or {}
    header = [aliases.get(header_key(cell), header_key(cell)) for cell in rows[0][1]]
    missing = [c for c in required if c not in header]
    if missing:
        raise BadRequest(
            f"Missing column{'s' if len(missing) > 1 else ''}: {', '.join(missing)}. "
            f"The first row must be a header such as {example}."
        )
    known = [c for c in header if c in columns]
    if len(set(known)) != len(known):
        raise BadRequest("The header repeats a column name")

    body = rows[1:]
    if not body:
        raise BadRequest(f"The file has a header but no {noun}")
    if len(body) > max_rows:
        raise BadRequest(f"Import at most {max_rows} {noun} at a time")

    index = {c: header.index(c) for c in columns if c in header}
    return [
        (line, {c: (_unescape(row[i]) if i < len(row) else "") for c, i in index.items()})
        for line, row in body
    ]
