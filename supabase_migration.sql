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
