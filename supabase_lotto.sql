-- ============================================================
--  로또 분석기 · 클라우드 동기화 테이블
--  Supabase 대시보드 → SQL Editor 에 전체 붙여넣고 [Run] 한 번만 실행하세요.
-- ============================================================

-- 1) 테이블 -----------------------------------------------------
create table if not exists public.lotto_records (
  owner       text        not null,                       -- 내 동기화 키 (앱이 자동 생성)
  round       integer     not null,                       -- 회차
  date        text,                                       -- 저장/추첨일
  games       jsonb       not null default '[]'::jsonb,   -- 내가 산 줄들
  win_numbers jsonb,                                      -- 당첨번호 6개
  bonus       integer,                                    -- 보너스
  matches     jsonb,                                      -- 매칭 결과
  extra       jsonb,                                      -- 백테스트/기록전용 플래그 등
  updated_at  timestamptz not null default now(),
  primary key (owner, round)
);

create index if not exists lotto_records_owner_idx on public.lotto_records (owner);

-- 2) RLS 켜기 ---------------------------------------------------
alter table public.lotto_records enable row level security;

-- 3) 요청 헤더에서 '내 동기화 키'를 꺼내는 함수 ------------------
--    anon key 는 공개돼도 됩니다. 이 키(x-owner-key)를 모르면
--    어떤 행도 읽거나 쓸 수 없습니다.
create or replace function public.lotto_owner_key()
returns text
language sql
stable
as $$
  select nullif(current_setting('request.headers', true)::json ->> 'x-owner-key', '')
$$;

-- 4) 정책: 내 키와 일치하는 행만 --------------------------------
drop policy if exists lotto_own_select on public.lotto_records;
drop policy if exists lotto_own_insert on public.lotto_records;
drop policy if exists lotto_own_update on public.lotto_records;
drop policy if exists lotto_own_delete on public.lotto_records;

create policy lotto_own_select on public.lotto_records
  for select to anon, authenticated
  using (owner = public.lotto_owner_key());

create policy lotto_own_insert on public.lotto_records
  for insert to anon, authenticated
  with check (owner = public.lotto_owner_key() and length(owner) >= 24);

create policy lotto_own_update on public.lotto_records
  for update to anon, authenticated
  using (owner = public.lotto_owner_key())
  with check (owner = public.lotto_owner_key());

create policy lotto_own_delete on public.lotto_records
  for delete to anon, authenticated
  using (owner = public.lotto_owner_key());

-- 5) updated_at 자동 갱신 ---------------------------------------
create or replace function public.lotto_touch()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists lotto_records_touch on public.lotto_records;
create trigger lotto_records_touch
  before insert or update on public.lotto_records
  for each row execute function public.lotto_touch();

-- ============================================================
--  확인:  select count(*) from public.lotto_records;
--  → RLS 때문에 SQL Editor(서비스 롤)에서는 전체가 보이고,
--    앱(anon)에서는 내 키와 일치하는 행만 보입니다.
-- ============================================================
