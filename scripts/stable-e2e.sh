#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${MZ_E2E_BASE_URL:-http://127.0.0.1}"
API="${BASE_URL%/}/api"
EMAIL="${MZ_E2E_EMAIL:-owner.e2e@milyzebra.test}"
PASSWORD="${MZ_E2E_PASSWORD:-StableE2E-2026!}"

json_get() {
  python3 -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"
}

request() {
  local method="$1" url="$2" body="${3:-}" token="${4:-}" idem="${5:-}"
  local args=(-fsS -X "$method" "$url" -H 'Accept: application/json')
  [[ -n "$body" ]] && args+=(-H 'Content-Type: application/json' --data "$body")
  [[ -n "$token" ]] && args+=(-H "Authorization: Bearer $token")
  [[ -n "$idem" ]] && args+=(-H "Idempotency-Key: $idem")
  curl "${args[@]}"
}

for i in $(seq 1 90); do
  if curl -fsS "$API/health" >/tmp/mz-health.json 2>/dev/null; then break; fi
  if [[ "$i" -eq 90 ]]; then echo 'API no respondió al health check' >&2; exit 1; fi
  sleep 2
done
grep -q '"status":"ok"' /tmp/mz-health.json

BOOTSTRAP=$(request POST "$API/bootstrap" "{\"store_name\":\"Mily Zebra E2E\",\"branch_name\":\"Roatán E2E\",\"email\":\"$EMAIL\",\"full_name\":\"Propietario E2E\",\"password\":\"$PASSWORD\"}")
TOKEN=$(printf '%s' "$BOOTSTRAP" | json_get access_token)
[[ -n "$TOKEN" ]]

ME=$(request GET "$API/me" '' "$TOKEN")
printf '%s' "$ME" | grep -q '"role":"owner"'

PRODUCT=$(request POST "$API/products" '{"sku":"E2E-001","barcode":"750000000001","name":"Blusa E2E","description":"Producto de prueba estable","category":"Mily Basics","size":"M","color":"Rosa","unit_cost":"100.00","sale_price":"249.00"}' "$TOKEN")
PRODUCT_ID=$(printf '%s' "$PRODUCT" | json_get id)
[[ -n "$PRODUCT_ID" ]]

request POST "$API/inventory/movements" "{\"product_id\":\"$PRODUCT_ID\",\"quantity_delta\":\"5\",\"reason\":\"stable_e2e_seed\"}" "$TOKEN" >/tmp/mz-stock-seed.json
grep -q '"quantity":"5.000"' /tmp/mz-stock-seed.json

CASH=$(request POST "$API/cash/open" '{"opening_amount":"100.00"}' "$TOKEN")
CASH_ID=$(printf '%s' "$CASH" | json_get id)
[[ -n "$CASH_ID" ]]

SALE_KEY="stable-e2e-sale-0001"
SALE_BODY="{\"payment_method\":\"cash\",\"lines\":[{\"product_id\":\"$PRODUCT_ID\",\"quantity\":\"1\"}]}"
SALE1=$(request POST "$API/sales" "$SALE_BODY" "$TOKEN" "$SALE_KEY")
SALE1_ID=$(printf '%s' "$SALE1" | json_get id)
[[ -n "$SALE1_ID" ]]
printf '%s' "$SALE1" | grep -q '"total":"249.00"'

SALE2=$(request POST "$API/sales" "$SALE_BODY" "$TOKEN" "$SALE_KEY")
SALE2_ID=$(printf '%s' "$SALE2" | json_get id)
[[ "$SALE1_ID" == "$SALE2_ID" ]]

INVENTORY=$(request GET "$API/inventory" '' "$TOKEN")
python3 -c 'import json,sys; rows=json.loads(sys.argv[1]); pid=sys.argv[2]; row=next(r for r in rows if r["product_id"]==pid); assert row["quantity"]=="4.000", row' "$INVENTORY" "$PRODUCT_ID"

SUMMARY=$(request GET "$API/cash/$CASH_ID/summary" '' "$TOKEN")
python3 -c 'import json,sys; s=json.loads(sys.argv[1]); assert s["expected_amount"]=="349.00", s; assert sum(1 for m in s["movements"] if m.get("reference_type")=="sale")==1, s' "$SUMMARY"

request POST "$API/cash/$CASH_ID/close" '{"closing_amount":"349.00"}' "$TOKEN" >/tmp/mz-cash-close.json
grep -q '"difference":"0.00"' /tmp/mz-cash-close.json

curl -fsS "$BASE_URL/" >/tmp/mz-storefront.html
grep -q '<div id="root"></div>' /tmp/mz-storefront.html
curl -fsS "$BASE_URL/admin" >/tmp/mz-admin.html
grep -q '<div id="root"></div>' /tmp/mz-admin.html

echo 'STABLE_E2E=PASS'
echo "SALE_ID=$SALE1_ID"
echo "PRODUCT_ID=$PRODUCT_ID"
