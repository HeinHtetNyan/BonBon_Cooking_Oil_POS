import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { authApi } from "@/api/auth";
import { useAuthStore } from "@/store/auth";
import { getErrorMessage } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";

const loginSchema = z.object({
  username: z.string().min(1),
  password: z.string().min(1),
});
type LoginForm = z.infer<typeof loginSchema>;

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { setAuth } = useAuthStore();
  const [error, setError] = useState<string | null>(null);

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
  });

  async function onSubmit(data: LoginForm) {
    setError(null);
    try {
      const res = await authApi.login(data);
      setAuth(res.user, res.tokens.access_token, res.tokens.refresh_token);
      navigate("/dashboard");
    } catch (e) {
      setError(getErrorMessage(e));
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-8">
        <div className="flex flex-col items-center gap-3">
          <div className="flex items-center justify-center w-14 h-14 rounded-2xl overflow-hidden shadow-lg">
            <img src="/logo.jpg" alt="Bon Bon Oil" className="w-full h-full object-cover" />
          </div>
          <div className="text-center">
            <h1 className="text-2xl font-bold">Bon Bon Oil</h1>
            <p className="text-sm text-muted-foreground">{t("auth.enterpriseResourcePlanning")}</p>
          </div>
        </div>

        <div className="bg-card rounded-xl border shadow-sm p-6 space-y-5">
          <div>
            <h2 className="text-lg font-semibold">{t("auth.signIn")}</h2>
            <p className="text-sm text-muted-foreground">{t("auth.enterCredentials")}</p>
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" autoComplete="off">
            <div className="space-y-1.5">
              <Label htmlFor="username">{t("auth.username")}</Label>
              <Input id="username" placeholder={t("auth.enterUsername")} {...register("username")} />
              {errors.username && <p className="text-xs text-destructive">{t("auth.usernameRequired")}</p>}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">{t("auth.password")}</Label>
              <Input id="password" type="password" placeholder={t("auth.enterPassword")} {...register("password")} />
              {errors.password && <p className="text-xs text-destructive">{t("auth.passwordRequired")}</p>}
            </div>

            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" />{t("auth.signingIn")}</>
              ) : t("auth.signIn")}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
