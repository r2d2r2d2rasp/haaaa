#!/usr/bin/env bash
# Carica su Vercel (production) le variabili di .env.local, senza stamparle.
# Rilanciabile: sovrascrive i valori esistenti.
# Uso, dalla cartella web/ dopo `vercel link`:  bash scripts/vercel-env.sh
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env.local ] || { echo "Manca web/.env.local"; exit 1; }

for name in NEXT_PUBLIC_SUPABASE_URL NEXT_PUBLIC_SUPABASE_ANON_KEY SUPABASE_SERVICE_ROLE_KEY ADMIN_PASSWORD; do
  value="$(grep -E "^${name}=" .env.local | head -1 | cut -d= -f2-)"
  if [ -z "$value" ]; then echo "⚠️  $name vuota in .env.local, saltata"; continue; fi
  if out="$(printf '%s' "$value" | vercel env add "$name" production --force 2>&1)"; then
    echo "✓ $name"
  else
    echo "✗ $name"; echo "$out" | grep -vF "$value" | tail -5
  fi
done
