import { useEffect } from "react";
import { RouterProvider } from "react-router-dom";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import type { Persister } from "@tanstack/react-query-persist-client";
import { queryClient } from "@/lib/queryClient";
import { router } from "@/router";
import { Toaster } from "@/components/ui/toaster";

const CACHE_KEY = "bonbon-cache-v1";

const persister: Persister = {
  persistClient: (client) => {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify(client)); } catch { /* storage full */ }
  },
  restoreClient: () => {
    try {
      const raw = localStorage.getItem(CACHE_KEY);
      return raw ? JSON.parse(raw) : undefined;
    } catch { return undefined; }
  },
  removeClient: () => {
    try { localStorage.removeItem(CACHE_KEY); } catch { /* ignore */ }
  },
};

function ReconnectSync() {
  useEffect(() => {
    function resume() {
      queryClient.resumePausedMutations().then(() => {
        queryClient.invalidateQueries();
      });
    }
    window.addEventListener("online", resume);
    return () => window.removeEventListener("online", resume);
  }, []);
  return null;
}

export default function App() {
  return (
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister,
        maxAge: 1000 * 60 * 60 * 24, // 24h
        buster: "v1",
      }}
      onSuccess={() => {
        // After restoring cache on startup, resume any mutations that were
        // paused from a previous session (e.g. form submitted while offline)
        if (navigator.onLine) {
          queryClient.resumePausedMutations().then(() => {
            queryClient.invalidateQueries();
          });
        }
      }}
    >
      <ReconnectSync />
      <RouterProvider router={router} />
      <Toaster />
    </PersistQueryClientProvider>
  );
}
