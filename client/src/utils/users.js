import api from "./axios";

/**
 * Download the institution's users as CSV, in the import's columns (passwords
 * are never exported). `filters`: role, batch/department/section/cohort, q.
 * The request needs the Bearer token, so the file is fetched, then saved.
 */
export const exportUsers = async (filters = {}) => {
  const { data } = await api.get("/institution/users/export", { params: filters, responseType: "blob" });
  const url = URL.createObjectURL(data);
  const stamp = new Date().toISOString().slice(0, 10);
  const link = Object.assign(document.createElement("a"), { href: url, download: `users-${stamp}.csv` });
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
