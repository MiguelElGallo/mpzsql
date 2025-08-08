# Let's Encrypt Certificate Generation with DNS-01 Challenge

This document explains how to use the `generate_cert2.sh` script to generate SSL/TLS certificates using Let's Encrypt with DNS-01 challenge verification.

## Overview

The `generate_cert2.sh` script generates SSL/TLS certificates from Let's Encrypt using DNS TXT record verification (DNS-01 challenge). This method allows you to:

- Generate certificates for domains without running a web server
- Create wildcard certificates (*.example.com)
- Generate certificates for internal/private domains
- Avoid firewall issues with HTTP-01 challenges

## Prerequisites

### 1. Install Certbot

**macOS (using Homebrew):**
```bash
brew install certbot
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install certbot
```

**CentOS/RHEL:**
```bash
sudo yum install certbot
```

### 2. Domain Requirements

- Domain must be publicly registered
- You must have access to modify DNS records for the domain
- Domain's DNS must be publicly accessible

## Basic Usage

### Manual DNS Challenge (Recommended for first-time users)

```bash
# Basic usage with manual DNS record creation
./generate_cert2.sh -d example.com -e admin@example.com -p manual

# Using staging server for testing
./generate_cert2.sh -d test.example.com -e admin@example.com -p manual --staging

# Dry run to test configuration
./generate_cert2.sh -d example.com -e admin@example.com -p manual --dry-run
```

### Command Line Options

```
-d, --domain DOMAIN          Domain name for the certificate (required)
-e, --email EMAIL            Email address for Let's Encrypt account (required)
-n, --cert-name NAME         Certificate name (default: domain name)
-p, --dns-provider PROVIDER  DNS provider (manual, cloudflare, route53, etc.)
-s, --staging                Use Let's Encrypt staging server for testing
--dry-run                    Perform a test run without creating certificates
-h, --help                   Show help message
```

## DNS Providers

### Manual DNS (Default)

Best for: Learning, testing, or one-time certificate generation.

```bash
./generate_cert2.sh -d example.com -e admin@example.com -p manual
```

The script will:
1. Display the required TXT record details
2. Wait for you to create the DNS record
3. Proceed with validation once you press Enter

**Manual Steps:**
1. Run the script
2. Create a TXT record as instructed:
   - Name: `_acme-challenge.example.com`
   - Type: `TXT`
   - Value: (provided by script)
   - TTL: `300` or your provider's minimum
3. Wait for DNS propagation (1-60 minutes)
4. Verify with: `dig TXT _acme-challenge.example.com`
5. Press Enter in the script to continue

### Cloudflare DNS

Best for: Automated certificate generation with Cloudflare-managed domains.

**Setup:**
1. Install Cloudflare plugin:
   ```bash
   # Ubuntu/Debian
   sudo apt install python3-certbot-dns-cloudflare

   # macOS
   pip3 install certbot-dns-cloudflare
   ```

2. Create credentials file:
   ```bash
   mkdir -p ~/.secrets/certbot
   chmod 700 ~/.secrets/certbot
   ```

3. Create `~/.secrets/certbot/cloudflare.ini`:
   ```ini
   # Cloudflare API credentials
   dns_cloudflare_email = your-email@example.com
   dns_cloudflare_api_key = your-global-api-key
   ```

   Or using API token (recommended):
   ```ini
   # Cloudflare API token
   dns_cloudflare_api_token = your-api-token
   ```

4. Secure the credentials:
   ```bash
   chmod 600 ~/.secrets/certbot/cloudflare.ini
   ```

5. Generate certificate:
   ```bash
   ./generate_cert2.sh -d example.com -e admin@example.com -p cloudflare
   ```

### AWS Route53

Best for: Domains managed in AWS Route53.

**Setup:**
1. Install Route53 plugin:
   ```bash
   # Ubuntu/Debian
   sudo apt install python3-certbot-dns-route53

   # macOS
   pip3 install certbot-dns-route53
   ```

2. Configure AWS credentials (choose one method):

   **Method 1: AWS CLI**
   ```bash
   aws configure
   ```

   **Method 2: Environment variables**
   ```bash
   export AWS_ACCESS_KEY_ID=your-access-key
   export AWS_SECRET_ACCESS_KEY=your-secret-key
   ```

   **Method 3: IAM role** (if running on EC2)

3. Generate certificate:
   ```bash
   ./generate_cert2.sh -d example.com -e admin@example.com -p route53
   ```

