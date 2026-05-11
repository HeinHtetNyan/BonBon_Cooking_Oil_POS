import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { useUIStore } from "@/store/ui";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";
import { usePendingUploads } from "@/hooks/usePendingUploads";
import { cn } from "@/lib/utils";

export function AppLayout() {
  const { mobileSidebarOpen, setMobileSidebarOpen } = useUIStore();
  const online = useOnlineStatus();
  const pendingUploads = usePendingUploads();

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Mobile overlay backdrop */}
      {mobileSidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setMobileSidebarOpen(false)}
        />
      )}

      {/* Sidebar: overlay on mobile, static on desktop */}
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex lg:static lg:z-auto",
          mobileSidebarOpen ? "flex" : "hidden lg:flex",
        )}
      >
        <Sidebar onMobileClose={() => setMobileSidebarOpen(false)} />
      </div>

      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Header />

        {/* Offline / pending-upload banner */}
        {!online && (
          <div className="bg-destructive/10 border-b border-destructive/20 px-4 py-2 text-xs text-destructive font-medium text-center">
            No internet connection — your data is saved and will upload automatically when reconnected.
          </div>
        )}
        {online && pendingUploads > 0 && (
          <div className="bg-orange-50 border-b border-orange-200 px-4 py-2 text-xs text-orange-700 font-medium text-center animate-pulse">
            Uploading {pendingUploads} saved {pendingUploads === 1 ? "item" : "items"}…
          </div>
        )}

        <main className="flex-1 overflow-auto p-4 sm:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
