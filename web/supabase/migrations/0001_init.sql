-- TorinoSegnala: schema iniziale
create extension if not exists postgis;
create extension if not exists pgcrypto;

-- ───────── Categorie ─────────
create table report_categories (
  slug text primary key,
  name text not null,
  icon text not null default '📍',
  default_severity int not null default 2 check (default_severity between 1 and 5)
);

insert into report_categories (slug, name, icon, default_severity) values
  ('rifiuti_abbandonati', 'Rifiuti abbandonati', '🗑️', 4),
  ('cassonetto_pieno',    'Cassonetto pieno',    '♻️', 3),
  ('buca',                'Buca stradale',       '🕳️', 4),
  ('graffiti',            'Graffiti / vandalismo','🎨', 1),
  ('illuminazione',       'Illuminazione guasta','💡', 3),
  ('altro',               'Altro',               '📍', 2);

-- ───────── Dispositivi POD e chiavi API ─────────
create table devices (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  type text not null check (type in ('fixed', 'mobile')),
  label text,                       -- es. "Semaforo Via Roma/Via Po", "Bus 15"
  fixed_geom geography(Point, 4326),-- posizione nota per i POD fissi
  last_geom geography(Point, 4326),
  battery numeric,
  firmware text,
  last_seen_at timestamptz,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table api_keys (
  id uuid primary key default gen_random_uuid(),
  device_id uuid not null references devices(id) on delete cascade,
  key_prefix text not null,         -- primi caratteri, per riconoscerla in dashboard
  key_hash text not null unique,    -- SHA-256 esadecimale: la chiave in chiaro NON è salvata
  created_at timestamptz not null default now(),
  last_used_at timestamptz,
  revoked_at timestamptz
);

create table device_heartbeats (
  id bigserial primary key,
  device_id uuid not null references devices(id) on delete cascade,
  geom geography(Point, 4326),
  battery numeric,
  ts timestamptz not null default now()
);
create index on device_heartbeats (device_id, ts desc);

-- ───────── Zone CAP ─────────
create table cap_zones (
  cap text primary key,
  name text,
  geom geography(MultiPolygon, 4326) not null
);
create index on cap_zones using gist (geom);

-- ───────── Segnalazioni ─────────
create table reports (
  id uuid primary key default gen_random_uuid(),
  source text not null check (source in ('citizen', 'device')),
  device_id uuid references devices(id) on delete set null,
  category text not null references report_categories(slug),
  description text,
  geom geography(Point, 4326) not null,
  cap text,
  photo_url text,
  confidence numeric not null default 1 check (confidence between 0 and 1),
  severity int not null default 2,
  status text not null default 'open' check (status in ('open', 'in_progress', 'resolved', 'rejected')),
  dedupe_group uuid,
  observations int not null default 1,
  metadata jsonb not null default '{}'::jsonb,
  captured_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);
create index on reports using gist (geom);
create index on reports (status, created_at desc);
create index on reports (category);
create index on reports (cap);

-- Assegna CAP e severità di default; aggiorna resolved_at
create or replace function reports_before_insert() returns trigger language plpgsql as $$
begin
  select z.cap into new.cap from cap_zones z where st_covers(z.geom, new.geom) limit 1;
  new.severity := coalesce((select default_severity from report_categories where slug = new.category), 2);
  return new;
end $$;
create trigger trg_reports_before_insert before insert on reports
  for each row execute function reports_before_insert();

create or replace function reports_before_update() returns trigger language plpgsql as $$
begin
  if new.status = 'resolved' and old.status <> 'resolved' then new.resolved_at = now(); end if;
  return new;
end $$;
create trigger trg_reports_before_update before update on reports
  for each row execute function reports_before_update();

-- Inserimento con deduplica: stessa categoria entro 25 m e 24 h → stesso gruppo.
-- Il report esistente aumenta observations e confidence (noisy-OR).
create or replace function ingest_report(
  p_source text, p_device_id uuid, p_category text, p_lat double precision, p_lon double precision,
  p_description text, p_photo_url text, p_confidence numeric, p_captured_at timestamptz, p_metadata jsonb
) returns table (id uuid, deduped boolean) language plpgsql as $$
declare
  pt geography := st_setsrid(st_makepoint(p_lon, p_lat), 4326)::geography;
  existing reports%rowtype;
begin
  select r.* into existing from reports r
   where r.category = p_category and r.status in ('open', 'in_progress')
     and r.created_at > now() - interval '24 hours'
     and st_dwithin(r.geom, pt, 25)
   order by st_distance(r.geom, pt) limit 1;

  if found then
    update reports set
      observations = observations + 1,
      confidence = 1 - (1 - reports.confidence) * (1 - p_confidence),
      dedupe_group = coalesce(reports.dedupe_group, reports.id),
      photo_url = coalesce(reports.photo_url, p_photo_url)
    where reports.id = existing.id;
    return query select existing.id, true;
  end if;

  return query
    insert into reports (source, device_id, category, description, geom, photo_url, confidence, captured_at, metadata)
    values (p_source, p_device_id, p_category, p_description, pt, p_photo_url, p_confidence, p_captured_at, coalesce(p_metadata, '{}'))
    returning reports.id, false;
end $$;

-- ───────── Statistiche per la dashboard ─────────
create or replace view v_stats_by_cap as
  select coalesce(cap, 'N/D') as cap, count(*) as total,
         count(*) filter (where status in ('open','in_progress')) as open_count
  from reports group by 1;

create or replace view v_stats_by_category as
  select c.slug, c.name, c.icon, count(r.id) as total
  from report_categories c left join reports r on r.category = c.slug
  group by c.slug, c.name, c.icon;

create or replace view v_stats_by_day as
  select date_trunc('day', created_at)::date as day, count(*) as total
  from reports group by 1 order by 1;

-- ───────── Sicurezza (RLS) ─────────
-- Le scritture dei POD passano da route handler con service role (che bypassa RLS).
-- Il pubblico può SOLO leggere segnalazioni e categorie.
alter table reports enable row level security;
alter table report_categories enable row level security;
alter table devices enable row level security;
alter table api_keys enable row level security;
alter table device_heartbeats enable row level security;
alter table cap_zones enable row level security;

create policy "public read reports" on reports for select using (true);
create policy "public read categories" on report_categories for select using (true);
create policy "public read cap zones" on cap_zones for select using (true);
-- devices/api_keys/heartbeats: nessuna policy → accessibili solo con service role.

-- Vista pubblica dei POD senza dati sensibili
create or replace view v_public_devices with (security_invoker = false) as
  select id, name, type, label, st_y(last_geom::geometry) as lat, st_x(last_geom::geometry) as lon,
         battery, last_seen_at, active
  from devices;
grant select on v_public_devices to anon, authenticated;

-- Realtime sulle nuove segnalazioni
alter publication supabase_realtime add table reports;

-- Bucket pubblico per le foto delle segnalazioni (scrittura solo via service role)
insert into storage.buckets (id, name, public) values ('report-photos', 'report-photos', true)
on conflict (id) do nothing;
