#!/usr/bin/env bash
# ==============================================================================
# Manage self-managed mutual TLS (mTLS) client certificates for OpenOptOut.
#
# Mint a local Certificate Authority (CA) and issue or revoke per-device
# client certificates exported as PKCS#12 (.p12) bundles.
#
# Usage:
#   ./scripts/openoptout-mtls.sh init-ca [--days 3650] [--ca-dir DIR] [--force]
#   ./scripts/openoptout-mtls.sh issue <device-name> [--days 365] [--ca-dir DIR] [--out FILE] [--pass PASS]
#   ./scripts/openoptout-mtls.sh revoke <device-name-or-serial> [--ca-dir DIR]
#   ./scripts/openoptout-mtls.sh list [--ca-dir DIR]
#   ./scripts/openoptout-mtls.sh status [--ca-dir DIR]
#
# Examples:
#   ./scripts/openoptout-mtls.sh init-ca
#   ./scripts/openoptout-mtls.sh issue "jordan-laptop"
#   ./scripts/openoptout-mtls.sh issue "phone-jordan" --out ~/Desktop/phone.p12
#   ./scripts/openoptout-mtls.sh revoke "phone-jordan"
#   ./scripts/openoptout-mtls.sh list
#   ./scripts/openoptout-mtls.sh status
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

command -v openssl >/dev/null 2>&1 || {
  echo -e "${RED}Error: openssl is required but not installed or not in PATH.${NC}" >&2
  exit 1
}

CA_DIR="deploy/ca"
PROXY_CERTS_DIR="deploy/certs"
CA_KEY="${CA_DIR}/client-ca.key"
CA_CERT="${CA_DIR}/client-ca.pem"
PROXY_CA_CERT="${PROXY_CERTS_DIR}/client-ca.pem"
INDEX_FILE="${CA_DIR}/index.json"
SERIAL_FILE="${CA_DIR}/serial"

usage() {
  cat <<EOF
Usage: $0 <command> [options]

Commands:
  init-ca                  Initialize a local private CA for client certificates
  issue <device-name>      Issue a client certificate for a device/browser (.p12)
  revoke <name-or-serial>  Revoke an issued client certificate
  list                     List all issued client certificates and their status
  status                   Display the local CA's status, validity, and fingerprint

Global options:
  --ca-dir DIR             Directory holding CA keys and index (default: deploy/ca)
  -h, --help               Show this help message

Options for init-ca:
  --days DAYS              CA validity in days (default: 3650 / 10 years)
  --force                  Overwrite existing CA if one already exists

Options for issue:
  --days DAYS              Certificate validity in days (default: 365 / 1 year)
  --out FILE               Destination path for .p12 bundle
  --pass PASS              Password to protect the .p12 bundle (prompted if omitted)

Options for revoke:
  --reason REASON          Revocation reason (optional)
EOF
  exit "${1:-1}"
}

if [ $# -lt 1 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
  usage 0
fi

CMD="$1"
shift

# Parse options
DAYS=""
FORCE=0
OUT_FILE=""
PASS=""
REASON="unspecified"
NAME_OR_SERIAL=""

while [ $# -gt 0 ]; do
  case "$1" in
    --ca-dir)
      CA_DIR="$2"
      CA_KEY="${CA_DIR}/client-ca.key"
      CA_CERT="${CA_DIR}/client-ca.pem"
      INDEX_FILE="${CA_DIR}/index.json"
      SERIAL_FILE="${CA_DIR}/serial"
      shift 2
      ;;
    --days)
      DAYS="$2"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --out)
      OUT_FILE="$2"
      shift 2
      ;;
    --pass)
      PASS="$2"
      shift 2
      ;;
    --reason)
      REASON="$2"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    -*)
      echo -e "${RED}Unknown option: $1${NC}" >&2
      usage
      ;;
    *)
      if [ -z "$NAME_OR_SERIAL" ]; then
        NAME_OR_SERIAL="$1"
      else
        echo -e "${RED}Unexpected extra argument: $1${NC}" >&2
        usage
      fi
      shift
      ;;
  esac
done

