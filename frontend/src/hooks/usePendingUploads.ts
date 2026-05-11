import { useEffect, useState } from "react";
import { queryClient } from "@/lib/queryClient";

export function usePendingUploads(): number {
  const [count, setCount] = useState(() =>
    queryClient.getMutationCache().getAll().filter((m) => m.state.isPaused).length
  );

  useEffect(() => {
    const cache = queryClient.getMutationCache();
    const update = () => {
      setCount(cache.getAll().filter((m) => m.state.isPaused).length);
    };
    const unsubscribe = cache.subscribe(update);
    return unsubscribe;
  }, []);

  return count;
}
