// Display metadata for the roles the backend knows about (accounts.User.ROLE_CHOICES).
export const ROLES = [
  {
    value: "student",
    label: "Student",
    plural: "Students",
    description: "Takes assessments and AI interviews.",
    tone: "violet",
  },
  {
    value: "educator",
    label: "Educator",
    plural: "Educators",
    description: "Creates assessments and reviews results.",
    tone: "success",
  },
  {
    value: "admin",
    label: "Admin",
    plural: "Admins",
    description: "Manages users, cohorts and settings.",
    tone: "blue",
  },
];

export const roleMeta = (value) =>
  ROLES.find((role) => role.value === value) ?? { value, label: value, tone: "neutral" };
