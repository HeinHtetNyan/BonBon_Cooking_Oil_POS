import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 0,
      gcTime: 1000 * 60 * 60 * 24, // keep cache 24h so offline still shows data
      retry: 2,
      retryDelay: 1_000,
      refetchOnWindowFocus: true,
      refetchOnMount: true,
      refetchOnReconnect: true,
      refetchInterval: 3_000,
      refetchIntervalInBackground: false,
      networkMode: "offlineFirst",
    },
    mutations: {
      networkMode: "offlineFirst", // queue mutations while offline, fire when reconnected
      retry: 2,
      retryDelay: 2_000,
    },
  },
});
