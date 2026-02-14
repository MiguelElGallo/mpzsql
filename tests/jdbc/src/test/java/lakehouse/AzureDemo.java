package lakehouse;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.sql.*;

/**
 * Quick demo: discover catalogs/schemas, create a table in lakehouse.main,
 * insert rows, and query them on the deployed Azure Container App.
 *
 * Usage:
 *   AzureDemo <endpoint> <password> [username]
 *
 * Endpoint examples:
 *   ca-myapp.westus.azurecontainerapps.io
 *   ca-myapp.westus.azurecontainerapps.io:443
 *   grpc+tls://ca-myapp.westus.azurecontainerapps.io:443
 *
 * Optional environment fallback:
 *   LAKEHOUSE_DEMO_ENDPOINT, LAKEHOUSE_DEMO_PASSWORD, LAKEHOUSE_DEMO_USER
 */
public class AzureDemo {
    private static final String DEFAULT_USER = "lakehouse";
    private static final int DEFAULT_TLS_PORT = 443;
    private static final int DEFAULT_PLAINTEXT_PORT = 31337;

    private record EndpointTarget(String host, int port, boolean useEncryption) {}

    private static String envOrNull(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.trim();
    }

    private static String argOrEnv(String[] args, int index, String envName) {
        if (args.length > index && args[index] != null && !args[index].isBlank()) {
            return args[index].trim();
        }
        return envOrNull(envName);
    }

    private static void printUsageAndExit() {
        System.err.println("Usage: AzureDemo <endpoint> <password> [username]");
        System.err.println("  endpoint examples:");
        System.err.println("    ca-myapp.westus.azurecontainerapps.io");
        System.err.println("    ca-myapp.westus.azurecontainerapps.io:443");
        System.err.println("    grpc+tls://ca-myapp.westus.azurecontainerapps.io:443");
        System.err.println("  env fallback:");
        System.err.println("    LAKEHOUSE_DEMO_ENDPOINT, LAKEHOUSE_DEMO_PASSWORD, LAKEHOUSE_DEMO_USER");
        System.exit(2);
    }

    private static EndpointTarget parseEndpoint(String rawEndpoint) {
        String endpoint = rawEndpoint.trim();
        boolean useEncryption = true;
        int defaultPort = DEFAULT_TLS_PORT;

        if (endpoint.startsWith("grpc+tls://")) {
            endpoint = endpoint.substring("grpc+tls://".length());
            useEncryption = true;
            defaultPort = DEFAULT_TLS_PORT;
        } else if (endpoint.startsWith("grpc://")) {
            endpoint = endpoint.substring("grpc://".length());
            useEncryption = false;
            defaultPort = DEFAULT_PLAINTEXT_PORT;
        }

        String host = endpoint;
        int port = defaultPort;
        int colon = endpoint.lastIndexOf(':');
        if (colon > 0 && colon < endpoint.length() - 1) {
            host = endpoint.substring(0, colon);
            String portText = endpoint.substring(colon + 1);
            try {
                port = Integer.parseInt(portText);
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException("Invalid endpoint port: " + portText, e);
            }
        }
        if (host.isBlank()) {
            throw new IllegalArgumentException("Endpoint host must not be empty.");
        }
        return new EndpointTarget(host, port, useEncryption);
    }

    private static String enc(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        String endpoint = argOrEnv(args, 0, "LAKEHOUSE_DEMO_ENDPOINT");
        String password = argOrEnv(args, 1, "LAKEHOUSE_DEMO_PASSWORD");
        String username = argOrEnv(args, 2, "LAKEHOUSE_DEMO_USER");
        if (username == null) {
            username = DEFAULT_USER;
        }
        if (endpoint == null || password == null) {
            printUsageAndExit();
            return;
        }

        EndpointTarget target = parseEndpoint(endpoint);
        String jdbc = "jdbc:arrow-flight-sql://" + target.host() + ":" + target.port()
                + "?useEncryption=" + target.useEncryption()
                + "&user=" + enc(username)
                + "&password=" + enc(password);

        System.out.println("Connecting to " + target.host() + ":" + target.port() + " ...");
        try (Connection conn = DriverManager.getConnection(jdbc)) {
            Statement st = conn.createStatement();

            // ── DISCOVER CATALOGS & SCHEMAS ──
            System.out.println("\n=== CATALOGS ===");
            ResultSet rs = st.executeQuery(
                    "SELECT catalog_name FROM information_schema.schemata GROUP BY catalog_name");
            while (rs.next()) System.out.println("  " + rs.getString(1));
            rs.close();

            System.out.println("\n=== SCHEMAS ===");
            rs = st.executeQuery(
                    "SELECT catalog_name, schema_name FROM information_schema.schemata ORDER BY 1, 2");
            while (rs.next())
                System.out.println("  " + rs.getString(1) + "." + rs.getString(2));
            rs.close();

            // ── CREATE TABLE in lakehouse.main ──
            st.execute("CREATE TABLE IF NOT EXISTS lakehouse.main.whatever ("
                    + "id INTEGER, "
                    + "name TEXT, "
                    + "description TEXT, "
                    + "value DOUBLE, "
                    + "created_at TIMESTAMP)");
            System.out.println("\n✓  Created table 'lakehouse.main.whatever'");

            // ── INSERT ROWS ──
            String ins = "INSERT INTO lakehouse.main.whatever VALUES (?, ?, ?, ?, ?)";
            try (PreparedStatement ps = conn.prepareStatement(ins)) {
                Object[][] rows = {
                    {1, "Widget A", "First widget",   19.99, Timestamp.valueOf("2026-02-12 10:00:00")},
                    {2, "Widget B", "Second widget",  29.99, Timestamp.valueOf("2026-02-12 10:05:00")},
                    {3, "Widget C", "Third widget",   39.99, Timestamp.valueOf("2026-02-12 10:10:00")},
                    {4, "Gadget X", "Premium gadget", 99.50, Timestamp.valueOf("2026-02-12 10:15:00")},
                    {5, "Gadget Y", "Budget gadget",  49.75, Timestamp.valueOf("2026-02-12 10:20:00")},
                };
                for (Object[] r : rows) {
                    ps.setInt(1, (int) r[0]);
                    ps.setString(2, (String) r[1]);
                    ps.setString(3, (String) r[2]);
                    ps.setDouble(4, (double) r[3]);
                    ps.setTimestamp(5, (Timestamp) r[4]);
                    ps.executeUpdate();
                }
            }
            System.out.println("✓  Inserted 5 rows");

            // ── QUERY ──
            System.out.println("\n── SELECT * FROM lakehouse.main.whatever ORDER BY id ──");
            rs = st.executeQuery(
                    "SELECT id, name, description, value, created_at "
                    + "FROM lakehouse.main.whatever ORDER BY id");
            System.out.printf("%-4s %-12s %-18s %8s  %s%n",
                    "ID", "NAME", "DESCRIPTION", "VALUE", "CREATED_AT");
            System.out.println("-".repeat(70));
            while (rs.next()) {
                System.out.printf("%-4d %-12s %-18s %8.2f  %s%n",
                        rs.getInt("id"),
                        rs.getString("name"),
                        rs.getString("description"),
                        rs.getDouble("value"),
                        rs.getString("created_at"));
            }
            rs.close();
            st.close();
            System.out.println("\nDone.");
        }
    }
}
