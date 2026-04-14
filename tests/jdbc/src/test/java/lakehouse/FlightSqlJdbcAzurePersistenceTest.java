/*
 * Live JDBC persistence test for the deployed Azure Container App.
 *
 * <p>System properties:
 * <ul>
 *   <li>{@code flight.url} - e.g. {@code grpc+tls://ca-example.region.azurecontainerapps.io:443}</li>
 *   <li>{@code flight.user} - defaults to {@code lakehouse}</li>
 *   <li>{@code FLIGHT_PASSWORD} environment variable - required</li>
 * </ul>
 *
 * <p>Run with:
 * <pre>
 *     mvn test -Dflight.url=grpc+tls://ca-example.region.azurecontainerapps.io:443 \
 *              -Dflight.user=lakehouse \
 *              -Dtest=FlightSqlJdbcAzurePersistenceTest
 * </pre>
 */
package lakehouse;

import static org.junit.jupiter.api.Assertions.*;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.UUID;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;

class FlightSqlJdbcAzurePersistenceTest {
    private static final String ALIAS = "lakehouse";
    private static final String SCHEMA = "main";
    private static final String DEFAULT_USER = "lakehouse";
    private static final int DEFAULT_TLS_PORT = 443;
    private static final int DEFAULT_PLAINTEXT_PORT = 31337;

    private record EndpointTarget(String host, int port, boolean useEncryption) {}

    private static String fq(String table) {
        return ALIAS + "." + SCHEMA + "." + table;
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

    private static boolean isConfigured(String value) {
        return value != null && !value.isBlank() && !value.startsWith("${");
    }

    private static Connection connect() throws SQLException {
        String endpoint = System.getProperty("flight.url");
        String password = System.getenv("FLIGHT_PASSWORD");
        String username = System.getProperty("flight.user", DEFAULT_USER);
        boolean required = Boolean.getBoolean("live.azure.jdbc.required");
        if (!isConfigured(username)) {
            username = DEFAULT_USER;
        }

        if (required) {
            assertTrue(isConfigured(endpoint), "flight.url is required");
            assertTrue(isConfigured(password), "FLIGHT_PASSWORD is required");
        } else {
            Assumptions.assumeTrue(isConfigured(endpoint), "flight.url is required");
            Assumptions.assumeTrue(isConfigured(password), "FLIGHT_PASSWORD is required");
        }

        EndpointTarget target = parseEndpoint(endpoint);
        String jdbc = "jdbc:arrow-flight-sql://" + target.host() + ":" + target.port()
                + "?useEncryption=" + target.useEncryption()
                + "&user=" + enc(username)
                + "&password=" + enc(password);

        return DriverManager.getConnection(jdbc);
    }

    private static void dropBestEffort(String table) {
        try (Connection conn = connect();
             Statement st = conn.createStatement()) {
            st.execute("DROP TABLE IF EXISTS " + table);
        } catch (Exception ignored) {
            // Cleanup is best-effort; the primary assertion failure should stay visible.
        }
    }

    @Test
    void persistsWritesAcrossJdbcConnections() throws SQLException {
        String suffix = UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        String table = fq("live_jdbc_persist_" + suffix);

        try {
            try (Connection writer = connect();
                 Statement st = writer.createStatement()) {
                writer.setAutoCommit(true);
                st.execute("DROP TABLE IF EXISTS " + table);
                st.execute("CREATE TABLE " + table + " (id INT, label TEXT)");
                st.execute("INSERT INTO " + table + " VALUES (101, 'alpha'), (202, 'beta')");
            }

            try (Connection reader = connect();
                 Statement st = reader.createStatement();
                 ResultSet rs = st.executeQuery("SELECT id, label FROM " + table + " ORDER BY id")) {
                assertTrue(rs.next());
                assertEquals(101, rs.getInt("id"));
                assertEquals("alpha", rs.getString("label"));

                assertTrue(rs.next());
                assertEquals(202, rs.getInt("id"));
                assertEquals("beta", rs.getString("label"));

                assertFalse(rs.next());
            }
        } finally {
            dropBestEffort(table);
        }
    }
}
