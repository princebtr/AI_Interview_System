import { useEffect } from "react";
import { createPortal } from "react-dom";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { applyTheme } from "./utils/theme";
import ProtectedRoute from "./components/auth/ProtectedRoute";
import RequireRole from "./components/auth/RequireRole";
import Login from "./components/auth/Login";
import AppShell from "./components/layout/AppShell";
import SettingsLayout from "./pages/settings/SettingsLayout";
import ProfileTab from "./pages/settings/ProfileTab";
import AccountTab from "./pages/settings/AccountTab";
import PasswordTab from "./pages/settings/PasswordTab";
import InstitutionTab from "./pages/settings/InstitutionTab";
import SetPassword from "./pages/SetPassword";
import AdminDashboard from "./pages/admin/AdminDashboard";
import Users from "./pages/admin/Users";
import ImportUsers from "./pages/admin/ImportUsers";
import Structure from "./pages/admin/Structure";
import GroupDetail from "./pages/admin/GroupDetail";
import Board from "./pages/Board";
import EducatorDashboard from "./pages/educator/EducatorDashboard";
import AddQuestions from "./pages/educator/AddQuestions";
import QuestionBank from "./pages/educator/QuestionBank";
import Students from "./pages/educator/Students";
import Assessments from "./pages/educator/Assessments";
import CreateAssessment from "./pages/educator/CreateAssessment";
import AssessmentDetail from "./pages/educator/AssessmentDetail";
import StudentHome from "./pages/student/StudentHome";
import StudentReport from "./pages/reports/StudentReport";
import ReportsOverview from "./pages/reports/ReportsOverview";
import MyTests from "./pages/student/MyTests";
import SetupCheck from "./pages/student/SetupCheck";
import TakeTest from "./pages/student/TakeTest";
import Interview from "./pages/Interview";
import Assessment from "./pages/Assessment";

// Each role gets its own accent colour (see index.css) on every screen it sees,
// unless the institution has its own colours (set in the Django admin), which
// then apply to all of its admins, educators and students.
const RoleTheme = () => {
  const { user } = useAuth();
  // Keyed by user too: signing in replaces whatever the sign-in page showed.
  const themeKey = JSON.stringify([user?.id ?? null, user?.institution?.theme?.palette ?? null]);
  useEffect(() => {
    const root = document.documentElement;
    if (user?.role) root.dataset.role = user.role;
    else delete root.dataset.role;
  }, [user?.role]);
  useEffect(() => {
    applyTheme(JSON.parse(themeKey)[1]);
  }, [themeKey]);
  return null;
};

// One URL, three homes: the backend role decides which dashboard you see.
/** Students get their own report; admins and educators the institution's. */
const RoleReports = () => {
  const { user } = useAuth();
  return user?.role === "student" ? <StudentReport /> : <ReportsOverview />;
};

const RoleHome = () => {
  const { user } = useAuth();
  if (user?.role === "admin") return <AdminDashboard />;
  if (user?.role === "educator") return <EducatorDashboard />;
  return <StudentHome />;
};

const only = (roles, element) => <RequireRole roles={roles}>{element}</RequireRole>;
const ADMIN = ["admin"];
const STAFF = ["admin", "educator"];
const STUDENT = ["student"];

const App = () => (
  <AuthProvider>
    <RoleTheme />
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/set-password"
          element={
            <ProtectedRoute passwordSetup>
              <SetPassword />
            </ProtectedRoute>
          }
        />

        <Route
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        >
          <Route path="/dashboard" element={<RoleHome />} />
          <Route path="/settings" element={<SettingsLayout />}>
            <Route index element={<Navigate to="profile" replace />} />
            <Route path="profile" element={<ProfileTab />} />
            <Route path="account" element={<AccountTab />} />
            <Route path="password" element={<PasswordTab />} />
            <Route path="institution" element={only(ADMIN, <InstitutionTab />)} />
            <Route path="*" element={<Navigate to="profile" replace />} />
          </Route>

          <Route path="/board" element={<Board />} />

          <Route path="/users" element={only(ADMIN, <Users />)} />
          <Route path="/users/import" element={only(ADMIN, <ImportUsers />)} />
          <Route path="/structure" element={only(ADMIN, <Structure />)} />
          <Route path="/structure/:level/:id" element={only(ADMIN, <GroupDetail />)} />
          <Route path="/cohorts" element={<Navigate to="/structure" replace />} />

          <Route path="/questions/add" element={only(STAFF, <AddQuestions />)} />
          <Route path="/generator" element={<Navigate to="/questions/add?tab=ai" replace />} />
          <Route path="/questions" element={only(STAFF, <QuestionBank />)} />
          <Route path="/students" element={only(STAFF, <Students />)} />
          <Route path="/assessments" element={only(STAFF, <Assessments />)} />
          <Route path="/assessments/new" element={only(STAFF, <CreateAssessment />)} />
          <Route path="/assessments/:id" element={only(STAFF, <AssessmentDetail />)} />

          <Route path="/interview" element={only(STUDENT, <Interview />)} />
          <Route path="/assessment" element={only(STUDENT, <Assessment />)} />
          <Route path="/tests" element={only(STUDENT, <MyTests />)} />
          <Route path="/tests/setup-check" element={only(STUDENT, <SetupCheck />)} />
          <Route path="/tests/:id" element={only(STUDENT, <TakeTest />)} />
          <Route path="/performance" element={<Navigate to="/reports" replace />} />
          <Route path="/reports" element={<RoleReports />} />
          <Route path="/reports/students/:id" element={only(STAFF, <StudentReport />)} />
        </Route>

        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>

      {/* Rendered at <body> so toasts stay visible and announced while a modal
          panel makes the app root inert. Top-centre keeps them clear of panel footers. */}
      {createPortal(
        <Toaster
          position="top-center"
          toastOptions={{
            duration: 4000,
            style: {
              background: "#fff",
              color: "#0f172a",
              border: "1px solid #e2e8f0",
              borderRadius: "12px",
              boxShadow: "0 10px 25px -5px color-mix(in oklab, var(--shadow-tint) 18%, transparent)",
              fontWeight: 500,
              fontSize: "14px",
              padding: "10px 14px",
            },
            success: { iconTheme: { primary: "#047857", secondary: "#fff" } },
            error: { duration: 5000, iconTheme: { primary: "#dc2626", secondary: "#fff" } },
          }}
        />,
        document.body
      )}
    </Router>
  </AuthProvider>
);

export default App;
