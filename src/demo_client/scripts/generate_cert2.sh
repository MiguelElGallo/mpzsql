#!/bin/bash
# Generate Let's Encrypt certificate using DNS-01 challenge
# This script creates a certificate verified by DNS TXT records using Let's Encrypt

set -e

# Configuration
CERT_DIR="../../../certs"
CERT_FILE="$CERT_DIR/letsencrypt-server.crt"
KEY_FILE="$CERT_DIR/letsencrypt-server.key"
FULLCHAIN_FILE="$CERT_DIR/letsencrypt-fullchain.pem"
CHAIN_FILE="$CERT_DIR/letsencrypt-chain.pem"
AUTH_HOOK_SCRIPT="$CERT_DIR/auth-hook.sh"
CLEANUP_HOOK_SCRIPT="$CERT_DIR/cleanup-hook.sh"

# Default values
DOMAIN=""
EMAIL=""
STAGING=false
DRY_RUN=false
CERT_NAME=""
DNS_PROVIDER=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to display usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Generate Let's Encrypt certificate using DNS-01 challenge with TXT record verification"
    echo ""
    echo "OPTIONS:"
    echo "  -d, --domain DOMAIN          Domain name for the certificate (required)"
    echo "  -e, --email EMAIL            Email address for Let's Encrypt account (required)"
    echo "  -n, --cert-name NAME         Certificate name (default: domain name)"
    echo "  -p, --dns-provider PROVIDER  DNS provider (manual, cloudflare, route53, etc.)"
    echo "  -s, --staging                Use Let's Encrypt staging server for testing"
    echo "  --dry-run                    Perform a test run without creating actual certificates"
    echo "  -h, --help                   Show this help message"
    echo ""
    echo "EXAMPLES:"
    echo "  # Manual DNS challenge (requires manual TXT record creation)"
    echo "  $0 -d example.com -e admin@example.com -p manual"
    echo ""
    echo "  # Staging server for testing"
    echo "  $0 -d test.example.com -e admin@example.com -p manual --staging"
    echo ""
    echo "  # Dry run to test configuration"
    echo "  $0 -d example.com -e admin@example.com -p manual --dry-run"
    echo ""
    echo "SUPPORTED DNS PROVIDERS:"
    echo "  - manual: Manual TXT record creation (default)"
    echo "  - cloudflare: Cloudflare DNS API (requires additional setup)"
    echo "  - route53: AWS Route53 DNS API (requires additional setup)"
    echo "  - google: Google Cloud DNS API (requires additional setup)"
    echo "  - And many others (see certbot documentation)"
    echo ""
    echo "PREREQUISITES:"
    echo "  1. Install certbot: brew install certbot (macOS) or apt install certbot (Ubuntu)"
    echo "  2. For automated DNS providers, install the respective certbot plugin"
    echo "  3. Ensure domain's DNS is publicly accessible"
    echo ""
    exit 1
}

# Function to print colored output
print_status() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Function to check if certbot is installed
check_certbot() {
    if ! command -v certbot &> /dev/null; then
        print_error "certbot is not installed. Please install it first:"
        echo "  macOS: brew install certbot"
        echo "  Ubuntu/Debian: sudo apt update && sudo apt install certbot"
        echo "  CentOS/RHEL: sudo yum install certbot"
        exit 1
    fi
    
    print_success "certbot is installed: $(certbot --version)"
}

# Function to validate domain format
validate_domain() {
    local domain="$1"
    if [[ ! "$domain" =~ ^[a-zA-Z0-9][a-zA-Z0-9\.-]*[a-zA-Z0-9]\.[a-zA-Z]{2,}$ ]]; then
        print_error "Invalid domain format: $domain"
        exit 1
    fi
}

