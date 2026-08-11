-- MuseForge — Supabase Migration v2
-- Supabase Dashboard → SQL Editor'de çalıştırın.

-- ── Profiller tablosu ─────────────────────────────────────────────────────────
create table if not exists public.profiles (
  id              uuid references auth.users on delete cascade primary key,
  email           text,
  role            text        not null default 'user',   -- 'user' | 'admin'
  plan            text        not null default 'free',   -- 'free' | 'creator' | 'pro'
  credits         int         not null default 3,        -- ücretsiz kredit
  stripe_customer_id text,
  stripe_subscription_id text,
  created_at      timestamptz default now(),
  updated_at      timestamptz default now()
);

-- Yeni kullanıcı kaydında otomatik profil oluştur
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- updated_at otomatik güncelle
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists profiles_updated_at on public.profiles;
create trigger profiles_updated_at
  before update on public.profiles
  for each row execute procedure public.set_updated_at();

-- ── Jobs tablosu (isteğe bağlı kalıcı depolama) ───────────────────────────────
create table if not exists public.jobs (
  id              text primary key,
  user_id         uuid references auth.users on delete set null,
  user_email      text,
  idea            text,
  style           text        default 'Cinematic',
  director_style  text        default 'cinematic_balanced',
  aspect_ratio    text        default '16:9',
  num_scenes      int         default 3,
  user_requirement text       default '',
  demo            boolean     default false,
  status          text        default 'queued',
  result          jsonb,
  error           text,
  created_at      timestamptz default now(),
  updated_at      timestamptz default now()
);

drop trigger if exists jobs_updated_at on public.jobs;
create trigger jobs_updated_at
  before update on public.jobs
  for each row execute procedure public.set_updated_at();

-- ── Row Level Security ────────────────────────────────────────────────────────
alter table public.profiles enable row level security;
alter table public.jobs     enable row level security;

-- Kullanıcılar kendi profilini okur/günceller
create policy "users_read_own_profile"
  on public.profiles for select using (auth.uid() = id);

create policy "users_update_own_profile"
  on public.profiles for update using (auth.uid() = id);

-- Kullanıcılar kendi job'larını görür
create policy "users_read_own_jobs"
  on public.jobs for select using (auth.uid() = user_id);

