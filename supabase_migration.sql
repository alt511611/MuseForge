-- MuseForge Supabase Migration
-- Bu dosyayı Supabase Dashboard → SQL Editor'de çalıştırın.
-- Mevcut SQLite jobs tablosunu kaldırıp Supabase'e taşıyın.

-- ── Kullanıcı profilleri tablosu ──────────────────────────────────────────────
create table if not exists public.profiles (
  id          uuid references auth.users on delete cascade primary key,
  email       text,
  role        text not null default 'user',   -- 'user' | 'admin'
  created_at  timestamptz default now()
);

-- Auth trigger: her yeni kullanıcı için otomatik profil oluştur
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

-- ── Jobs tablosu ──────────────────────────────────────────────────────────────
-- NOT: Mevcut sistem jobs'ları bellekte tutuyor (jobs.py).
-- İleride kalıcı hale getirmek için bu tabloyu kullanın.
create table if not exists public.jobs (
  id              text primary key,
  user_id         uuid references auth.users on delete set null,
  user_email      text,
  idea            text,
  style           text default 'Cinematic',
  director_style  text default 'cinematic_balanced',
  aspect_ratio    text default '16:9',
  num_scenes      int  default 3,
  user_requirement text default '',
  demo            boolean default false,
  status          text default 'queued',
  result          jsonb,
  error           text,
  created_at      timestamptz default now(),
  updated_at      timestamptz default now()
);

-- Row Level Security
alter table public.profiles enable row level security;
alter table public.jobs     enable row level security;

-- Kullanıcılar kendi profillerini okuyabilir
create policy "users_read_own_profile"
  on public.profiles for select
  using (auth.uid() = id);

-- Kullanıcılar kendi job'larını okuyabilir
create policy "users_read_own_jobs"
  on public.jobs for select
  using (auth.uid() = user_id);

-- Adminler her şeyi görebilir (role = 'admin' check via profiles)
create policy "admins_read_all_jobs"
  on public.jobs for all
  using (
    exists (
      select 1 from public.profiles
      where id = auth.uid() and role = 'admin'
    )
  );

-- ── Admin kullanıcısı atama (email ile) ──────────────────────────────────────
-- Bir kullanıcıyı admin yapmak için:
-- update public.profiles set role = 'admin' where email = 'admin@example.com';
--
-- Supabase app_metadata ile de yapılabilir (JWT'de taşınır, daha güvenli):
-- update auth.users set raw_app_meta_data = raw_app_meta_data || '{"role":"admin"}'
-- where email = 'admin@example.com';
