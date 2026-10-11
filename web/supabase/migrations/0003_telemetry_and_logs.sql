-- Telemetria ambientale dai POD + registro delle chiamate API (console IT)

-- Misure dei sensori (CO2, temperatura, umidità, PM, rumore, …): metriche libere in jsonb
create table if not exists device_readings (
  id bigserial primary key,
  device_id uuid not null references devices(id) on delete cascade,
  ts timestamptz not null default now(),
  geom geography(Point, 4326),
  metrics jsonb not null
);
create index if not exists device_readings_device_ts on device_readings (device_id, ts desc);
create index if not exists device_readings_ts on device_readings (ts desc);

-- Ogni richiesta dei POD (anche fallita): cosa ha inviato, esito, da dove
create table if not exists api_request_log (
  id bigserial primary key,
  device_id uuid references devices(id) on delete set null,
  key_prefix text,
  endpoint text not null,
  status int not null,
  ip text,
  body jsonb,
  ts timestamptz not null default now()
);
create index if not exists api_request_log_ts on api_request_log (ts desc);
create index if not exists api_request_log_device_ts on api_request_log (device_id, ts desc);

-- Etichetta per riconoscere le chiavi (es. "Team POD - test")
alter table api_keys add column if not exists label text;

-- Solo service role (nessuna policy pubblica)
alter table device_readings enable row level security;
alter table api_request_log enable row level security;

-- Include la correzione di 0002 (severità di default se la categoria non esiste)
create or replace function reports_before_insert() returns trigger language plpgsql as $$
begin
  select z.cap into new.cap from cap_zones z where st_covers(z.geom, new.geom) limit 1;
  new.severity := coalesce((select default_severity from report_categories where slug = new.category), 2);
  return new;
end $$;
