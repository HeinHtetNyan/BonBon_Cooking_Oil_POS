import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  LayoutDashboard, FileText, Users, Package, Factory,
  Receipt, BarChart3, UserCog, ChevronLeft, Droplets, X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/store/ui";
import { useAuthStore } from "@/store/auth";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";

const navItems = [
  { to: "/dashboard", icon: LayoutDashboard, key: "nav.dashboard",     roles: [] },
  { to: "/vouchers",  icon: FileText,        key: "nav.salesVouchers", roles: [] },
  { to: "/customers", icon: Users,           key: "nav.customers",     roles: [] },
  { to: "/inventory", icon: Package,         key: "nav.inventory",     roles: [] },
  { to: "/production",icon: Factory,         key: "nav.production",    roles: ["warehouse","manager","admin","super_admin"] },
  { to: "/expenses",  icon: Receipt,         key: "nav.expenses",      roles: [] },
  { to: "/reports",   icon: BarChart3,       key: "nav.reports",       roles: ["accountant","manager","admin","super_admin"] },
  { to: "/users",     icon: UserCog,         key: "nav.users",         roles: ["admin","super_admin","manager"] },
];

interface SidebarProps {
  onMobileClose?: () => void;
}

export function Sidebar({ onMobileClose }: SidebarProps) {
  const { t } = useTranslation();
  const { sidebarOpen, toggleSidebar } = useUIStore();
  const { user } = useAuthStore();

  const visibleItems = navItems.filter(
    (item) => item.roles.length === 0 || (user && item.roles.includes(user.role)),
  );

  /* On mobile the sidebar is always full-width (w-60).
     On desktop it follows the sidebarOpen toggle (w-60 / w-16). */
  const desktopWidth = sidebarOpen ? "lg:w-60" : "lg:w-16";

  return (
    <aside className={cn(
      "flex flex-col h-full bg-sidebar text-sidebar-foreground border-r border-sidebar-border transition-all duration-300 shrink-0",
      "w-64 sm:w-60",
      desktopWidth,
    )}>
      {/* Logo + close button */}
      <div className="flex items-center gap-3 px-4 h-14 shrink-0 border-b border-sidebar-border">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary shrink-0">
          <Droplets className="w-4 h-4 text-white" />
        </div>
        <div className={cn("overflow-hidden flex-1 min-w-0", !sidebarOpen && "lg:hidden")}>
          <p className="text-sm font-bold text-white truncate">Bon Bon Oil</p>
          <p className="text-xs text-sidebar-foreground/60 truncate">{t("nav.erpSystem")}</p>
        </div>
        {/* Mobile-only close button */}
        <Button
          variant="ghost"
          size="icon"
          onClick={onMobileClose}
          className="lg:hidden shrink-0 text-sidebar-foreground hover:bg-sidebar-muted hover:text-white"
        >
          <X className="w-4 h-4" />
        </Button>
      </div>

      <ScrollArea className="flex-1 py-4">
        <nav className="space-y-1 px-2">
          {visibleItems.map(({ to, icon: Icon, key }) => (
            <NavLink
              key={to}
              to={to}
              onClick={onMobileClose}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors",
                  isActive
                    ? "bg-primary text-white"
                    : "text-sidebar-foreground hover:bg-sidebar-muted hover:text-white",
                )
              }
            >
              <Icon className="w-4 h-4 shrink-0" />
              <span className={cn("truncate", !sidebarOpen && "lg:hidden")}>{t(key)}</span>
            </NavLink>
          ))}
        </nav>
      </ScrollArea>

      {/* Collapse toggle — desktop only */}
      <div className="hidden lg:block p-2 border-t border-sidebar-border">
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleSidebar}
          className="w-full text-sidebar-foreground hover:bg-sidebar-muted hover:text-white"
        >
          <ChevronLeft className={cn("w-4 h-4 transition-transform", !sidebarOpen && "rotate-180")} />
        </Button>
      </div>
    </aside>
  );
}
