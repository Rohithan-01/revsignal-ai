"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, ApiConnectionError } from "@/lib/api";
import { demoDeals, demoMetrics } from "@/lib/demo-data";
import type { Deal, Metrics, RevenueData } from "@/lib/types";

const RevenueContext = createContext<RevenueData | null>(null);

export function RevenueDataProvider({ children }: { children: ReactNode }) {
  const [deals, setDeals] = useState<Deal[]>([]);
  const [metrics, setMetrics] = useState<Metrics>(demoMetrics([]));
  const [source, setSource] = useState<RevenueData["source"]>("demo");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await api.health();
      const [liveDeals, liveMetrics] = await Promise.all([api.deals(), api.metrics()]);
      setDeals(liveDeals);
      setMetrics(liveMetrics);
      setSource("live");
    } catch (reason) {
      if (reason instanceof ApiConnectionError) {
        setDeals(demoDeals);
        setMetrics(demoMetrics(demoDeals));
        setSource("demo");
      } else {
        setError(reason instanceof Error ? reason.message : "Unable to load revenue data.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const replaceDeal = useCallback((updated: Deal) => {
    setDeals((current) =>
      current.map((deal) => (deal.deal_id === updated.deal_id ? updated : deal)),
    );
    setMetrics((current) => {
      const updatedDeals = deals.map((deal) =>
        deal.deal_id === updated.deal_id ? updated : deal,
      );
      return source === "demo" ? demoMetrics(updatedDeals) : current;
    });
  }, [deals, source]);

  const value = useMemo(
    () => ({ deals, metrics, source, loading, error, refresh, replaceDeal }),
    [deals, metrics, source, loading, error, refresh, replaceDeal],
  );
  return <RevenueContext.Provider value={value}>{children}</RevenueContext.Provider>;
}

export function useRevenueData(): RevenueData {
  const context = useContext(RevenueContext);
  if (!context) throw new Error("useRevenueData must be used inside RevenueDataProvider.");
  return context;
}
