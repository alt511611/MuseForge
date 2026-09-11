"use client";

/**
 * Shared helpers for low-credit warnings.
 *
 * The allowances below are a COPY. The grants themselves are made by the
 * server (stripe_integration.PLAN_CREDITS) and by the database
 * (public.plan_limits in supabase_migration.sql); this file only needs them
 * to decide when a balance has fallen far enough to warn about.
 *
 * A copy is only safe while something checks it, so something does:
 * server/tests/test_one_allowance_in_three_places.py reads this file and
 * fails when the three disagree. They disagreed once -- this table still said
 * 25 and 55 after the real grants moved to 16 and 36 -- and the only visible
 * symptom was a low-credit banner appearing at the wrong balance, which is
 * not the kind of thing anybody reports.
 */
export const PLAN_MONTHLY_CREDITS = {
  free: 3,
  creator: 16,
  pro: 36,
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