-- Adminler her şeyi yönetir.
--
-- NOTE: this checks the JWT's app_metadata directly via auth.jwt(), NOT a
-- subquery against public.profiles. A policy on public.profiles that itself
-- queries public.profiles (`exists (select 1 from public.profiles where ...)`)
-- is a well-known Supabase/Postgres footgun — it can trigger
-- "infinite recursion detected in policy for relation profiles" at query
-- time. Reading the role out of the JWT avoids the self-reference entirely.
-- This requires setting the role in auth.users.raw_app_meta_data (see the
-- "Admin atama" section below), not just in the profiles table.
create policy "admins_all_profiles"
  on public.profiles for all
  using (coalesce(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'admin');

create policy "admins_all_jobs"
  on public.jobs for all
  using (coalesce(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'admin');

-- ── Plan limitleri yardımcı görünümü ──────────────────────────────────────────
create or replace view public.plan_limits as
select
  'free'    as plan, 3  as monthly_credits, 3  as max_scenes, false as hd_export
union all
select 'creator',       30, 5, false
union all
select 'pro',          150, 5, true;

-- ── Credit Ledger (hareket geçmişi) ──────────────────────────────────────────
create table if not exists public.credit_ledger (
  id          bigserial primary key,
  user_id     uuid references auth.users on delete cascade not null,
  amount      int not null,              -- pozitif = ekleme, negatif = kullanım
  reason      text not null default '',  -- 'video_generation' | 'subscription_renewal' | 'credit_purchase' | 'refund'
  job_id      text,                      -- ilgili job (varsa)
  created_at  timestamptz default now()
);

alter table public.credit_ledger enable row level security;

create policy "users_read_own_ledger"
  on public.credit_ledger for select using (auth.uid() = user_id);

create policy "service_insert_ledger"
  on public.credit_ledger for insert
  with check (true);   -- service key ile insert, RLS bypass için service role kullanılır

-- Plan limitleri görünümünü yeni değerlerle güncelle
create or replace view public.plan_limits as
select 'free'    as plan, 3   as monthly_credits, 3 as max_scenes, false as hd_export
union all
select 'creator',          25, 5, false
union all
select 'pro',              55, 5, true;

-- ── Admin atama ───────────────────────────────────────────────────────────────
-- IMPORTANT: after the RLS fix above, admin RLS access is granted via the JWT's
-- app_metadata ONLY — updating public.profiles.role alone is NOT enough for
-- RLS purposes (it's still fine to keep profiles.role in sync for display in
-- the UI, but it doesn't grant any RLS bypass by itself).
--
-- To make a user an admin, run:
--   update auth.users
--   set raw_app_meta_data = raw_app_meta_data || '{"role":"admin"}'
--   where email = 'admin@example.com';
--
-- Optionally also mirror it into profiles for UI display:
--   update public.profiles set role = 'admin' where email = 'admin@example.com';

-- ── Stripe webhook'un güncelleyeceği yardımcı fonksiyon ──────────────────────
-- Backend'deki stripe.py bu fonksiyonu doğrudan çağırmak yerine Supabase
-- service key ile REST API üzerinden günceller; bu fonksiyon referans içindir.
create or replace function public.apply_subscription(
  p_user_id uuid,
  p_plan text,
  p_credits int,
  p_stripe_customer_id text default null,
  p_stripe_subscription_id text default null
)
returns void language plpgsql security definer as $$
begin
  update public.profiles
  set
    plan = p_plan,
    credits = credits + p_credits,
    stripe_customer_id = coalesce(p_stripe_customer_id, stripe_customer_id),
    stripe_subscription_id = coalesce(p_stripe_subscription_id, stripe_subscription_id)
  where id = p_user_id;
end;
$$;

-- ── Atomic credit deduction (prevents race conditions) ───────────────────────
-- Called by server/api.py:_deduct_credits via POST /rest/v1/rpc/deduct_credits
-- Returns the new credit balance on success, or -1 if insufficient credits.
create or replace function public.deduct_credits(p_user_id uuid, p_amount int)
returns int language plpgsql security definer as $$
declare
  v_new int;
begin
  update public.profiles
  set credits = credits - p_amount
  where id = p_user_id and credits >= p_amount
  returning credits into v_new;

  if v_new is null then
    return -1;  -- insufficient balance
  end if;

  return v_new;
end;
$$;

-- ── Stripe event idempotency table ───────────────────────────────────────────
-- Prevents duplicate credit allocation if Stripe retries the same webhook event.
create table if not exists public.processed_stripe_events (
  event_id    text primary key,
  processed_at timestamptz default now()
);

-- Only the service role needs to read/write this table
alter table public.processed_stripe_events enable row level security;

create policy "service_manage_stripe_events"
  on public.processed_stripe_events for all
  using (false)     -- no direct user access
  with check (false);

-- ── Optional background music + watermark bookkeeping ────────────────────────
-- music_enabled: whether this job paid for + attempted background music
-- (Creator/Pro only — enforced server-side in server/api.py).
-- plan: snapshot of the user's plan at generation time, so the watermark
-- decision (server/pipelines/idea2video.py: WATERMARK_PLANS) is reproducible
-- even if the user later upgrades/downgrades.
alter table public.jobs add column if not exists music_enabled boolean default false;
alter table public.jobs add column if not exists dialogue_enabled boolean default false;
alter table public.jobs add column if not exists plan text default 'free';

-- Creator's real scene cap is 3 (was 5 — "Priority render" and "3 team
-- seats" claims were removed since neither had a real enforcement mechanism;
-- this scene-count difference plus the Free-plan-only watermark are the real,
-- currently-enforced Creator/Pro differentiators).
create or replace view public.plan_limits as
select 'free'    as plan, 3   as monthly_credits, 3 as max_scenes, false as hd_export
union all
select 'creator',          25, 3, false
union all
select 'pro',              55, 5, true;

-- Raised scene caps: Free 5 / Creator 8 / Pro 10 (Kling v3 durations make
-- longer dramas practical; server/api.py PLAN_MAX_SCENES is the enforcer).
create or replace view public.plan_limits as
select 'free'    as plan, 3   as monthly_credits, 5 as max_scenes, false as hd_export
union all
select 'creator',          25, 8, false
union all
select 'pro',              55, 10, true;

-- Raised again for ~3 min Pro videos (avg ~7.5s/scene; non-finale ≤9s,
-- finale ≤15s). Free 8 / Creator 16 / Pro 24. server/api.py PLAN_MAX_SCENES
-- remains the real enforcer.
create or replace view public.plan_limits as
select 'free'    as plan, 3   as monthly_credits, 8 as max_scenes, false as hd_export
union all
select 'creator',          25, 16, false
union all
select 'pro',              55, 24, true;

-- ── Pro character library (reuse locked portraits across dramas) ─────────────
-- Pro-only at the API layer. Real cost: one portrait gen + durable storage.
create table if not exists public.character_library (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id),
  name text not null,
  static_features text not null,
  portrait_url text not null,
  created_at timestamptz not null default now()
);

alter table public.character_library enable row level security;

create policy "users manage own characters"
  on public.character_library
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

grant select, insert, update, delete on public.character_library to authenticated;
grant all on public.character_library to service_role;

-- ── Credit lots: every grant expires 30 days after it lands ──────────────────
-- profiles.credits was a single scalar, so it could not answer "when does THIS
-- credit die?" -- which made two things impossible: honouring a 30-day validity
-- per purchase, and telling a subscription renewal apart from a pack the user
-- paid for separately. The renewal path papered over that by RESETTING the
-- balance to the plan allowance, which silently destroyed purchased packs.
--
-- Each grant is now its own row with its own expiry. The balance is the sum of
-- what is left on lots that have not expired, so an expired credit stops being
-- spendable the moment it lapses -- even if the housekeeping job below never
-- runs. profiles.credits is kept in sync as a read cache for the UI and for
-- older code paths; credit_lots is the authority.
create table if not exists public.credit_lots (
  id          bigserial primary key,
  user_id     uuid references auth.users on delete cascade not null,
  amount      int not null,               -- granted
  remaining   int not null,               -- unspent
  reason      text not null default '',   -- 'credit_purchase' | 'subscription_renewal' | 'signup_grant' | 'migration'
  granted_at  timestamptz not null default now(),
  expires_at  timestamptz not null,
  constraint credit_lots_remaining_sane check (remaining >= 0 and remaining <= amount)
);

-- The hot path is "oldest-expiring live lot for this user", i.e. FIFO by expiry.
create index if not exists credit_lots_spendable_idx
  on public.credit_lots (user_id, expires_at)
  where remaining > 0;

alter table public.credit_lots enable row level security;

create policy "users_read_own_lots"
  on public.credit_lots for select using (auth.uid() = user_id);

grant select on public.credit_lots to authenticated;
grant all on public.credit_lots to service_role;

-- Default validity for a grant, used only when the caller passes no p_days.
-- It is the MONTHLY ALLOWANCE window: an allowance is rented for the month and
-- lapses with it, which is what stops it being hoarded across renewals.
-- Purchased packs and prepaid annual allowances are granted with an explicit
-- p_days of 365 (see server/stripe_integration.py) -- money already taken does
-- not get a 30-day fuse.
-- Changing this affects only NEW grants; lots already issued keep the expiry
-- they were sold with.
create or replace function public.credit_validity_days()
returns int language sql immutable as $$ select 30 $$;

-- Spendable balance: what is left on lots that have not lapsed.
create or replace function public.credit_balance(p_user_id uuid)
returns int language sql stable security definer as $$
  select coalesce(sum(remaining), 0)::int
  from public.credit_lots
  where user_id = p_user_id
    and remaining > 0
    and expires_at > now();
$$;

-- Keep the profiles.credits read cache honest after any lot movement.
create or replace function public.sync_credit_cache(p_user_id uuid)
returns int language plpgsql security definer as $$
declare
  v_balance int;
begin
  v_balance := public.credit_balance(p_user_id);
  update public.profiles set credits = v_balance where id = p_user_id;
  return v_balance;
end;
$$;

-- Grant credits. They are spendable immediately and die p_days later.
-- Returns the new spendable balance.
create or replace function public.grant_credits(
  p_user_id uuid,
  p_amount int,
  p_reason text default 'credit_purchase',
  p_days int default null
)
returns int language plpgsql security definer as $$
declare
  v_days int;
begin
  if p_amount is null or p_amount <= 0 then
    return public.credit_balance(p_user_id);
  end if;

  v_days := coalesce(p_days, public.credit_validity_days());

  insert into public.credit_lots (user_id, amount, remaining, reason, expires_at)
  values (p_user_id, p_amount, p_amount, p_reason, now() + make_interval(days => v_days));

  insert into public.credit_ledger (user_id, amount, reason)
  values (p_user_id, p_amount, p_reason);

  return public.sync_credit_cache(p_user_id);
end;
$$;

-- Atomic FIFO deduction across live lots, soonest-to-expire first, so a credit
-- about to lapse is spent before one with time left on it.
-- Returns the new balance, or -1 if the user cannot cover p_amount.
-- Replaces the single-UPDATE version above; server/api.py:_deduct_credits
-- calls this by the same name and signature.
create or replace function public.deduct_credits(p_user_id uuid, p_amount int)
returns int language plpgsql security definer as $$
declare
  v_lot record;
  v_left int := p_amount;
  v_take int;
  v_avail int;
begin
  if p_amount is null or p_amount <= 0 then
    return public.credit_balance(p_user_id);
  end if;

  -- Lock the user's live lots so two concurrent generations cannot both pass
  -- the balance check and overdraw. Locking is a separate statement because
  -- Postgres rejects FOR UPDATE alongside an aggregate.
  perform 1
  from public.credit_lots
  where user_id = p_user_id and remaining > 0 and expires_at > now()
  for update;

  select coalesce(sum(remaining), 0)::int into v_avail
  from public.credit_lots
  where user_id = p_user_id and remaining > 0 and expires_at > now();

  if v_avail < p_amount then
    return -1;
  end if;

  for v_lot in
    select id, remaining
    from public.credit_lots
    where user_id = p_user_id and remaining > 0 and expires_at > now()
    order by expires_at asc, id asc
  loop
    exit when v_left <= 0;
    v_take := least(v_lot.remaining, v_left);
    update public.credit_lots set remaining = remaining - v_take where id = v_lot.id;
    v_left := v_left - v_take;
  end loop;

  return public.sync_credit_cache(p_user_id);
end;
$$;

-- Housekeeping: write off lapsed lots and record the loss in the ledger, so a
-- user can see WHY their balance dropped. Purely cosmetic for correctness --
-- credit_balance() already ignores expired lots -- but without it the ledger
-- shows a balance falling with no matching entry.
-- Schedule hourly, e.g. via pg_cron:
--   select cron.schedule('expire-credits', '0 * * * *', 'select public.expire_credits()');
create or replace function public.expire_credits()
returns int language plpgsql security definer as $$
declare
  v_users uuid[];
  v_user uuid;
  v_lost int;
  v_total int := 0;
begin
  -- Snapshot the affected users into an array rather than looping over a
  -- cursor we then write to inside the loop.
  select coalesce(array_agg(distinct user_id), '{}')
  into v_users
  from public.credit_lots
  where remaining > 0 and expires_at <= now();

  foreach v_user in array v_users loop
    -- Read what this user is about to lose BEFORE zeroing, so the ledger
    -- entry carries the real amount.
    select coalesce(sum(remaining), 0)::int
    into v_lost
    from public.credit_lots
    where user_id = v_user and remaining > 0 and expires_at <= now();

    if v_lost > 0 then
      update public.credit_lots set remaining = 0
      where user_id = v_user and remaining > 0 and expires_at <= now();

      insert into public.credit_ledger (user_id, amount, reason)
      values (v_user, -v_lost, 'credit_expired');

      perform public.sync_credit_cache(v_user);
      v_total := v_total + v_lost;
    end if;
  end loop;

  return v_total;
end;
$$;

-- Revoke unspent SUBSCRIPTION credits (used when a subscription is cancelled).
-- Deliberately leaves 'credit_purchase' lots alone: a pack was bought outright
-- and is the user's property until it expires on its own schedule.
create or replace function public.revoke_subscription_credits(p_user_id uuid)
returns int language plpgsql security definer as $$
declare
  v_lost int;
begin
  select coalesce(sum(remaining), 0)::int into v_lost
  from public.credit_lots
  where user_id = p_user_id and remaining > 0 and reason = 'subscription_renewal';

  if v_lost > 0 then
    update public.credit_lots set remaining = 0
    where user_id = p_user_id and remaining > 0 and reason = 'subscription_renewal';

    insert into public.credit_ledger (user_id, amount, reason)
    values (p_user_id, -v_lost, 'subscription_cancelled');
  end if;

  return public.sync_credit_cache(p_user_id);
end;
$$;

-- Backfill: give every existing balance a lot so nobody's credits vanish when
-- the balance starts being read from credit_lots. Runs once -- the guard makes
-- re-running the migration a no-op.
insert into public.credit_lots (user_id, amount, remaining, reason, expires_at)
select p.id, p.credits, p.credits, 'migration',
       now() + make_interval(days => public.credit_validity_days())
from public.profiles p
where p.credits > 0
  and not exists (select 1 from public.credit_lots l where l.user_id = p.id);

-- plan_limits still advertised the retired 25/55 allowances; the real grants
-- are server/stripe_integration.py PLAN_CREDITS (16 / 36).
create or replace view public.plan_limits as
select 'free'    as plan, 3   as monthly_credits, 8 as max_scenes, false as hd_export
union all
select 'creator',          16, 16, false
union all
select 'pro',              36, 24, true;
