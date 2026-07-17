"use client";

/**
 * Shared helpers for low-credit warnings.
 * Plan monthly allowances must stay in sync with server PLAN_CREDITS / plan_limits.
 */
export const PLAN_MONTHLY_CREDITS = {
  free: 3,
  creator: 120,
  pro: 300,
};

/** True when remaining credits are below 20% of the plan's monthly allowance. */
export function isLowCredits(credits, plan) {
  const allowance = PLAN_MONTHLY_CREDITS[plan] ?? PLAN_MONTHLY_CREDITS.free;
  if (typeof credits !== "number" || credits < 0) return false;
  return credits > 0 && credits < allowance * 0.2;
}

export function isOutOfCredits(credits) {
  return typeof credits === "number" && credits <= 0;
}