# Function to validate email format
validate_email() {
    local email="$1"
    if [[ ! "$email" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
        print_error "Invalid email format: $email"
        exit 1
    fi
}

# Function to create manual DNS authentication hook
create_manual_auth_hook() {
    cat > "$AUTH_HOOK_SCRIPT" << 'EOF'
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
EOF
    chmod +x "$AUTH_HOOK_SCRIPT"
}

# Function to create manual DNS cleanup hook
create_manual_cleanup_hook() {
    cat > "$CLEANUP_HOOK_SCRIPT" << 'EOF'
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
EOF
    chmod +x "$CLEANUP_HOOK_SCRIPT"
}

# Function to build certbot command
build_certbot_command() {
    local cmd="certbot certonly"
    
    # User-writable directories (no root required)
    local config_dir="$HOME/.config/letsencrypt"
    local work_dir="$HOME/.local/share/letsencrypt"
    local logs_dir="$HOME/.local/share/letsencrypt/logs"
    
    # Create directories if they don't exist
    mkdir -p "$config_dir" "$work_dir" "$logs_dir"
    
    cmd="$cmd --config-dir $config_dir"
    cmd="$cmd --work-dir $work_dir"
    cmd="$cmd --logs-dir $logs_dir"
    
    # Basic options
    # Note: Don't use --non-interactive for manual DNS challenges
    # as it prevents the auth hook from displaying the TXT record value
    if [ "$DNS_PROVIDER" != "manual" ]; then
        cmd="$cmd --non-interactive"
    fi
    cmd="$cmd --agree-tos"
    cmd="$cmd --email $EMAIL"
    cmd="$cmd --domains $DOMAIN"
    
    # Certificate name
    if [ -n "$CERT_NAME" ]; then
        cmd="$cmd --cert-name $CERT_NAME"
    else
        cmd="$cmd --cert-name $DOMAIN"
    fi
    
    # DNS challenge type
    cmd="$cmd --preferred-challenges dns"
    
    # DNS provider specific options
    case "$DNS_PROVIDER" in
        "manual")
            cmd="$cmd --manual"
            cmd="$cmd --manual-auth-hook $AUTH_HOOK_SCRIPT"
            cmd="$cmd --manual-cleanup-hook $CLEANUP_HOOK_SCRIPT"
            ;;
        "cloudflare")
            cmd="$cmd --dns-cloudflare"
            cmd="$cmd --dns-cloudflare-credentials ~/.secrets/certbot/cloudflare.ini"
            ;;
        "route53")
            cmd="$cmd --dns-route53"
            ;;
        "google")
            cmd="$cmd --dns-google"
            cmd="$cmd --dns-google-credentials ~/.secrets/certbot/google.json"
            ;;
        *)
            if [ -n "$DNS_PROVIDER" ] && [ "$DNS_PROVIDER" != "manual" ]; then
                cmd="$cmd --dns-$DNS_PROVIDER"
            else
                cmd="$cmd --manual"
                cmd="$cmd --manual-auth-hook $AUTH_HOOK_SCRIPT"
                cmd="$cmd --manual-cleanup-hook $CLEANUP_HOOK_SCRIPT"
            fi
            ;;
    esac
    
    # Staging server
    if [ "$STAGING" = true ]; then
        cmd="$cmd --staging"
    fi
    
    # Dry run
    if [ "$DRY_RUN" = true ]; then
        cmd="$cmd --dry-run"
    fi
    
    echo "$cmd"
}

# Function to copy certificates to our cert directory
copy_certificates() {
    local cert_name="$1"
    local config_dir="$HOME/.config/letsencrypt"
    local live_dir="$config_dir/live/$cert_name"
    
    if [ ! -d "$live_dir" ]; then
        print_error "Certificate directory not found: $live_dir"
        print_error "Available certificates:"
        ls -la "$config_dir/live/" 2>/dev/null || echo "No certificates found"
        return 1
    fi
    
    print_status "Copying certificates to $CERT_DIR..."
    
    # Copy the certificates
    if [ -f "$live_dir/fullchain.pem" ]; then
        cp "$live_dir/fullchain.pem" "$FULLCHAIN_FILE"
        cp "$live_dir/cert.pem" "$CERT_FILE"
        print_success "Certificate copied to $CERT_FILE"
    fi
    
    if [ -f "$live_dir/chain.pem" ]; then
        cp "$live_dir/chain.pem" "$CHAIN_FILE"
        print_success "Chain copied to $CHAIN_FILE"
    fi
    
    if [ -f "$live_dir/privkey.pem" ]; then
        cp "$live_dir/privkey.pem" "$KEY_FILE"
        chmod 600 "$KEY_FILE"
        print_success "Private key copied to $KEY_FILE"
    fi
    
    # Set appropriate permissions
    chmod 644 "$CERT_FILE" 2>/dev/null || true
    chmod 644 "$FULLCHAIN_FILE" 2>/dev/null || true
    chmod 644 "$CHAIN_FILE" 2>/dev/null || true
}

