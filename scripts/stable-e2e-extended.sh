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

LOGIN=$(curl -fsS -X POST "$API/auth/login" --data-urlencode "username=$EMAIL" --data-urlencode "password=$PASSWORD")
TOKEN=$(printf '%s' "$LOGIN" | json_get access_token)
[[ -n "$TOKEN" ]]

enable_module() {
  local key="$1"
  request PUT "$API/admin/modules/$key?enabled=true" '' "$TOKEN" >/tmp/mz-module.json
  grep -q "\"key\":\"$key\"" /tmp/mz-module.json
}

BRANCHES=$(request GET "$API/admin/branches" '' "$TOKEN")
ORIGIN_BRANCH_ID=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])[0]["id"])' "$BRANCHES")

enable_module purchasing
DEST=$(request POST "$API/admin/branches" '{"code":"SPS-E2E","name":"San Pedro Sula E2E"}' "$TOKEN")
DEST_BRANCH_ID=$(printf '%s' "$DEST" | json_get id)
OPS_PRODUCT=$(request POST "$API/products" '{"sku":"E2E-OPS-001","name":"Producto operativo E2E","category":"Mily Basics","unit_cost":"100.00","sale_price":"249.00"}' "$TOKEN")
OPS_PRODUCT_ID=$(printf '%s' "$OPS_PRODUCT" | json_get id)
SUPPLIER=$(request POST "$API/ops/suppliers" '{"name":"Proveedor E2E","phone":"+50400000000"}' "$TOKEN")
SUPPLIER_ID=$(printf '%s' "$SUPPLIER" | json_get id)
PURCHASE=$(request POST "$API/ops/purchases" "{\"supplier_id\":\"$SUPPLIER_ID\",\"branch_id\":\"$ORIGIN_BRANCH_ID\",\"lines\":[{\"product_id\":\"$OPS_PRODUCT_ID\",\"quantity\":\"10\",\"unit_cost\":\"100.00\"}]}" "$TOKEN")
PURCHASE_ID=$(printf '%s' "$PURCHASE" | json_get id)
RECEIVED=$(request POST "$API/ops/purchases/$PURCHASE_ID/receive" '' "$TOKEN")
printf '%s' "$RECEIVED" | grep -q '"status":"received"'
TRANSFER=$(request POST "$API/ops/transfers" "{\"from_branch_id\":\"$ORIGIN_BRANCH_ID\",\"to_branch_id\":\"$DEST_BRANCH_ID\",\"lines\":[{\"product_id\":\"$OPS_PRODUCT_ID\",\"quantity\":\"3\"}]}" "$TOKEN")
TRANSFER_ID=$(printf '%s' "$TRANSFER" | json_get id)
request POST "$API/ops/transfers/$TRANSFER_ID/ship" '' "$TOKEN" | grep -q '"status":"shipped"'
request POST "$API/ops/transfers/$TRANSFER_ID/receive" '' "$TOKEN" | grep -q '"status":"received"'
OPS_STOCK=$(request GET "$API/inventory" '' "$TOKEN")
python3 -c 'import json,sys; rows=json.loads(sys.argv[1]); pid,origin,dest=sys.argv[2:5]; b={r["branch_id"]:r["quantity"] for r in rows if r["product_id"]==pid}; assert b[origin]=="7.000",b; assert b[dest]=="3.000",b' "$OPS_STOCK" "$OPS_PRODUCT_ID" "$ORIGIN_BRANCH_ID" "$DEST_BRANCH_ID"

