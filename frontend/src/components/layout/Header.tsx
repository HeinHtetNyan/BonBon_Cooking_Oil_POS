import { Menu, Bell, LogOut, User, Settings, Wifi, WifiOff, Loader2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useIsMutating } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth";
import { useUIStore } from "@/store/ui";
import { authApi } from "@/api/auth";
import { queryClient } from "@/lib/queryClient";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { ROLES } from "@/lib/constants";
import i18n from "@/i18n";

function LanguageToggle() {
  const lang = i18n.language;
  function toggle() {
    const next = lang === "en" ? "mm" : "en";
    i18n.changeLanguage(next);
    localStorage.setItem("lang", next);
  }
  return (
    <Button variant="outline" size="sm" onClick={toggle} className="font-medium text-xs px-3">
      {lang === "en" ? "မြန်မာ" : "ENG"}
    </Button>
  );
}

export function Header() {
  const { t } = useTranslation();
  const { user, clearAuth, refreshToken } = useAuthStore();
  const { toggleSidebar, setMobileSidebarOpen } = useUIStore();
  const navigate = useNavigate();
  const online = useOnlineStatus();
  const pendingMutations = useIsMutating();

  async function handleLogout() {
    try {
      await authApi.logout(refreshToken ?? undefined);
    } finally {
      clearAuth();
      queryClient.clear();
      navigate("/login");
    }
  }

  const initials = user?.full_name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2) ?? "??";

  return (
    <header className="h-14 flex items-center justify-between px-4 border-b bg-background shrink-0">
      {/* Mobile hamburger — opens overlay sidebar */}
      <Button variant="ghost" size="icon" onClick={() => setMobileSidebarOpen(true)} className="lg:hidden">
        <Menu className="w-5 h-5" />
      </Button>
      {/* Desktop hamburger — collapses/expands sidebar */}
      <Button variant="ghost" size="icon" onClick={toggleSidebar} className="hidden lg:flex">
        <Menu className="w-5 h-5" />
      </Button>

      <div className="flex-1" />

      <div className="flex items-center gap-2">
        {!online ? (
          <div className="flex items-center gap-1.5 text-xs text-destructive font-medium animate-pulse">
            <WifiOff className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Offline — data will upload when reconnected</span>
          <span className="sm:hidden">Offline</span>
          </div>
        ) : pendingMutations > 0 ? (
          <div className="hidden sm:flex items-center gap-1.5 text-xs text-orange-500 font-medium">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            <span>Uploading…</span>
          </div>
        ) : (
          <div className="hidden sm:flex items-center gap-1.5 text-xs text-green-600 font-medium">
            <Wifi className="w-3.5 h-3.5" />
            <span>Live</span>
          </div>
        )}

        <LanguageToggle />

        <Button variant="ghost" size="icon">
          <Bell className="w-5 h-5" />
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="flex items-center gap-2 px-2">
              <Avatar className="w-8 h-8">
                <AvatarFallback className="bg-primary text-white text-xs">{initials}</AvatarFallback>
              </Avatar>
              <div className="hidden md:block text-left">
                <p className="text-sm font-medium">{user?.full_name}</p>
                <p className="text-xs text-muted-foreground">{user?.role ? ROLES[user.role] : ""}</p>
              </div>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuLabel>
              <p className="font-medium">{user?.full_name}</p>
              <p className="text-xs text-muted-foreground font-normal">{user?.email}</p>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate("/profile")}>
              <User className="mr-2 h-4 w-4" /> {t("header.profile")}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => navigate("/settings")}>
              <Settings className="mr-2 h-4 w-4" /> {t("header.settings")}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleLogout} className="text-destructive focus:text-destructive">
              <LogOut className="mr-2 h-4 w-4" /> {t("header.logout")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
