import { useEffect, useState } from "react";
import { Activity, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  fetchAuthConfig,
  googleLoginUrl,
  login,
  microsoftLoginUrl,
  register,
  resendVerification,
  type AuthConfig,
  type AuthUser,
} from "@/lib/auth";

type LoginViewProps = {
  onSuccess: (user: AuthUser) => void;
};

type AuthMode = "signin" | "signup";

function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
  );
}

function MicrosoftIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#f25022" d="M1 1h10v10H1z" />
      <path fill="#00a4ef" d="M13 1h10v10H13z" />
      <path fill="#7fba00" d="M1 13h10v10H1z" />
      <path fill="#ffb900" d="M13 13h10v10H13z" />
    </svg>
  );
}

export default function LoginView({ onSuccess }: LoginViewProps) {
  const [mode, setMode] = useState<AuthMode>("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null);

  useEffect(() => {
    fetchAuthConfig().then(setAuthConfig).catch(() => {
      setAuthConfig({ auth_enabled: true, google: false, microsoft: false, password: true, signup: false });
    });

    const params = new URLSearchParams(window.location.search);
    const authError = params.get("auth_error");
    if (authError === "verify_failed") {
      setError("Email verification link is invalid or expired.");
      window.history.replaceState({}, "", window.location.pathname);
    } else if (authError) {
      setError("Sign-in was cancelled or failed. Please try again.");
      window.history.replaceState({}, "", window.location.pathname);
    }
    if (params.get("email_verified") === "1") {
      setInfo("Email confirmed. Signing you in…");
      setMode("signin");
      window.history.replaceState({}, "", window.location.pathname);
      window.location.reload();
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setLoading(true);
    try {
      if (mode === "signup") {
        const result = await register(email.trim(), password, name.trim() || undefined);
        setInfo(
          result.message ||
            `Account created. Confirm the link we sent to ${result.email || email} before signing in.`,
        );
        setMode("signin");
      } else {
        const result = await login(email.trim(), password);
        onSuccess(result);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : mode === "signup" ? "Sign up failed" : "Sign in failed");
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    if (!email.trim()) {
      setError("Enter your email to resend the confirmation link.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await resendVerification(email.trim());
      setInfo(`If an account exists for ${email.trim()}, we sent a new confirmation email.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resend email");
    } finally {
      setLoading(false);
    }
  };

  const showGoogle = authConfig?.google ?? false;
  const showMicrosoft = authConfig?.microsoft ?? false;
  const showSocial = mode === "signin" && (showGoogle || showMicrosoft);
  const showPassword = authConfig?.password ?? true;
  const showSignup = authConfig?.signup ?? false;

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden p-6">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_50%_-10%,hsl(262_83%_58%/0.12),transparent)]" />
      <div className="pointer-events-none absolute -right-32 top-20 h-96 w-96 rounded-full bg-violet-500/10 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-32 -left-20 h-80 w-80 rounded-full bg-primary/10 blur-3xl" />

      <div className="relative w-full max-w-md">
        <div className="vd-panel-elevated border-border/40 p-8 shadow-2xl shadow-primary/5">
          <div className="mb-8 flex flex-col items-center text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-violet-600 shadow-lg shadow-primary/30">
              <Activity className="h-7 w-7 text-white" />
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">VisionDock</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {mode === "signup" ? "Create your workspace account" : "Sign in to your workspace"}
            </p>
          </div>

          {showSignup && (
            <div className="mb-4 flex rounded-lg bg-muted p-1">
              <button
                type="button"
                className={`flex-1 rounded-md py-2 text-sm font-medium transition-colors ${
                  mode === "signin" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground"
                }`}
                onClick={() => { setMode("signin"); setError(null); setInfo(null); }}
              >
                Sign in
              </button>
              <button
                type="button"
                className={`flex-1 rounded-md py-2 text-sm font-medium transition-colors ${
                  mode === "signup" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground"
                }`}
                onClick={() => { setMode("signup"); setError(null); setInfo(null); }}
              >
                Sign up
              </button>
            </div>
          )}

          {showSocial && (
            <div className="space-y-3">
              {showMicrosoft && (
                <Button type="button" variant="outline" className="h-11 w-full" onClick={() => { window.location.href = microsoftLoginUrl(); }}>
                  <MicrosoftIcon className="mr-2 h-5 w-5" />
                  Continue with Microsoft
                </Button>
              )}
              {showGoogle && (
                <Button type="button" variant="outline" className="h-11 w-full" onClick={() => { window.location.href = googleLoginUrl(); }}>
                  <GoogleIcon className="mr-2 h-5 w-5" />
                  Continue with Google
                </Button>
              )}
              {showPassword && (
                <div className="relative pt-1">
                  <div className="absolute inset-0 flex items-center">
                    <span className="w-full border-t border-border" />
                  </div>
                  <div className="relative flex justify-center text-xs uppercase">
                    <span className="bg-card px-2 text-muted-foreground">or</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {showPassword && (
            <form onSubmit={handleSubmit} className={`space-y-4 ${showSocial ? "mt-4" : ""}`}>
              {mode === "signup" && (
                <div className="space-y-2">
                  <label htmlFor="name" className="text-sm font-medium text-foreground">Name</label>
                  <Input id="name" type="text" autoComplete="name" placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} className="h-11" />
                </div>
              )}
              <div className="space-y-2">
                <label htmlFor="email" className="text-sm font-medium text-foreground">
                  {mode === "signup" ? "Email" : "Email or username"}
                </label>
                <Input id="email" type={mode === "signup" ? "email" : "text"} autoComplete={mode === "signup" ? "email" : "username"} placeholder={mode === "signup" ? "you@company.com" : "admin@visiondock.local"} value={email} onChange={(e) => setEmail(e.target.value)} required className="h-11" />
              </div>
              <div className="space-y-2">
                <label htmlFor="password" className="text-sm font-medium text-foreground">Password</label>
                <Input id="password" type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} placeholder={mode === "signup" ? "At least 8 characters" : "••••••••••••"} value={password} onChange={(e) => setPassword(e.target.value)} required minLength={mode === "signup" ? 8 : undefined} className="h-11" />
              </div>

              {info && (
                <div className="space-y-2 rounded-lg border border-emerald-500/20 bg-emerald-500/8 px-3 py-2 text-sm text-emerald-800">
                  <p>{info}</p>
                  {mode === "signin" && info.toLowerCase().includes("confirm") && (
                    <button type="button" className="text-xs font-semibold text-emerald-900 underline" onClick={() => void handleResend()} disabled={loading}>
                      Resend confirmation email
                    </button>
                  )}
                </div>
              )}

              {error && (
                <div className="rounded-lg border border-destructive/20 bg-destructive/8 px-3 py-2 text-sm text-destructive">{error}</div>
              )}

              <Button type="submit" disabled={loading} className="h-11 w-full shadow-lg shadow-primary/20">
                {loading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    {mode === "signup" ? "Creating account…" : "Signing in…"}
                  </>
                ) : mode === "signup" ? (
                  "Create account"
                ) : (
                  "Sign in"
                )}
              </Button>
            </form>
          )}

          {!showPassword && showSocial && error && (
            <div className="mt-4 rounded-lg border border-destructive/20 bg-destructive/8 px-3 py-2 text-sm text-destructive">{error}</div>
          )}
        </div>
        <p className="mt-6 text-center text-xs text-muted-foreground">VisionDock · Computer Vision Platform</p>
      </div>
    </div>
  );
}