enable_module delivery
DRIVER=$(request POST "$API/ops/users" "{\"email\":\"driver.e2e@milyzebra.test\",\"full_name\":\"Driver E2E\",\"password\":\"driver-secure-password\",\"role\":\"driver\",\"branch_id\":\"$ORIGIN_BRANCH_ID\"}" "$TOKEN")
DRIVER_ID=$(printf '%s' "$DRIVER" | json_get id)
CUSTOMER=$(request POST "$API/ops/customers" '{"full_name":"Cliente Roatán E2E","phone":"+50411111111"}' "$TOKEN")
CUSTOMER_ID=$(printf '%s' "$CUSTOMER" | json_get id)
DELIVERY=$(request POST "$API/ops/deliveries" "{\"branch_id\":\"$ORIGIN_BRANCH_ID\",\"customer_id\":\"$CUSTOMER_ID\",\"driver_user_id\":\"$DRIVER_ID\",\"address_text\":\"West End, Roatán\"}" "$TOKEN")
DELIVERY_ID=$(printf '%s' "$DELIVERY" | json_get id)
printf '%s' "$DELIVERY" | grep -q '"status":"assigned"'
DRIVER_LOGIN=$(curl -fsS -X POST "$API/auth/login" --data-urlencode 'username=driver.e2e@milyzebra.test' --data-urlencode 'password=driver-secure-password')
DRIVER_TOKEN=$(printf '%s' "$DRIVER_LOGIN" | json_get access_token)
ASSIGNED=$(request GET "$API/ops/deliveries" '' "$DRIVER_TOKEN")
python3 -c 'import json,sys; rows=json.loads(sys.argv[1]); did=sys.argv[2]; assert any(r["id"]==did for r in rows), rows' "$ASSIGNED" "$DELIVERY_ID"
OUT_FOR_DELIVERY=$(request POST "$API/ops/deliveries/$DELIVERY_ID/status" '{"status":"out_for_delivery","proof_note":null}' "$DRIVER_TOKEN")
printf '%s' "$OUT_FOR_DELIVERY" | grep -q '"status":"out_for_delivery"'
DELIVERED=$(request POST "$API/ops/deliveries/$DELIVERY_ID/status" '{"status":"delivered","proof_note":"Entregado conforme en Stable Gate."}' "$DRIVER_TOKEN")
printf '%s' "$DELIVERED" | grep -q '"status":"delivered"'

DEVICE=$(request POST "$API/admin/devices/enroll" "{\"branch_id\":\"$ORIGIN_BRANCH_ID\",\"device_id\":\"POS-E2E-01\",\"name\":\"Caja E2E\"}" "$TOKEN")
DEVICE_TOKEN=$(printf '%s' "$DEVICE" | json_get token)
PRINT_JOB=$(request POST "$API/print-jobs" "{\"branch_id\":\"$ORIGIN_BRANCH_ID\",\"device_id\":\"POS-E2E-01\",\"job_type\":\"receipt\",\"payload\":\"{\\\"text\\\":\\\"Mily Zebra Stable E2E\\\"}\"}" "$TOKEN")
PRINT_JOB_ID=$(printf '%s' "$PRINT_JOB" | json_get id)
INVALID_DEVICE_CODE=$(curl -sS -o /tmp/mz-device-invalid.json -w '%{http_code}' -X POST "$API/device/print-jobs/claim" -H 'X-Device-ID: POS-E2E-01' -H 'X-Device-Token: wrong')
[[ "$INVALID_DEVICE_CODE" == '401' ]]
FOUND_TARGET=0
for _ in $(seq 1 10); do
  CLAIMED=$(curl -fsS -X POST "$API/device/print-jobs/claim" -H 'X-Device-ID: POS-E2E-01' -H "X-Device-Token: $DEVICE_TOKEN")
  [[ "$CLAIMED" == "null" ]] && break
  CLAIMED_ID=$(printf '%s' "$CLAIMED" | json_get id)
  COMPLETED=$(curl -fsS -X POST "$API/device/print-jobs/$CLAIMED_ID/complete?success=true" -H 'X-Device-ID: POS-E2E-01' -H "X-Device-Token: $DEVICE_TOKEN")
  printf '%s' "$COMPLETED" | grep -q '"status":"completed"'
  if [[ "$CLAIMED_ID" == "$PRINT_JOB_ID" ]]; then FOUND_TARGET=1; break; fi
done
[[ "$FOUND_TARGET" == '1' ]]

