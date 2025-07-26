#!/bin/bash
# Manual DNS authentication hook for certbot

# Redirect hook's output and input to the user's terminal
exec > /dev/tty
exec < /dev/tty

echo ""
echo "==========================================="
echo "DNS-01 Challenge Authentication Required"
echo "==========================================="
echo ""
echo "Domain: $CERTBOT_DOMAIN"
echo ""
echo "Please create the following DNS TXT record:"
echo ""
echo "Record Name: _acme-challenge.$CERTBOT_DOMAIN"
echo "Record Type: TXT"
echo "Record Value: $CERTBOT_VALIDATION"
echo "TTL: 300 (or your DNS provider's minimum)"
echo ""
echo "IMPORTANT: Copy this exact value for the TXT record:"
echo "$CERTBOT_VALIDATION"
echo ""
echo "After creating the record, wait for DNS propagation (usually 1-10 minutes)."
echo ""
echo "Press Enter when you have created the DNS record and it has propagated..."

# Simple read without complex verification loop
read -r

echo "Continuing with validation..."