# Function to display certificate information
show_certificate_info() {
    local cert_name="$1"
    local config_dir="$HOME/.config/letsencrypt"
    
    print_success "Certificate generated successfully!"
    echo ""
    print_status "Certificate information:"
    certbot certificates --cert-name "$cert_name" --config-dir "$config_dir" 2>/dev/null || true
    echo ""
    
    if [ -f "$CERT_FILE" ]; then
        print_status "Certificate details:"
        openssl x509 -in "$CERT_FILE" -text -noout | grep -A 3 "Subject:\|DNS:\|Not Before\|Not After" || true
    fi
    
    echo ""
    print_status "Files created:"
    echo "   Certificate: $CERT_FILE"
    echo "   Private Key: $KEY_FILE"
    echo "   Full Chain: $FULLCHAIN_FILE"
    echo "   Chain Only: $CHAIN_FILE"
    echo ""
    
    print_status "Usage with MPZSQL server:"
    echo "   python3 -m mpzsql.cli --tls-cert $FULLCHAIN_FILE --tls-key $KEY_FILE --username admin --password secret"
    echo ""
    
    print_status "Usage with client:"
    echo "   python3 src/demo_client/client.py connect --cert $FULLCHAIN_FILE --user admin --password secret --host $DOMAIN --port 8080"
}

# Function to show renewal information
show_renewal_info() {
    local cert_name="$1"
    local config_dir="$HOME/.config/letsencrypt"
    
    echo ""
    print_status "Certificate Renewal:"
    echo "Let's Encrypt certificates are valid for 90 days. To renew:"
    echo ""
    echo "Manual renewal:"
    echo "  certbot renew --cert-name $cert_name --config-dir $config_dir"
    echo ""
    echo "Automatic renewal (add to crontab):"
    echo "  0 12 * * * /usr/bin/certbot renew --quiet --config-dir $config_dir"
    echo ""
    echo "Test renewal:"
    echo "  certbot renew --cert-name $cert_name --dry-run --config-dir $config_dir"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--domain)
            DOMAIN="$2"
            shift 2
            ;;
        -e|--email)
            EMAIL="$2"
            shift 2
            ;;
        -n|--cert-name)
            CERT_NAME="$2"
            shift 2
            ;;
        -p|--dns-provider)
            DNS_PROVIDER="$2"
            shift 2
            ;;
        -s|--staging)
            STAGING=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Validate required arguments
if [ -z "$DOMAIN" ]; then
    print_error "Domain is required. Use -d or --domain to specify."
    usage
fi

if [ -z "$EMAIL" ]; then
    print_error "Email is required. Use -e or --email to specify."
    usage
fi

# Set defaults
if [ -z "$DNS_PROVIDER" ]; then
    DNS_PROVIDER="manual"
fi

if [ -z "$CERT_NAME" ]; then
    CERT_NAME="$DOMAIN"
fi

# Validate inputs
validate_domain "$DOMAIN"
validate_email "$EMAIL"

# Create certificates directory
mkdir -p "$CERT_DIR"

print_status "Starting Let's Encrypt certificate generation with DNS-01 challenge"
echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo "DNS Provider: $DNS_PROVIDER"
echo "Certificate Name: $CERT_NAME"
if [ "$STAGING" = true ]; then
    print_warning "Using staging server (certificates will not be trusted)"
fi
if [ "$DRY_RUN" = true ]; then
    print_warning "Dry run mode (no actual certificates will be created)"
fi
echo ""

# Check prerequisites
check_certbot

# Create manual hook scripts if using manual DNS
if [ "$DNS_PROVIDER" = "manual" ]; then
    print_status "Creating manual DNS authentication hooks..."
    create_manual_auth_hook
    create_manual_cleanup_hook
fi

# Build and execute certbot command
print_status "Building certbot command..."
CERTBOT_CMD=$(build_certbot_command)

print_status "Executing: $CERTBOT_CMD"
echo ""

# Execute certbot
if eval "$CERTBOT_CMD"; then
    if [ "$DRY_RUN" = false ]; then
        # Copy certificates to our directory
        copy_certificates "$CERT_NAME"
        
        # Show certificate information
        show_certificate_info "$CERT_NAME"
        
        # Show renewal information
        show_renewal_info "$CERT_NAME"
    else
        print_success "Dry run completed successfully!"
        print_status "Configuration is valid. Remove --dry-run to generate actual certificates."
    fi
else
    print_error "Certificate generation failed!"
    echo ""
    print_status "Common issues and solutions:"
    echo "1. DNS record not propagated - wait longer and try again"
    echo "2. Domain not publicly accessible - ensure DNS is configured correctly"
    echo "3. Rate limits - use --staging for testing or wait before retrying"
    echo "4. Invalid domain - check domain name format"
    echo ""
    print_status "Check certbot logs for more details:"
    echo "   tail -f $HOME/.local/share/letsencrypt/logs/letsencrypt.log"
    exit 1
fi

print_success "Certificate generation process completed!"
