# Certificate Generation Scripts Comparison

This document compares the two certificate generation scripts available in this directory.

## Script Overview

| Feature | generate_cert.sh | generate_cert2.sh |
|---------|------------------|-------------------|
| **Certificate Type** | Self-signed | Let's Encrypt (trusted) |
| **Validation Method** | Local generation | DNS-01 challenge |
| **Trust Level** | Not trusted by browsers | Trusted by all major browsers |
| **Validity Period** | 365 days (configurable) | 90 days (auto-renewable) |
| **Cost** | Free | Free |
| **Setup Complexity** | Simple | Moderate |
| **Automation** | Full | Partial (renewal only) |
| **Internet Required** | No | Yes |
| **DNS Access Required** | No | Yes |

## When to Use Each Script

### Use `generate_cert.sh` (Self-signed) when:

✅ **Development and Testing**
- Local development environments
- Internal testing where browser warnings are acceptable
- Offline environments without internet access
- Quick prototyping and demos

✅ **Internal Networks**
- Internal company applications
- Services that don't face the public internet
- Development environments behind corporate firewalls

✅ **Learning and Experimentation**
- Understanding TLS/SSL concepts
- Testing certificate configurations
- Educational purposes

### Use `generate_cert2.sh` (Let's Encrypt) when:

✅ **Production Environments**
- Public-facing web services
- Applications that need trusted certificates
- Production deployments

✅ **Client-Facing Applications**
- Web applications accessed by end users
- APIs consumed by third-party clients
- Services requiring browser trust

✅ **Compliance Requirements**
- Applications requiring valid SSL certificates
- Environments with security compliance needs
- Professional deployments

## Technical Differences

### generate_cert.sh (Self-signed)
```bash
# Simple local generation
openssl req -x509 -newkey rsa:2048 -keyout server.key -out server.crt -days 365 -nodes

# Pros:
+ No external dependencies
+ Works offline
+ Instant generation
+ No rate limits
+ Full control over certificate details

# Cons:
- Browser security warnings
- Not trusted by default
- Manual trust required
- Not suitable for production
```

### generate_cert2.sh (Let's Encrypt)
```bash
# Domain validation required
certbot certonly --manual --preferred-challenges dns -d example.com

# Pros:
+ Trusted by all browsers
+ Professional appearance
+ Free trusted certificates
+ Automatic renewal possible
+ Industry standard

# Cons:
- Requires domain ownership
- Needs DNS management access
- Internet connectivity required
- 90-day validity (needs renewal)
- Rate limits apply
```

## Certificate Files Comparison

### Self-signed Certificates (generate_cert.sh)
```
certs/
├── server.crt          # Self-signed certificate
├── server.key          # Private key
└── openssl.conf        # OpenSSL configuration
```

### Let's Encrypt Certificates (generate_cert2.sh)
```
certs/
├── letsencrypt-server.crt      # Server certificate only
├── letsencrypt-server.key      # Private key
├── letsencrypt-fullchain.pem   # Certificate + intermediates (recommended)
├── letsencrypt-chain.pem       # Intermediate certificates only
├── auth-hook.sh                # DNS authentication script
└── cleanup-hook.sh             # DNS cleanup script
```

## Usage Examples

### Quick Development Setup (Self-signed)
```bash
# Generate certificate in seconds
./generate_cert.sh

# Start server immediately
python3 -m mpzsql.cli \
  --tls-cert ../../../certs/server.crt \
  --tls-key ../../../certs/server.key \
  --username admin --password secret

# Connect (ignore browser warnings)
curl -k https://localhost:8080/api/health
```

### Production Setup (Let's Encrypt)
```bash
# Generate trusted certificate (requires domain and DNS access)
./generate_cert2.sh -d myapp.example.com -e admin@example.com -p manual

# Start server with trusted certificate
python3 -m mpzsql.cli \
  --tls-cert ../../../certs/letsencrypt-fullchain.pem \
  --tls-key ../../../certs/letsencrypt-server.key \
  --username admin --password secret

# Connect without warnings
curl https://myapp.example.com:8080/api/health
```

## Migration Path

To migrate from self-signed to Let's Encrypt certificates:

1. **Test with staging first:**
   ```bash
   ./generate_cert2.sh -d yourdomain.com -e your@email.com -p manual --staging
   ```

2. **Generate production certificate:**
   ```bash
   ./generate_cert2.sh -d yourdomain.com -e your@email.com -p manual
   ```

3. **Update server configuration:**
   ```bash
   # Change from:
   --tls-cert ../../../certs/server.crt
   --tls-key ../../../certs/server.key
   
   # To:
   --tls-cert ../../../certs/letsencrypt-fullchain.pem
   --tls-key ../../../certs/letsencrypt-server.key
   ```

4. **Set up renewal:**
   ```bash
   # Add to crontab
   0 12 * * * /usr/bin/certbot renew --quiet
   ```

## Best Practices

### For Development
1. Use self-signed certificates for speed and simplicity
2. Document that certificates are self-signed in README
3. Provide instructions for accepting certificate warnings
4. Consider using mkcert for local development trust

### For Production
1. Always use Let's Encrypt or other trusted CA certificates
2. Set up automatic renewal before certificates expire
3. Monitor certificate expiration dates
4. Use full certificate chain files (fullchain.pem)
5. Test renewal process regularly

### For Both
1. Protect private keys with appropriate file permissions (600)
2. Use strong key sizes (2048-bit RSA minimum)
3. Keep certificates and keys in secure locations
4. Regular security updates and monitoring

## Troubleshooting

### Common Self-signed Issues
- **Browser warnings**: Expected behavior, add security exception
- **Client trust errors**: Import certificate to client trust store
- **API client errors**: Configure client to accept self-signed certificates

### Common Let's Encrypt Issues
- **Domain validation fails**: Check DNS configuration and propagation
- **Rate limits**: Use staging server for testing
- **Renewal fails**: Check permissions and DNS API credentials
- **Certificate not trusted**: Ensure using fullchain.pem

## Additional Resources

- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [Certbot User Guide](https://certbot.eff.org/docs/using.html)
- [OpenSSL Documentation](https://www.openssl.org/docs/)
- [TLS/SSL Best Practices](https://wiki.mozilla.org/Security/Server_Side_TLS)
