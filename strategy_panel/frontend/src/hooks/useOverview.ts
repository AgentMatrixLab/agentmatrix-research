import { useEffect, useState } from "react";
import { getOverview, type ApiOverviewFolio } from "@/api";

export function useOverview() {
  const [folio, setFolio] = useState<ApiOverviewFolio | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getOverview()
      .then((data) => {
        if (!cancelled) {
          setFolio(data.folio);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  return { folio, loading };
}