ensure_ca_dir() {
  mkdir -p "$CA_DIR"
  chmod 700 "$CA_DIR"
  mkdir -p "$PROXY_CERTS_DIR"
  if [ ! -f "$SERIAL_FILE" ]; then
    echo "1001" > "$SERIAL_FILE"
  fi
  if [ ! -f "$INDEX_FILE" ]; then
    echo "[]" > "$INDEX_FILE"
  fi
}

cmd_init_ca() {
  ensure_ca_dir
  local days="${DAYS:-3650}"

  if [ -f "$CA_CERT" ] && [ -f "$CA_KEY" ] && [ "$FORCE" -eq 0 ]; then
    echo -e "${YELLOW}A Client CA already exists at ${CA_CERT}.${NC}"
    echo "Pass --force to overwrite it (warning: all existing client certificates will be invalidated)."
    exit 1
  fi

  echo -e "${CYAN}==> Initializing OpenOptOut Client Certificate Authority...${NC}"
  local tmp_cnf
  tmp_cnf="$(mktemp)"
  cat > "$tmp_cnf" <<EOF
[req]
distinguished_name = req_dn
x509_extensions = v3_ca
prompt = no

[req_dn]
CN = OpenOptOut Client CA

[v3_ca]
basicConstraints = critical, CA:true
keyUsage = critical, digitalSignature, cRLSign, keyCertSign
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
EOF

  openssl req -new -x509 -newkey rsa:4096 -nodes \
    -keyout "$CA_KEY" \
    -out "$CA_CERT" \
    -days "$days" \
    -sha256 \
    -config "$tmp_cnf" >/dev/null 2>&1
  rm -f "$tmp_cnf"

  chmod 600 "$CA_KEY"
  chmod 644 "$CA_CERT"

  # Copy public CA cert to proxy certs dir so reverse proxy can verify client certs
  cp -f "$CA_CERT" "$PROXY_CA_CERT"
  chmod 644 "$PROXY_CA_CERT"

  local fp
  fp="$(openssl x509 -in "$CA_CERT" -noout -fingerprint -sha256 | cut -d= -f2)"
  local exp
  exp="$(openssl x509 -in "$CA_CERT" -noout -enddate | cut -d= -f2)"

  echo -e "${GREEN}✓ Client CA initialized successfully!${NC}"
  echo "  CA Certificate:   $CA_CERT"
  echo "  CA Private Key:   $CA_KEY (permissions locked: 600)"
  echo "  Proxy CA Copy:    $PROXY_CA_CERT"
  echo "  Valid Until:      $exp"
  echo "  SHA-256 Fingerprint: $fp"
  echo ""
  echo "Next steps:"
  echo "  1. Issue certificates for devices that need access:"
  echo "     $0 issue <device-name>"
  echo "  2. Enable mTLS enforcement on your reverse proxy:"
  echo "     ./scripts/enable-https.sh --client-mtls"
}

