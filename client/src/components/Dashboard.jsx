import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useForm } from "react-hook-form";
import { EyeIcon, EyeSlashIcon } from "@heroicons/react/24/outline";

const Dashboard = () => {
  const { user, logout, updateUser, updatePassword } = useAuth();
  const [activeTab, setActiveTab] = useState("profile");
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const {
    register: registerProfile,
    handleSubmit: handleProfileSubmit,
    formState: { errors: profileErrors },
  } = useForm({
    defaultValues: {
      name: user?.name || "",
      email: user?.email || "",
    },
  });

  const {
    register: registerPassword,
    handleSubmit: handlePasswordSubmit,
    watch,
    formState: { errors: passwordErrors },
  } = useForm();

  const newPassword = watch("newPassword");

  const onProfileSubmit = async (data) => {
    const result = await updateUser(data);
    if (result.success) {
      setActiveTab("profile");
    }
  };

  const onPasswordSubmit = async (data) => {
    const { confirmNewPassword, ...passwordData } = data;
    const result = await updatePassword(passwordData);
    if (result.success) {
      setActiveTab("profile");
    }
  };

  const handleLogout = () => {
    logout();
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-6">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
              <p className="text-gray-600">Welcome back, {user?.name}!</p>
            </div>
            <button
              onClick={handleLogout}
              className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-md text-sm font-medium"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="px-4 py-6 sm:px-0">
          <div className="bg-white shadow rounded-lg">
            {/* Tabs */}
            <div className="border-b border-gray-200">
              <nav className="-mb-px flex space-x-8" aria-label="Tabs">
                <button
                  onClick={() => setActiveTab("profile")}
                  className={`py-2 px-1 border-b-2 font-medium text-sm ${
                    activeTab === "profile"
                      ? "border-indigo-500 text-indigo-600"
                      : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                  }`}
                >
                  Profile
                </button>
                <button
                  onClick={() => setActiveTab("security")}
                  className={`py-2 px-1 border-b-2 font-medium text-sm ${
                    activeTab === "security"
                      ? "border-indigo-500 text-indigo-600"
                      : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                  }`}
                >
                  Security
                </button>
              </nav>
            </div>

            <div className="p-6">
              {/* Profile Tab */}
              {activeTab === "profile" && (
                <div>
                  <h3 className="text-lg font-medium text-gray-900 mb-4">
                    Profile Information
                  </h3>
                  <form onSubmit={handleProfileSubmit} className="space-y-4">
                    <div>
                      <label
                        htmlFor="name"
                        className="block text-sm font-medium text-gray-700"
                      >
                        Full Name
                      </label>
                      <input
                        {...registerProfile("name", {
                          required: "Name is required",
                          minLength: {
                            value: 2,
                            message: "Name must be at least 2 characters",
                          },
                          maxLength: {
                            value: 50,
                            message: "Name cannot exceed 50 characters",
                          },
                        })}
                        type="text"
                        className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                      />
                      {profileErrors.name && (
                        <p className="mt-1 text-sm text-red-600">
                          {profileErrors.name.message}
                        </p>
                      )}
                    </div>

                    <div>
                      <label
                        htmlFor="email"
                        className="block text-sm font-medium text-gray-700"
                      >
                        Email Address
                      </label>
                      <input
                        {...registerProfile("email", {
                          required: "Email is required",
                          pattern: {
                            value: /^\S+@\S+$/i,
                            message: "Invalid email address",
                          },
                        })}
                        type="email"
                        className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                      />
                      {profileErrors.email && (
                        <p className="mt-1 text-sm text-red-600">
                          {profileErrors.email.message}
                        </p>
                      )}
                    </div>

                    <div className="flex justify-end">
                      <button
                        type="submit"
                        className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-md text-sm font-medium"
                      >
                        Update Profile
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* Security Tab */}
              {activeTab === "security" && (
                <div>
                  <h3 className="text-lg font-medium text-gray-900 mb-4">
                    Change Password
                  </h3>
                  <form onSubmit={handlePasswordSubmit} className="space-y-4">
                    <div>
                      <label
                        htmlFor="currentPassword"
                        className="block text-sm font-medium text-gray-700"
                      >
                        Current Password
                      </label>
                      <div className="mt-1 relative">
                        <input
                          {...registerPassword("currentPassword", {
                            required: "Current password is required",
                          })}
                          type={showCurrentPassword ? "text" : "password"}
                          className="block w-full px-3 py-2 pr-10 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                        />
                        <button
                          type="button"
                          className="absolute inset-y-0 right-0 pr-3 flex items-center"
                          onClick={() =>
                            setShowCurrentPassword(!showCurrentPassword)
                          }
                        >
                          {showCurrentPassword ? (
                            <EyeSlashIcon className="h-5 w-5 text-gray-400" />
                          ) : (
                            <EyeIcon className="h-5 w-5 text-gray-400" />
                          )}
                        </button>
                      </div>
                      {passwordErrors.currentPassword && (
                        <p className="mt-1 text-sm text-red-600">
                          {passwordErrors.currentPassword.message}
                        </p>
                      )}
                    </div>

                    <div>
                      <label
                        htmlFor="newPassword"
                        className="block text-sm font-medium text-gray-700"
                      >
                        New Password
                      </label>
                      <div className="mt-1 relative">
                        <input
                          {...registerPassword("newPassword", {
                            required: "New password is required",
                            minLength: {
                              value: 6,
                              message: "Password must be at least 6 characters",
                            },
                            pattern: {
                              value: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/,
                              message:
                                "Password must contain at least one lowercase letter, one uppercase letter, and one number",
                            },
                          })}
                          type={showNewPassword ? "text" : "password"}
                          className="block w-full px-3 py-2 pr-10 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                        />
                        <button
                          type="button"
                          className="absolute inset-y-0 right-0 pr-3 flex items-center"
                          onClick={() => setShowNewPassword(!showNewPassword)}
                        >
                          {showNewPassword ? (
                            <EyeSlashIcon className="h-5 w-5 text-gray-400" />
                          ) : (
                            <EyeIcon className="h-5 w-5 text-gray-400" />
                          )}
                        </button>
                      </div>
                      {passwordErrors.newPassword && (
                        <p className="mt-1 text-sm text-red-600">
                          {passwordErrors.newPassword.message}
                        </p>
                      )}
                    </div>

                    <div>
                      <label
                        htmlFor="confirmNewPassword"
                        className="block text-sm font-medium text-gray-700"
                      >
                        Confirm New Password
                      </label>
                      <div className="mt-1 relative">
                        <input
                          {...registerPassword("confirmNewPassword", {
                            required: "Please confirm your new password",
                            validate: (value) =>
                              value === newPassword || "Passwords do not match",
                          })}
                          type={showConfirmPassword ? "text" : "password"}
                          className="block w-full px-3 py-2 pr-10 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                        />
                        <button
                          type="button"
                          className="absolute inset-y-0 right-0 pr-3 flex items-center"
                          onClick={() =>
                            setShowConfirmPassword(!showConfirmPassword)
                          }
                        >
                          {showConfirmPassword ? (
                            <EyeSlashIcon className="h-5 w-5 text-gray-400" />
                          ) : (
                            <EyeIcon className="h-5 w-5 text-gray-400" />
                          )}
                        </button>
                      </div>
                      {passwordErrors.confirmNewPassword && (
                        <p className="mt-1 text-sm text-red-600">
                          {passwordErrors.confirmNewPassword.message}
                        </p>
                      )}
                    </div>

                    <div className="flex justify-end">
                      <button
                        type="submit"
                        className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-md text-sm font-medium"
                      >
                        Update Password
                      </button>
                    </div>
                  </form>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