WEB_PRODUCT=$(request POST "$API/products" '{"sku":"E2E-WEB-001","name":"Blusa Island Web E2E","category":"Island Mood","unit_cost":"200.00","sale_price":"499.00"}' "$TOKEN")
WEB_PRODUCT_ID=$(printf '%s' "$WEB_PRODUCT" | json_get id)
request POST "$API/inventory/movements" "{\"product_id\":\"$WEB_PRODUCT_ID\",\"quantity_delta\":\"4\",\"reason\":\"opening_stock\"}" "$TOKEN" >/dev/null
CATALOG=$(request GET "$API/store/mily-zebra/catalog")
python3 -c 'import json,sys; c=json.loads(sys.argv[1]); pid=sys.argv[2]; assert any(p["id"]==pid for p in c["products"]), c' "$CATALOG" "$WEB_PRODUCT_ID"
CHECKOUT_BODY="{\"full_name\":\"Cliente Web E2E\",\"email\":\"cliente.e2e@example.com\",\"phone\":\"+50422222222\",\"payment_method\":\"manual_transfer\",\"fulfillment_method\":\"pickup\",\"lines\":[{\"product_id\":\"$WEB_PRODUCT_ID\",\"quantity\":\"2\"}]}"
ORDER=$(request POST "$API/store/mily-zebra/checkout" "$CHECKOUT_BODY" '' 'stable-web-order-0001')
ORDER_ID=$(printf '%s' "$ORDER" | json_get id)
TRACKING_TOKEN=$(printf '%s' "$ORDER" | json_get tracking_token)
printf '%s' "$ORDER" | grep -q '"status":"pending_payment"'
printf '%s' "$ORDER" | grep -q '"total":"998.00"'
ORDER_REPEAT=$(request POST "$API/store/mily-zebra/checkout" "$CHECKOUT_BODY" '' 'stable-web-order-0001')
[[ "$(printf '%s' "$ORDER_REPEAT" | json_get id)" == "$ORDER_ID" ]]
BLOCK_CODE=$(curl -sS -o /tmp/mz-blocked-order.json -w '%{http_code}' -X POST "$API/store/mily-zebra/checkout" -H 'Content-Type: application/json' -H 'Idempotency-Key: stable-web-order-0002' --data "{\"full_name\":\"Otra Cliente\",\"payment_method\":\"cash_on_delivery\",\"lines\":[{\"product_id\":\"$WEB_PRODUCT_ID\",\"quantity\":\"3\"}]}")
[[ "$BLOCK_CODE" == '409' ]]
TRACKED=$(request GET "$API/store/mily-zebra/orders/$ORDER_ID/track?token=$TRACKING_TOKEN")
printf '%s' "$TRACKED" | grep -q '"status":"pending_payment"'
PAID=$(request POST "$API/commerce/orders/$ORDER_ID/mark-paid" '{"external_reference":"BANK-STABLE-001"}' "$TOKEN")
printf '%s' "$PAID" | grep -q '"status":"confirmed"'
FULFILLED=$(request POST "$API/commerce/orders/$ORDER_ID/fulfill" '' "$TOKEN")
printf '%s' "$FULFILLED" | grep -q '"status":"fulfilled"'
WEB_STOCK=$(request GET "$API/inventory" '' "$TOKEN")
python3 -c 'import json,sys; rows=json.loads(sys.argv[1]); pid=sys.argv[2]; row=next(r for r in rows if r["product_id"]==pid); assert row["quantity"]=="2.000",row' "$WEB_STOCK" "$WEB_PRODUCT_ID"

