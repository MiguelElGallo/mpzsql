/*
 * FlightSqlJdbcTest.java — JDBC integration tests for the Lakehouse Flight SQL server.
 *
 * <p>Each test exercises DDL/DML via the Arrow Flight SQL JDBC driver against
 * a running server.  The server URL is passed via the system property
 * {@code flight.url} (e.g. {@code -Dflight.url=grpc://127.0.0.1:31337}).
 *
 * <p>The DuckLake catalog alias is assumed to be {@code lakehouse}; all tables
 * are created inside {@code lakehouse.main.<name>} and dropped after each test.
 *
 * <p>Run with:
 * <pre>
 *     mvn test -Dflight.url=grpc://127.0.0.1:31337
 * </pre>
 */
package lakehouse;

import static org.junit.jupiter.api.Assertions.*;

import java.sql.*;
import org.junit.jupiter.api.*;

@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class FlightSqlJdbcTest {

    private static final String ALIAS = "lakehouse";
    private static final String SCHEMA = "main";

    private static Connection conn;

    /** Fully-qualified table name inside the DuckLake catalog. */
    private static String fq(String table) {
        return ALIAS + "." + SCHEMA + "." + table;
    }

    @BeforeAll
    static void connect() throws SQLException {
        String url = System.getProperty("flight.url", "grpc://127.0.0.1:31337");
        String jdbc = "jdbc:arrow-flight-sql://"
                + url.replaceFirst("^grpc://", "")
                + "?useEncryption=false";
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

    private void dropIfExists(String table) throws SQLException {
        exec("DROP TABLE IF EXISTS " + fq(table));
    }

    // ───────────────── DDL / DML tests ─────────────────

    @Test
    @Order(1)
    void createTable() throws SQLException {
        String t = "t_jdbc_create";
        dropIfExists(t);
        exec("CREATE TABLE " + fq(t) + " (id INT, name TEXT)");

        try (ResultSet rs = query("SELECT COUNT(*) FROM " + fq(t))) {
            assertTrue(rs.next());
            assertEquals(0, rs.getInt(1));
        } finally {
            dropIfExists(t);
        }
    }

    @Test
    @Order(2)
    void insertSelect() throws SQLException {
        String t = "t_jdbc_ins";
        dropIfExists(t);
        exec("CREATE TABLE " + fq(t) + " (id INT, val TEXT)");
        exec("INSERT INTO " + fq(t) + " VALUES (1, 'hello'), (2, 'world')");

        try (ResultSet rs = query("SELECT id, val FROM " + fq(t) + " ORDER BY id")) {
            assertTrue(rs.next());
            assertEquals(1, rs.getInt(1));
            assertEquals("hello", rs.getString(2));

            assertTrue(rs.next());
            assertEquals(2, rs.getInt(1));
            assertEquals("world", rs.getString(2));

            assertFalse(rs.next());
        } finally {
            dropIfExists(t);
        }
    }

    @Test
    @Order(3)
    void updateRows() throws SQLException {
        String t = "t_jdbc_upd";
        dropIfExists(t);
        exec("CREATE TABLE " + fq(t) + " (id INT, val TEXT)");
        exec("INSERT INTO " + fq(t) + " VALUES (1, 'old'), (2, 'keep')");
        exec("UPDATE " + fq(t) + " SET val = 'new' WHERE id = 1");

        try (ResultSet rs = query("SELECT val FROM " + fq(t) + " WHERE id = 1")) {
            assertTrue(rs.next());
            assertEquals("new", rs.getString(1));
        } finally {
            dropIfExists(t);
        }
    }

    @Test
    @Order(4)
    void deleteRows() throws SQLException {
        String t = "t_jdbc_del";
        dropIfExists(t);
        exec("CREATE TABLE " + fq(t) + " (id INT)");
        exec("INSERT INTO " + fq(t) + " VALUES (1), (2), (3)");
        exec("DELETE FROM " + fq(t) + " WHERE id = 2");

        try (ResultSet rs = query("SELECT id FROM " + fq(t) + " ORDER BY id")) {
            assertTrue(rs.next()); assertEquals(1, rs.getInt(1));
            assertTrue(rs.next()); assertEquals(3, rs.getInt(1));
            assertFalse(rs.next());
        } finally {
            dropIfExists(t);
        }
    }

    @Test
    @Order(5)
    void dropTable() throws SQLException {
        String t = "t_jdbc_drop";
        dropIfExists(t);
        exec("CREATE TABLE " + fq(t) + " (id INT)");
        exec("DROP TABLE " + fq(t));

        assertThrows(SQLException.class, () -> query("SELECT 1 FROM " + fq(t)));
    }

    @Test
    @Order(6)
    void preparedInsert() throws SQLException {
        String t = "t_jdbc_prep";
        dropIfExists(t);
        exec("CREATE TABLE " + fq(t) + " (id INT, label TEXT)");

        String sql = "INSERT INTO " + fq(t) + " VALUES (?, ?)";
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setInt(1, 42);
            ps.setString(2, "answer");
            ps.executeUpdate();
        }

        try (ResultSet rs = query("SELECT id, label FROM " + fq(t))) {
            assertTrue(rs.next());
            assertEquals(42, rs.getInt(1));
            assertEquals("answer", rs.getString(2));
        } finally {
            dropIfExists(t);
        }
    }

    @Test
    @Order(7)
    void fullLifecycle() throws SQLException {
        String t = "t_jdbc_life";
        dropIfExists(t);

        // CREATE
        exec("CREATE TABLE " + fq(t) + " (id INT, val TEXT)");

        // INSERT
        exec("INSERT INTO " + fq(t) + " VALUES (1, 'a'), (2, 'b'), (3, 'c')");
        try (ResultSet rs = query("SELECT COUNT(*) FROM " + fq(t))) {
            assertTrue(rs.next());
            assertEquals(3, rs.getInt(1));
        }

        // UPDATE
        exec("UPDATE " + fq(t) + " SET val = 'z' WHERE id = 2");
        try (ResultSet rs = query("SELECT val FROM " + fq(t) + " WHERE id = 2")) {
            assertTrue(rs.next());
            assertEquals("z", rs.getString(1));
        }

        // DELETE
        exec("DELETE FROM " + fq(t) + " WHERE id = 3");
        try (ResultSet rs = query("SELECT COUNT(*) FROM " + fq(t))) {
            assertTrue(rs.next());
            assertEquals(2, rs.getInt(1));
        }

        // DROP
        exec("DROP TABLE " + fq(t));
        assertThrows(SQLException.class, () -> query("SELECT 1 FROM " + fq(t)));
    }
}
