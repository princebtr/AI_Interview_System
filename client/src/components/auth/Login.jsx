import { useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { useAuth } from "../../context/AuthContext";
import api from "../../utils/axios";
import { applyTheme } from "../../utils/theme";
import AuthLayout from "./AuthLayout";
import { Button, Input } from "../ui";

const Login = () => {
  const { login, loading, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || "/dashboard";
  const [params] = useSearchParams();
  const school = params.get("school");
  const [brand, setBrand] = useState(null);

  // /login?school=<slug> shows that institution's logo and name.
  useEffect(() => {
    if (!school) return undefined;
    let cancelled = false;
    api
      .get(`/institutions/by-slug/${encodeURIComponent(school)}`)
      .then(({ data }) => !cancelled && setBrand(data))
      .catch(() => {}); // unknown school: fall back to the Cohortix sign-in
    return () => {
      cancelled = true;
    };
  }, [school]);

  useEffect(() => {
    document.title = brand ? `Sign in · ${brand.name}` : "Sign in · Cohortix";
    if (brand) applyTheme(brand.theme?.palette ?? null); // the school's colours, as its students will see them
  }, [brand]);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm();

  if (isAuthenticated) return <Navigate to={from} replace />;

  const onSubmit = async (data) => {
    const result = await login(data);
    if (result.success) navigate(from, { replace: true });
  };

  return (
    <AuthLayout
      brand={brand}
      title={brand ? `Sign in to ${brand.name}` : "Sign in"}
      subtitle="Welcome back. Pick up where you left off."
      footer="No account yet? Your institution's administrator creates accounts for students and educators."
    >
      <form className="space-y-5" onSubmit={handleSubmit(onSubmit)} noValidate>
        <Input
          id="email"
          label="Email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          error={errors.email?.message}
          {...register("email", {
            required: "Enter your email",
            pattern: { value: /^\S+@\S+\.\S+$/, message: "Enter a valid email address" },
          })}
        />
        <Input
          id="password"
          label="Password"
          type="password"
          autoComplete="current-password"
          error={errors.password?.message}
          {...register("password", { required: "Enter your password" })}
        />
        <Button type="submit" size="lg" loading={loading} className="w-full">
          Sign in
        </Button>
      </form>
    </AuthLayout>
  );
};

export default Login;
