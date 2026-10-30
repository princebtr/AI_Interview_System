export const cx = (...classes) => classes.filter(Boolean).join(" ");

export const apiError = (error, fallback) =>
  error?.response?.data?.error || error?.response?.data?.message || fallback;

export const initials = (name = "") =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("") || "?";

export const formatDate = (value, options = { day: "numeric", month: "short", year: "numeric" }) =>
  value ? new Date(value).toLocaleDateString(undefined, options) : "—";

// Unambiguous characters only (no 0/O, 1/l/I) so passwords are easy to share.
const PASSWORD_SETS = ["ABCDEFGHJKLMNPQRSTUVWXYZ", "abcdefghijkmnopqrstuvwxyz", "23456789"];

const randomIndex = (n) => {
  const buf = new Uint32Array(1);
  crypto.getRandomValues(buf);
  return buf[0] % n;
};

/** A random password with at least one upper, lower and digit. */
export const generatePassword = (length = 14) => {
  const all = PASSWORD_SETS.join("");
  const chars = PASSWORD_SETS.map((set) => set[randomIndex(set.length)]);
  while (chars.length < length) chars.push(all[randomIndex(all.length)]);
  for (let i = chars.length - 1; i > 0; i--) {
    const j = randomIndex(i + 1);
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  return chars.join("");
};
