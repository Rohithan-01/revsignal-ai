"use client";

import { useEffect } from "react";
import { animate, motion, useMotionValue, useReducedMotion, useTransform } from "framer-motion";
import type { ReactNode } from "react";
import { formatCompactCurrency } from "@/lib/formatters";

interface MetricCardProps {
  label: string;
  value: number;
  kind: "currency" | "count";
  icon: ReactNode;
  iconStyle: string;
  help: string;
  detail: ReactNode;
  index: number;
}

export function MetricCard({ label, value, kind, icon, iconStyle, help, detail, index }: MetricCardProps) {
  const reducedMotion = useReducedMotion();
  const animatedValue = useMotionValue(0);
  const display = useTransform(animatedValue, (current) =>
    kind === "currency" ? formatCompactCurrency(current) : Math.round(current).toLocaleString("en-IN"),
  );

  useEffect(() => {
    if (reducedMotion) {
      animatedValue.set(value);
      return;
    }
    const controls = animate(animatedValue, value, {
      duration: 0.85,
      delay: index * 0.06,
      ease: [0.22, 1, 0.36, 1],
    });
    return controls.stop;
  }, [animatedValue, index, reducedMotion, value]);

  return (
    <motion.article
      className="kpi-card"
      initial={reducedMotion ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: reducedMotion ? 0 : index * 0.06 }}
    >
      <div className="kpi-top">
        <span className={`kpi-icon ${iconStyle}`}>{icon}</span>
        <span className="kpi-label">{label}<span className="tooltip-wrap" title={help} aria-label={help}><span className="sr-only">Metric definition: </span><i>i</i></span></span>
      </div>
      <div className="kpi-value"><motion.span>{display}</motion.span>{kind === "count" && <span className="kpi-unit"> deals</span>}</div>
      <div className="kpi-foot">{detail}</div>
    </motion.article>
  );
}
