import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useForm } from "react-hook-form";
import {
  EyeIcon,
  EyeSlashIcon,
  UserIcon,
  ChevronDownIcon,
  CogIcon,
  ArrowRightOnRectangleIcon,
  AcademicCapIcon,
  DocumentTextIcon,
  ChatBubbleLeftRightIcon,
  CheckCircleIcon,
  ClockIcon,
  ChartBarIcon,
  TrophyIcon,
  CalendarIcon,
  BellIcon,
  QuestionMarkCircleIcon,
  UsersIcon,
  StarIcon,
  LightBulbIcon,
  ShieldCheckIcon,
} from "@heroicons/react/24/outline";

const Dashboard = () => {
  const { user, logout, updateUser, updatePassword } = useAuth();
  const navigate = useNavigate();
  const [showProfileDropdown, setShowProfileDropdown] = useState(false);
  const [showProfileModal, setShowProfileModal] = useState(false);
  const [activeTab, setActiveTab] = useState("profile");
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const dropdownRef = useRef(null);

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
      setShowProfileModal(false);
    }
  };

  const onPasswordSubmit = async (data) => {
    const { confirmNewPassword, ...passwordData } = data;
    const result = await updatePassword(passwordData);
    if (result.success) {
      setShowProfileModal(false);
    }
  };

  const handleLogout = () => {
    logout();
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setShowProfileDropdown(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  // Mock data for new components
  const userStats = {
    testsCompleted: 12,
    averageScore: 85,
    streakDays: 7,
    rank: "Gold",
  };

  const recentTests = [
    {
      id: 1,
      name: "React Technical Interview",
      score: 92,
      date: "2024-01-15",
      type: "interview",
    },
    {
      id: 2,
      name: "JavaScript Fundamentals",
      score: 78,
      date: "2024-01-12",
      type: "multiple-choice",
    },
    {
      id: 3,
      name: "System Design Assessment",
      score: 85,
      date: "2024-01-10",
      type: "long-answer",
    },
  ];

  const upcomingInterviews = [
    {
      id: 1,
      company: "TechCorp",
      role: "Frontend Developer",
      date: "2024-01-20",
      time: "14:30",
    },
    {
      id: 2,
      company: "DataSystems",
      role: "Full Stack Engineer",
      date: "2024-01-22",
      time: "10:00",
    },
  ];

  const testTypes = [
    {
      id: "interview",
      title: "AI Interview",
      description:
        "Real-time AI-powered interview with instant feedback and analysis",
      icon: ChatBubbleLeftRightIcon,
      color: "bg-blue-500",
      hoverColor: "hover:bg-blue-600",
      href: "/interview",
      features: [
        "Real-time analysis",
        "Voice recognition",
        "Performance metrics",
      ],
    },
    {
      id: "multiple-choice",
      title: "Quick Assessment",
      description:
        "Fast multiple choice tests with instant scoring and explanations",
      icon: CheckCircleIcon,
      color: "bg-green-500",
      hoverColor: "hover:bg-green-600",
      href: "/interview?tab=assessment",
      features: ["Instant results", "Detailed explanations", "Topic analysis"],
    },
    {
      id: "long-answer",
      title: "Written Evaluation",
      description: "Comprehensive written response evaluation with AI grading",
      icon: DocumentTextIcon,
      color: "bg-purple-500",
      hoverColor: "hover:bg-purple-600",
      href: "/test/long-answer",
      features: ["AI grading", "Structure analysis", "Content evaluation"],
    },
    {
      id: "academic",
      title: "Academic Prep",
      description: "Structured academic evaluation and comprehensive testing",
      icon: AcademicCapIcon,
      color: "bg-orange-500",
      hoverColor: "hover:bg-orange-600",
      href: "/test/academic",
      features: ["Academic focus", "Progress tracking", "Customizable tests"],
    },
  ];

  const tips = [
    "Practice regularly to improve your interview skills",
    "Review your performance metrics to identify areas for improvement",
    "Use the AI feedback to refine your communication style",
    "Try different test types to become a well-rounded candidate",
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-6">
            <div className="flex items-center space-x-3">
              <div className="flex items-center justify-center w-10 h-10 bg-indigo-600 rounded-lg">
                <ChatBubbleLeftRightIcon className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-gray-900">IntervueAI</h1>
                <p className="text-gray-600">
                  Welcome back, {user?.name}! Ready to practice?
                </p>
              </div>
            </div>

            {/* Notifications and Profile */}
            <div className="flex items-center space-x-4">
              <button className="relative p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-full">
                <BellIcon className="h-6 w-6" />
                <span className="absolute top-0 right-0 block h-2 w-2 bg-red-500 rounded-full"></span>
              </button>

              {/* Profile Dropdown */}
              <div className="relative" ref={dropdownRef}>
                <button
                  onClick={() => setShowProfileDropdown(!showProfileDropdown)}
                  className="flex items-center space-x-2 text-sm rounded-full focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                >
                  <div className="h-10 w-10 rounded-full bg-indigo-500 flex items-center justify-center">
                    <UserIcon className="h-6 w-6 text-white" />
                  </div>
                  <div className="text-left hidden md:block">
                    <span className="text-gray-700 font-medium block">
                      {user?.name}
                    </span>
                    <span className="text-gray-500 text-xs">
                      {userStats.rank} Member
                    </span>
                  </div>
                  <ChevronDownIcon className="h-4 w-4 text-gray-400" />
                </button>

                {/* Dropdown Menu */}
                {showProfileDropdown && (
                  <div className="absolute right-0 mt-2 w-56 bg-white rounded-md shadow-lg py-2 z-50 border border-gray-200">
                    <div className="px-4 py-2 border-b border-gray-100">
                      <p className="text-sm font-medium text-gray-900">
                        {user?.name}
                      </p>
                      <p className="text-sm text-gray-500">{user?.email}</p>
                    </div>
                    <button
                      onClick={() => {
                        setShowProfileModal(true);
                        setShowProfileDropdown(false);
                      }}
                      className="flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 w-full text-left"
                    >
                      <CogIcon className="h-4 w-4 mr-3" />
                      Profile Settings
                    </button>
                    <button
                      onClick={() => {
                        handleLogout();
                        setShowProfileDropdown(false);
                      }}
                      className="flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 w-full text-left"
                    >
                      <ArrowRightOnRectangleIcon className="h-4 w-4 mr-3" />
                      Logout
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="px-4 py-6 sm:px-0">
          {/* Stats Overview */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center">
                <div className="p-2 bg-blue-100 rounded-lg">
                  <CheckCircleIcon className="h-6 w-6 text-blue-600" />
                </div>
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-600">
                    Tests Completed
                  </p>
                  <p className="text-2xl font-bold text-gray-900">
                    {userStats.testsCompleted}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center">
                <div className="p-2 bg-green-100 rounded-lg">
                  <ChartBarIcon className="h-6 w-6 text-green-600" />
                </div>
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-600">
                    Average Score
                  </p>
                  <p className="text-2xl font-bold text-gray-900">
                    {userStats.averageScore}%
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center">
                <div className="p-2 bg-orange-100 rounded-lg">
                  <ClockIcon className="h-6 w-6 text-orange-600" />
                </div>
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-600">
                    Practice Streak
                  </p>
                  <p className="text-2xl font-bold text-gray-900">
                    {userStats.streakDays} days
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center">
                <div className="p-2 bg-purple-100 rounded-lg">
                  <TrophyIcon className="h-6 w-6 text-purple-600" />
                </div>
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-600">
                    Current Rank
                  </p>
                  <p className="text-2xl font-bold text-gray-900">
                    {userStats.rank}
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Left Column - Test Types */}
            <div className="lg:col-span-2">
              <div className="bg-white rounded-lg shadow">
                <div className="p-6 border-b border-gray-200">
                  <h2 className="text-xl font-bold text-gray-900">
                    Practice Tests
                  </h2>
                  <p className="text-gray-600">
                    Choose your assessment type to get started
                  </p>
                </div>
                <div className="p-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {testTypes.map((test) => {
                      const IconComponent = test.icon;
                      return (
                        <div
                          key={test.id}
                          className="border border-gray-200 rounded-lg hover:shadow-lg transition-all duration-200 cursor-pointer group hover:border-indigo-300"
                          onClick={() => navigate(test.href)}
                        >
                          <div className="p-6">
                            <div className="flex items-start justify-between mb-4">
                              <div
                                className={`${test.color} w-12 h-12 rounded-lg flex items-center justify-center group-hover:scale-110 transition-transform duration-200`}
                              >
                                <IconComponent className="h-6 w-6 text-white" />
                              </div>
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                Popular
                              </span>
                            </div>
                            <h3 className="text-lg font-semibold text-gray-900 mb-2 group-hover:text-indigo-600">
                              {test.title}
                            </h3>
                            <p className="text-gray-600 text-sm mb-4">
                              {test.description}
                            </p>
                            <ul className="space-y-1">
                              {test.features.map((feature, index) => (
                                <li
                                  key={index}
                                  className="flex items-center text-xs text-gray-500"
                                >
                                  <CheckCircleIcon className="h-3 w-3 text-green-500 mr-2" />
                                  {feature}
                                </li>
                              ))}
                            </ul>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Recent Tests Section */}
              <div className="bg-white rounded-lg shadow mt-8">
                <div className="p-6 border-b border-gray-200">
                  <h2 className="text-xl font-bold text-gray-900">
                    Recent Tests
                  </h2>
                  <p className="text-gray-600">Your latest practice sessions</p>
                </div>
                <div className="p-6">
                  <div className="space-y-4">
                    {recentTests.map((test) => (
                      <div
                        key={test.id}
                        className="flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:bg-gray-50"
                      >
                        <div className="flex items-center space-x-4">
                          <div
                            className={`p-2 rounded-lg ${
                              test.type === "interview"
                                ? "bg-blue-100"
                                : test.type === "multiple-choice"
                                ? "bg-green-100"
                                : test.type === "long-answer"
                                ? "bg-purple-100"
                                : "bg-orange-100"
                            }`}
                          >
                            {test.type === "interview" && (
                              <ChatBubbleLeftRightIcon className="h-5 w-5 text-blue-600" />
                            )}
                            {test.type === "multiple-choice" && (
                              <CheckCircleIcon className="h-5 w-5 text-green-600" />
                            )}
                            {test.type === "long-answer" && (
                              <DocumentTextIcon className="h-5 w-5 text-purple-600" />
                            )}
                          </div>
                          <div>
                            <h4 className="font-medium text-gray-900">
                              {test.name}
                            </h4>
                            <p className="text-sm text-gray-500">{test.date}</p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="font-semibold text-gray-900">
                            {test.score}%
                          </p>
                          <p className="text-sm text-gray-500">Score</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column - Sidebar */}
            <div className="space-y-8">
              {/* Upcoming Interviews */}
              <div className="bg-white rounded-lg shadow">
                <div className="p-6 border-b border-gray-200">
                  <h2 className="text-xl font-bold text-gray-900">
                    Upcoming Interviews
                  </h2>
                  <p className="text-gray-600">Your scheduled sessions</p>
                </div>
                <div className="p-6">
                  <div className="space-y-4">
                    {upcomingInterviews.map((interview) => (
                      <div
                        key={interview.id}
                        className="p-4 border border-gray-200 rounded-lg"
                      >
                        <div className="flex justify-between items-start mb-2">
                          <h4 className="font-semibold text-gray-900">
                            {interview.company}
                          </h4>
                          <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                            Scheduled
                          </span>
                        </div>
                        <p className="text-sm text-gray-600 mb-2">
                          {interview.role}
                        </p>
                        <div className="flex items-center text-sm text-gray-500">
                          <CalendarIcon className="h-4 w-4 mr-1" />
                          {interview.date} at {interview.time}
                        </div>
                      </div>
                    ))}
                  </div>
                  <button className="w-full mt-4 bg-gray-100 hover:bg-gray-200 text-gray-700 py-2 px-4 rounded-lg text-sm font-medium transition-colors duration-200">
                    Schedule New Interview
                  </button>
                </div>
              </div>

              {/* AI Tips */}
              <div className="bg-gradient-to-r from-indigo-500 to-purple-600 rounded-lg shadow text-white">
                <div className="p-6">
                  <div className="flex items-center mb-4">
                    <LightBulbIcon className="h-6 w-6 mr-2" />
                    <h2 className="text-xl font-bold">AI Pro Tips</h2>
                  </div>
                  <div className="space-y-3">
                    {tips.map((tip, index) => (
                      <div key={index} className="flex items-start">
                        <StarIcon className="h-4 w-4 mt-1 mr-2 flex-shrink-0" />
                        <p className="text-sm opacity-90">{tip}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Quick Actions */}
              <div className="bg-white rounded-lg shadow">
                <div className="p-6 border-b border-gray-200">
                  <h2 className="text-xl font-bold text-gray-900">
                    Quick Actions
                  </h2>
                </div>
                <div className="p-6">
                  <div className="grid grid-cols-2 gap-4">
                    <button className="flex flex-col items-center p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors duration-200">
                      <UsersIcon className="h-6 w-6 text-gray-600 mb-2" />
                      <span className="text-sm font-medium text-gray-700">
                        Mock Interview
                      </span>
                    </button>
                    <button className="flex flex-col items-center p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors duration-200">
                      <QuestionMarkCircleIcon className="h-6 w-6 text-gray-600 mb-2" />
                      <span className="text-sm font-medium text-gray-700">
                        FAQs
                      </span>
                    </button>
                    <button className="flex flex-col items-center p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors duration-200">
                      <ShieldCheckIcon className="h-6 w-6 text-gray-600 mb-2" />
                      <span className="text-sm font-medium text-gray-700">
                        Privacy
                      </span>
                    </button>
                    <button className="flex flex-col items-center p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors duration-200">
                      <ChartBarIcon className="h-6 w-6 text-gray-600 mb-2" />
                      <span className="text-sm font-medium text-gray-700">
                        Analytics
                      </span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Profile Modal - Keep existing modal code, but I'll add a small enhancement */}
      {showProfileModal && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
          <div className="relative top-20 mx-auto p-5 border w-96 shadow-lg rounded-md bg-white">
            <div className="mt-3">
              {/* Modal Header */}
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-2">
                  <ShieldCheckIcon className="h-5 w-5 text-indigo-600" />
                  <h3 className="text-lg font-medium text-gray-900">
                    Profile Settings
                  </h3>
                </div>
                <button
                  onClick={() => setShowProfileModal(false)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <span className="sr-only">Close</span>
                  <svg
                    className="h-6 w-6"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </div>

              {/* Rest of the modal code remains the same */}
              {/* Tabs */}
              <div className="border-b border-gray-200 mb-4">
                <nav className="-mb-px flex space-x-8">
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

              {/* Profile Tab */}
              {activeTab === "profile" && (
                <div>
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

                    <div className="flex justify-end space-x-3">
                      <button
                        type="button"
                        onClick={() => setShowProfileModal(false)}
                        className="bg-gray-300 hover:bg-gray-400 text-gray-700 px-4 py-2 rounded-md text-sm font-medium"
                      >
                        Cancel
                      </button>
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

                    <div className="flex justify-end space-x-3">
                      <button
                        type="button"
                        onClick={() => setShowProfileModal(false)}
                        className="bg-gray-300 hover:bg-gray-400 text-gray-700 px-4 py-2 rounded-md text-sm font-medium"
                      >
                        Cancel
                      </button>
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
      )}
    </div>
  );
};

export default Dashboard;