### Google Cloud DNS

Best for: Domains managed in Google Cloud DNS.

**Setup:**
1. Install Google DNS plugin:
   ```bash
   pip3 install certbot-dns-google
   ```

2. Create service account in Google Cloud Console
3. Download service account JSON file
4. Save to `~/.secrets/certbot/google.json`
5. Generate certificate:
   ```bash
   ./generate_cert2.sh -d example.com -e admin@example.com -p google
   ```

### Other DNS Providers

The script supports many other DNS providers. Install the appropriate certbot plugin:

```bash
# DigitalOcean
pip3 install certbot-dns-digitalocean

# OVH
pip3 install certbot-dns-ovh

# Linode
pip3 install certbot-dns-linode

# And many others...
```

Then use:
```bash
./generate_cert2.sh -d example.com -e admin@example.com -p digitalocean
```

## Generated Files

After successful generation, the following files are created in `../../../certs/`:

- `letsencrypt-server.crt` - Server certificate
- `letsencrypt-server.key` - Private key
- `letsencrypt-fullchain.pem` - Full certificate chain (recommended for most servers)
- `letsencrypt-chain.pem` - Intermediate certificates only

## Using with MPZSQL Server

Start the MPZSQL server with the generated certificate:

```bash
uv run mpzsql-server \
  --tls-cert ../../../certs/letsencrypt-fullchain.pem \
  --tls-key ../../../certs/letsencrypt-server.key \
  --username admin \
  --password secret
```

Connect with the client:

```bash
python3 src/demo_client/client.py connect \
  --cert ../../../certs/letsencrypt-fullchain.pem \
  --user admin \
  --password secret \
  --host example.com \
  --port 8080
```

## Certificate Renewal

Let's Encrypt certificates are valid for 90 days and should be renewed regularly.

### Manual Renewal

```bash
# Renew specific certificate
sudo certbot renew --cert-name example.com

# Renew all certificates
sudo certbot renew
```

### Automatic Renewal

Add to crontab for automatic renewal:

```bash
# Edit crontab
sudo crontab -e

# Add this line (runs twice daily)
0 12 * * * /usr/bin/certbot renew --quiet && systemctl reload nginx
```

### Test Renewal

Always test renewal before relying on it:

```bash
sudo certbot renew --cert-name example.com --dry-run
```

## Troubleshooting

### Common Issues

1. **DNS propagation delay**
   - Wait longer (up to 1 hour)
   - Check propagation: `dig TXT _acme-challenge.example.com`

2. **Rate limits**
   - Use `--staging` flag for testing
   - Let's Encrypt has rate limits: 50 certificates per week per domain

3. **Permission errors**
   - Run with `sudo` if needed
   - Check file permissions in `/etc/letsencrypt/`

4. **DNS provider API issues**
   - Verify API credentials
   - Check API rate limits
   - Ensure proper permissions

### Debug Information

Check certbot logs:
```bash
sudo tail -f /var/log/letsencrypt/letsencrypt.log
```

Test DNS resolution:
```bash
# Check if TXT record exists
dig TXT _acme-challenge.example.com

# Check from different DNS servers
nslookup -type=TXT _acme-challenge.example.com 8.8.8.8
```

## Security Considerations

1. **Protect private keys**: Ensure private key files have restrictive permissions (600)
2. **Secure API credentials**: Store DNS provider credentials securely
3. **Regular renewal**: Set up automatic renewal to avoid expired certificates
4. **Monitor expiration**: Use monitoring tools to track certificate expiration

## Examples

### Wildcard Certificate

```bash
# Generate wildcard certificate (requires DNS-01 challenge)
./generate_cert2.sh -d "*.example.com" -e admin@example.com -p cloudflare
```

### Multiple Domains

```bash
# For multiple domains, run separate commands or use certbot directly
./generate_cert2.sh -d www.example.com -e admin@example.com -p manual
./generate_cert2.sh -d api.example.com -e admin@example.com -p manual
```

### Testing with Staging

Always test with staging first:

```bash
./generate_cert2.sh -d test.example.com -e admin@example.com -p manual --staging
```

## Additional Resources

- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [Certbot Documentation](https://certbot.eff.org/docs/)
- [DNS-01 Challenge Details](https://letsencrypt.org/docs/challenge-types/#dns-01-challenge)
- [Rate Limits](https://letsencrypt.org/docs/rate-limits/)