cmd_issue() {
  ensure_ca_dir
  if [ -z "$NAME_OR_SERIAL" ]; then
    echo -e "${RED}Error: device-name is required.${NC}" >&2
    echo "Example: $0 issue \"jordan-laptop\"" >&2
    exit 1
  fi

  local dev_name="$NAME_OR_SERIAL"
  # Sanitize name
  local safe_name
  safe_name="$(echo -n "$dev_name" | tr -c 'a-zA-Z0-9._-' '-' | sed 's/^-*//;s/-*$//')"
  if [ -z "$safe_name" ]; then
    safe_name="client"
  fi

  if [ ! -f "$CA_CERT" ] || [ ! -f "$CA_KEY" ]; then
    echo -e "${RED}Error: Client CA not found at ${CA_CERT}.${NC}" >&2
    echo "Run '$0 init-ca' first." >&2
    exit 1
  fi

  local days="${DAYS:-365}"
  local serial
  serial="$(cat "$SERIAL_FILE" 2>/dev/null || echo "1001")"
  local next_serial=$((serial + 1))
  echo "$next_serial" > "$SERIAL_FILE"

  local dev_dir="${CA_DIR}/issued/${safe_name}"
  mkdir -p "$dev_dir"
  chmod 700 "$dev_dir"

  local client_key="${dev_dir}/${safe_name}.key"
  local client_csr="${dev_dir}/${safe_name}.csr"
  local client_cert="${dev_dir}/${safe_name}.crt"
  local p12_path="${OUT_FILE:-${dev_dir}/${safe_name}.p12}"

  if [ -z "$PASS" ]; then
    echo -n "Enter password to protect the .p12 certificate bundle (press Enter for none): "
    read -r -s PASS
    echo ""
  fi

  echo -e "${CYAN}==> Generating client certificate for '$dev_name' (serial $serial)...${NC}"

  # 1. Generate client private key
  openssl genrsa -out "$client_key" 2048 >/dev/null 2>&1
  chmod 600 "$client_key"

  # 2. Generate CSR
  openssl req -new -key "$client_key" -out "$client_csr" \
    -subj "/CN=${dev_name}" >/dev/null 2>&1

  # 3. Sign certificate with CA
  local tmp_ext
  tmp_ext="$(mktemp)"
  cat > "$tmp_ext" <<EOF
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
EOF

  openssl x509 -req -in "$client_csr" \
    -CA "$CA_CERT" \
    -CAkey "$CA_KEY" \
    -set_serial "$serial" \
    -out "$client_cert" \
    -days "$days" \
    -sha256 \
    -extfile "$tmp_ext" >/dev/null 2>&1
  rm -f "$tmp_ext" "$client_csr"

  # 4. Export PKCS#12 bundle
  if [ -n "$PASS" ]; then
    openssl pkcs12 -export -out "$p12_path" \
      -inkey "$client_key" \
      -in "$client_cert" \
      -certfile "$CA_CERT" \
      -name "$dev_name" \
      -passout "pass:$PASS" >/dev/null 2>&1
  else
    openssl pkcs12 -export -out "$p12_path" \
      -inkey "$client_key" \
      -in "$client_cert" \
      -certfile "$CA_CERT" \
      -name "$dev_name" \
      -passout "pass:" >/dev/null 2>&1
  fi
  chmod 600 "$p12_path"

  # Update index.json
  local now_iso
  now_iso="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  local exp_iso
  exp_iso="$(openssl x509 -in "$client_cert" -noout -enddate | cut -d= -f2)"

  # Record in python helper or small shell append
  python3 - <<PYEOF
import json, os
idx_file = "$INDEX_FILE"
try:
    with open(idx_file, "r") as f:
        data = json.load(f)
except Exception:
    data = []
# Update or append
data = [entry for entry in data if entry.get("name") != "$dev_name" or entry.get("status") == "revoked"]
data.append({
    "name": "$dev_name",
    "serial": "$serial",
    "issued_at": "$now_iso",
    "expires_at": "$exp_iso",
    "status": "valid",
    "p12_path": "$p12_path"
})
with open(idx_file, "w") as f:
    json.dump(data, f, indent=2)
PYEOF

  echo -e "${GREEN}✓ Client certificate successfully issued!${NC}"
  echo "  Device Name:   $dev_name"
  echo "  Serial Number: $serial"
  echo "  Valid Until:   $exp_iso"
  echo "  PKCS#12 File:  $p12_path"
  echo ""
  echo -e "${BOLD}How to install this certificate on your device:${NC}"
  echo "  • macOS / iOS:   Double-click the .p12 file to import it into Keychain Access."
  echo "                   On iOS, air-drop or email the file and install under Profiles."
  echo "  • Windows:       Double-click the .p12 file, choose 'Current User' -> 'Personal' store."
  echo "  • Linux/Firefox: Settings -> Privacy & Security -> Certificates -> View Certificates -> Your Certificates -> Import."
  echo "  • Android:       Settings -> Security -> Encryption & credentials -> Install a certificate -> VPN & app user certificate."
}

