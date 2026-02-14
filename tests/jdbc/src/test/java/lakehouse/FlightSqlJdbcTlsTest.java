/*
 * FlightSqlJdbcTlsTest.java — JDBC integration tests over TLS.
 *
 * <p>Connects to the Flight SQL server via {@code grpc+tls://} using
 * {@code useEncryption=true}. The Arrow JDBC driver uses shaded gRPC/Netty
 * internally, so we set {@code disableCertificateVerification=true} for
 * self-signed certs since Netty doesn't read JVM's default SSLContext.
 * Proper CA validation is covered by the ADBC TLS tests.
 *
 * <p>System properties:
 * <ul>
 *   <li>{@code flight.url} — e.g. {@code grpc+tls://127.0.0.1:12345}</li>
 * </ul>
 *
 * <p>Run with:
 * <pre>
 *     mvn test -Dflight.url=grpc+tls://127.0.0.1:12345 \
 *              -Dtest=FlightSqlJdbcTlsTest
 * </pre>
 */
package lakehouse;

import static org.junit.jupiter.api.Assertions.*;

import java.sql.*;
import org.junit.jupiter.api.*;

@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class FlightSqlJdbcTlsTest {

    private static Connection conn;

    @BeforeAll
    static void connect() throws Exception {
        String url = System.getProperty("flight.url", "grpc+tls://127.0.0.1:31337");

        // Build JDBC connection URL with encryption enabled.
        // disableCertificateVerification=true because the Arrow JDBC driver
        // uses shaded Netty which doesn't pick up JVM's SSLContext.setDefault().
        // The ADBC TLS tests cover proper CA chain validation.
        String host = url.replaceFirst("^grpc\\+tls://", "");
        String jdbc = "jdbc:arrow-flight-sql://" + host
                + "?useEncryption=true&disableCertificateVerification=true";

        conn = DriverManager.getConnection(jdbc);
    }

    @AfterAll
    static void disconnect() throws SQLException {
        if (conn != null && !conn.isClosed()) {
            conn.close();
        }
    }

    // ───────────────────── helpers ─────────────────────

    private void exec(String sql) throws SQLException {
        try (Statement st = conn.createStatement()) {
            st.execute(sql);
        }
    }

    private ResultSet query(String sql) throws SQLException {
        return conn.createStatement().executeQuery(sql);
    }

    // ───────────────── TLS tests ─────────────────

    @Test
    @Order(1)
    void simpleQueryOverTls() throws SQLException {
        try (ResultSet rs = query("SELECT 42 AS answer")) {
            assertTrue(rs.next());
            assertEquals(42, rs.getInt(1));
            assertFalse(rs.next());
        }
    }

    @Test
    @Order(2)
    void querySeededTableOverTls() throws SQLException {
        try (ResultSet rs = query("SELECT id, val FROM tls_test ORDER BY id")) {
            assertTrue(rs.next());
            assertEquals(1, rs.getInt("id"));
            assertEquals("encrypted", rs.getString("val"));

            assertTrue(rs.next());
            assertEquals(2, rs.getInt("id"));
            assertEquals("channel", rs.getString("val"));

            assertFalse(rs.next());
        }
    }

    @Test
    @Order(3)
    void ddlOverTls() throws SQLException {
        exec("CREATE TABLE tls_jdbc_ddl (x INT)");
        exec("INSERT INTO tls_jdbc_ddl VALUES (77)");

        try (ResultSet rs = query("SELECT x FROM tls_jdbc_ddl")) {
            assertTrue(rs.next());
            assertEquals(77, rs.getInt(1));
        } finally {
            exec("DROP TABLE IF EXISTS tls_jdbc_ddl");
        }
    }

    @Test
    @Order(4)
    void preparedStatementOverTls() throws SQLException {
        exec("CREATE TABLE tls_jdbc_prep (id INT, label TEXT)");
        try {
            String sql = "INSERT INTO tls_jdbc_prep VALUES (?, ?)";
            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                ps.setInt(1, 100);
                ps.setString(2, "secure");
                ps.executeUpdate();
            }

            try (ResultSet rs = query("SELECT id, label FROM tls_jdbc_prep")) {
                assertTrue(rs.next());
                assertEquals(100, rs.getInt(1));
                assertEquals("secure", rs.getString(2));
            }
        } finally {
            exec("DROP TABLE IF EXISTS tls_jdbc_prep");
        }
    }
}
