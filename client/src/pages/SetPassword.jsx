import { useAuth } from "../context/AuthContext";
import AuthLayout from "../components/auth/AuthLayout";
import ChangePasswordForm from "../components/ChangePasswordForm";

// First sign-in: accounts are created with a temporary password that must be replaced.
const SetPassword = () => {
  const { user, logout } = useAuth();
  const institution = user?.institution?.name;

  return (
    <AuthLayout
      brand={user?.institution}
      title="Choose your password"
      subtitle={`${institution ? `Welcome to ${institution}. ` : ""}Your account was set up with a temporary password. Replace it to continue.`}
      footer={
        <>
          Not {user?.name}?{" "}
          <button
            type="button"
            onClick={logout}
            className="font-medium text-accent-700 hover:text-accent-800"
          >
            Sign out
          </button>
        </>
      }
    >
      <ChangePasswordForm
        variant="page"
        currentLabel="Temporary password"
        submitLabel="Set password and continue"
      />
    </AuthLayout>
  );
};

export default SetPassword;
