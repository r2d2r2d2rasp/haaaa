-- Categoria inesistente: severità di default (2), così fallisce la FK (23503 → 422 in API) e non il NOT NULL.
create or replace function reports_before_insert() returns trigger language plpgsql as $$
begin
  select z.cap into new.cap from cap_zones z where st_covers(z.geom, new.geom) limit 1;
  new.severity := coalesce((select default_severity from report_categories where slug = new.category), 2);
  return new;
end $$;