enable_module accounting
enable_module receivables
enable_module banking
enable_module payables
CREDIT_CUSTOMER=$(request POST "$API/ops/customers" '{"full_name":"Cliente Crédito E2E","email":"credito.e2e@example.com"}' "$TOKEN")
CREDIT_CUSTOMER_ID=$(printf '%s' "$CREDIT_CUSTOMER" | json_get id)
CREDIT_SUPPLIER=$(request POST "$API/ops/suppliers" '{"name":"Proveedor Crédito E2E"}' "$TOKEN")
CREDIT_SUPPLIER_ID=$(printf '%s' "$CREDIT_SUPPLIER" | json_get id)
REC=$(request POST "$API/finance/receivables" "{\"party_id\":\"$CREDIT_CUSTOMER_ID\",\"reference\":\"CXC-E2E-001\",\"amount\":\"500.00\"}" "$TOKEN")
REC_ID=$(printf '%s' "$REC" | json_get id)
REC_PAY=$(request POST "$API/finance/receivables/$REC_ID/payments" '{"amount":"200.00","method":"cash"}' "$TOKEN")
printf '%s' "$REC_PAY" | grep -q '"balance":"300.00"'
printf '%s' "$REC_PAY" | grep -q '"status":"partial"'
PAY=$(request POST "$API/finance/payables" "{\"party_id\":\"$CREDIT_SUPPLIER_ID\",\"reference\":\"CXP-E2E-001\",\"amount\":\"800.00\"}" "$TOKEN")
PAY_ID=$(printf '%s' "$PAY" | json_get id)
PAY_DONE=$(request POST "$API/finance/payables/$PAY_ID/payments" '{"amount":"800.00","method":"transfer","reference":"BANK-E2E-001"}' "$TOKEN")
printf '%s' "$PAY_DONE" | grep -q '"balance":"0.00"'
printf '%s' "$PAY_DONE" | grep -q '"status":"paid"'
BANK=$(request POST "$API/finance/banking/accounts" '{"name":"Cuenta principal E2E","bank_name":"Banco E2E","currency":"HNL","account_last4":"1234"}' "$TOKEN")
BANK_ID=$(printf '%s' "$BANK" | json_get id)
BANK_TX=$(request POST "$API/finance/banking/accounts/$BANK_ID/transactions" '{"transaction_date":"2026-08-18","description":"Depósito E2E","amount":"200.00","external_reference":"MOV-E2E-001"}' "$TOKEN")
printf '%s' "$BANK_TX" | grep -q '"reconciliation_status":"unmatched"'
DUP_CODE=$(curl -sS -o /tmp/mz-bank-dup.json -w '%{http_code}' -X POST "$API/finance/banking/accounts/$BANK_ID/transactions" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' --data '{"transaction_date":"2026-08-18","description":"Duplicado","amount":"200.00","external_reference":"MOV-E2E-001"}')
[[ "$DUP_CODE" == '409' ]]

# Postventa real: lookup de línea retornable, reembolso cash, ledger e idempotencia.
RETURN_CASH=$(request POST "$API/cash/open" '{"opening_amount":"500.00"}' "$TOKEN")
RETURN_CASH_ID=$(printf '%s' "$RETURN_CASH" | json_get id)
RECENT_SALES=$(request GET "$API/post-sales/sales?limit=100" '' "$TOKEN")
RETURN_SALE_ID=$(python3 -c 'import json,sys; rows=json.loads(sys.argv[1]); sale=next(r for r in rows if r["payment_method"]=="cash" and r["total"]=="249.00"); print(sale["id"])' "$RECENT_SALES")
RETURN_DETAIL=$(request GET "$API/post-sales/sales/$RETURN_SALE_ID" '' "$TOKEN")
RETURN_LINE_ID=$(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(d["lines"][0]["sale_line_id"])' "$RETURN_DETAIL")
RETURN_PRODUCT_ID=$(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(d["lines"][0]["product_id"])' "$RETURN_DETAIL")
RETURN_BODY="{\"sale_id\":\"$RETURN_SALE_ID\",\"reason\":\"Stable Gate devolución\",\"lines\":[{\"sale_line_id\":\"$RETURN_LINE_ID\",\"quantity\":\"1\"}]}"
RETURN1=$(request POST "$API/post-sales/returns" "$RETURN_BODY" "$TOKEN" 'stable-return-0001')
RETURN_ID=$(printf '%s' "$RETURN1" | json_get id)
printf '%s' "$RETURN1" | grep -q '"total":"249.00"'
printf '%s' "$RETURN1" | grep -q '"status":"completed"'
RETURN2=$(request POST "$API/post-sales/returns" "$RETURN_BODY" "$TOKEN" 'stable-return-0001')
[[ "$(printf '%s' "$RETURN2" | json_get id)" == "$RETURN_ID" ]]
RETURN_SUMMARY=$(request GET "$API/cash/$RETURN_CASH_ID/summary" '' "$TOKEN")
python3 -c 'import json,sys; s=json.loads(sys.argv[1]); assert s["expected_amount"]=="251.00",s; refunds=[m for m in s["movements"] if m.get("reference_type")=="refund"]; assert len(refunds)==1,refunds; assert refunds[0]["amount"]=="-249.00",refunds' "$RETURN_SUMMARY"
RETURN_STOCK=$(request GET "$API/inventory" '' "$TOKEN")
python3 -c 'import json,sys; rows=json.loads(sys.argv[1]); pid=sys.argv[2]; row=next(r for r in rows if r["product_id"]==pid); assert row["quantity"]=="5.000",row' "$RETURN_STOCK" "$RETURN_PRODUCT_ID"
request POST "$API/cash/$RETURN_CASH_ID/close" '{"closing_amount":"251.00"}' "$TOKEN" | grep -q '"difference":"0.00"'

if docker compose logs --no-color worker 2>&1 | grep -q 'UndefinedTable'; then
  echo 'Worker arrancó antes de que Alembic terminara' >&2
  exit 1
fi

echo 'STABLE_EXTENDED_E2E=PASS'
