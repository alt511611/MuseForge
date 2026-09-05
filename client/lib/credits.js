"use client";

/**
 * Shared helpers for low-credit warnings.
 * Plan monthly allowances must stay in sync with server PLAN_CREDITS / plan_limits.
 */
export const PLAN_MONTHLY_CREDITS = {
  free: 3,
  creator: 25,
  pro: 55,
};

/** True when remaining credits are below 20% of the plan's monthly allowance. */
export function isLowCredits(credits, plan) {
  const allowance = PLAN_MONTHLY_CREDITS[plan] ?? PLAN_MONTHLY_CREDITS.free;
  if (typeof credits !== "number" || credits < 0) return false;
  return credits > 0 && credits < allowance * 0.2;
}

/** True only when the balance is KNOWN to be empty.
 *
 * The server answers -1 when it could not read the balance at all
 * (api._get_user_credits), and that number reaches this function through
 * /api/credits. Treating it as "<= 0" told a customer with a full account
 * that they were out of credits every time Supabase hiccuped -- the one
 * message that makes someone stop using a product they have paid for.
 * Unknown is not empty: it shows the account as it was.
 */
export function isOutOfCredits(credits) {
  return credits === 0;
}
