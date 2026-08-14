#!/usr/bin/env bash
set -euo pipefail

# Directory where certs are stored
CERTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${CERTS_DIR}"

# Detect host local IP or fallback to generic placeholder
HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "192.168.1.100")

echo "Generating self-signed SSL certificate with SAN..."
echo "Host IP: ${HOST_IP}"

# Create OpenSSL config with SAN
cat > openssl.cnf <<EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
req_extensions = req_ext
distinguished_name = dn

[dn]
C = JP
ST = Tokyo
L = Tokyo
O = LocalDev
OU = RCE
CN = ${HOST_IP}

[req_ext]
subjectAltName = @alt_names

[alt_names]
IP.1 = ${HOST_IP}
IP.2 = 127.0.0.1
DNS.1 = localhost
DNS.2 = your-domain.local
EOF

# Generate private key and self-signed certificate (valid for 365 days)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout server.key \
    -out server.crt \
    -config openssl.cnf

chmod 600 server.key
chmod 644 server.crt
rm -f openssl.cnf

echo "Successfully generated server.crt and server.key in ${CERTS_DIR}"