cmd_revoke() {
  ensure_ca_dir
  if [ -z "$NAME_OR_SERIAL" ]; then
    echo -e "${RED}Error: device-name or serial number is required.${NC}" >&2
    echo "Example: $0 revoke \"jordan-laptop\"" >&2
    exit 1
  fi

  local target="$NAME_OR_SERIAL"
  python3 - <<PYEOF
import json, sys
idx_file = "$INDEX_FILE"
try:
    with open(idx_file, "r") as f:
        data = json.load(f)
except Exception:
    data = []

found = False
for entry in data:
    if entry.get("name") == "$target" or str(entry.get("serial")) == "$target":
        entry["status"] = "revoked"
        entry["revoked_at"] = "$REASON"
        found = True
        print(f"Revoked certificate for '{entry.get('name')}' (serial {entry.get('serial')}).")

if not found:
    print(f"Error: Certificate '$target' not found.", file=sys.stderr)
    sys.exit(1)

with open(idx_file, "w") as f:
    json.dump(data, f, indent=2)
PYEOF

  echo -e "${GREEN}✓ Certificate recorded as revoked.${NC}"
}

cmd_list() {
  ensure_ca_dir
  python3 - <<PYEOF
import json
idx_file = "$INDEX_FILE"
try:
    with open(idx_file, "r") as f:
        data = json.load(f)
except Exception:
    data = []

if not data:
    print("No client certificates have been issued yet.")
    print("Run './scripts/openoptout-mtls.sh issue <device-name>' to issue one.")
    exit(0)

print(f"{'DEVICE NAME':<24} {'SERIAL':<10} {'STATUS':<10} {'EXPIRES':<26} {'BUNDLE PATH'}")
print("-" * 90)
for e in data:
    name = e.get("name", "")[:23]
    serial = str(e.get("serial", ""))
    status = e.get("status", "valid")
    expires = str(e.get("expires_at", ""))[:25]
    path = e.get("p12_path", "")
    print(f"{name:<24} {serial:<10} {status:<10} {expires:<26} {path}")
PYEOF
}

cmd_status() {
  ensure_ca_dir
  if [ ! -f "$CA_CERT" ]; then
    echo -e "${YELLOW}Client CA has not been initialized yet.${NC}"
    echo "Run './scripts/openoptout-mtls.sh init-ca' to create one."
    exit 0
  fi

  local fp
  fp="$(openssl x509 -in "$CA_CERT" -noout -fingerprint -sha256 | cut -d= -f2)"
  local subj
  subj="$(openssl x509 -in "$CA_CERT" -noout -subject | sed 's/subject=//')"
  local start
  start="$(openssl x509 -in "$CA_CERT" -noout -startdate | cut -d= -f2)"
  local end
  end="$(openssl x509 -in "$CA_CERT" -noout -enddate | cut -d= -f2)"

  echo -e "${BOLD}OpenOptOut Client CA Status:${NC}"
  echo "  Subject:      $subj"
  echo "  Certificate:  $CA_CERT"
  echo "  Key:          $CA_KEY"
  echo "  Valid From:   $start"
  echo "  Valid Until:  $end"
  echo "  Fingerprint:  $fp"

  if [ -f "$PROXY_CA_CERT" ]; then
    local pfp
    pfp="$(openssl x509 -in "$PROXY_CA_CERT" -noout -fingerprint -sha256 | cut -d= -f2)"
    if [ "$fp" = "$pfp" ]; then
      echo -e "  Proxy Copy:   ${GREEN}$PROXY_CA_CERT (synchronized)${NC}"
    else
      echo -e "  Proxy Copy:   ${YELLOW}$PROXY_CA_CERT (out of sync! Run: cp $CA_CERT $PROXY_CA_CERT)${NC}"
    fi
  else
    echo -e "  Proxy Copy:   ${RED}Missing! Run: cp $CA_CERT $PROXY_CA_CERT${NC}"
  fi

  echo ""
  cmd_list
}

case "$CMD" in
  init-ca)
    cmd_init_ca
    ;;
  issue)
    cmd_issue
    ;;
  revoke)
    cmd_revoke
    ;;
  list)
    cmd_list
    ;;
  status)
    cmd_status
    ;;
  *)
    echo -e "${RED}Unknown command: $CMD${NC}" >&2
    usage
    ;;
esac
