#!/bin/bash
# Manual DNS cleanup hook for certbot
echo "==========================================="
echo "DNS-01 Challenge Cleanup"
echo "==========================================="
echo ""
echo "You can now remove the following DNS TXT record:"
echo ""
echo "Name: _acme-challenge.$CERTBOT_DOMAIN"
echo "Type: TXT"
echo "Value: $CERTBOT_VALIDATION"
echo ""
echo "This record is no longer needed for certificate validation."
