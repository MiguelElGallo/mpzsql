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
import java.util.Calendar;
import java.util.TimeZone;
import org.junit.jupiter.api.*;

@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class FlightSqlJdbcTest {

    private static final String ALIAS = "lakehouse";
    private static final String SCHEMA = "main";
    private static final Calendar UTC_CALENDAR = Calendar.getInstance(TimeZone.getTimeZone("UTC"));

    private static Connection conn;

    /** Fully-qualified table name inside the DuckLake catalog. */
    private static String fq(String table) {
        return ALIAS + "." + SCHEMA + "." + table;
    }

    private static String uniqueTable(String prefix) {
        return "t_jdbc_" + prefix + "_" + java.util.UUID.randomUUID().toString().replace("-", "").substring(0, 12);
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
            assertEquals(1, ps.executeUpdate());
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
    void preparedTimestampRoundTrip() throws SQLException {
        String t = "t_jdbc_ts";
        dropIfExists(t);
        exec("CREATE TABLE " + fq(t) + " (id INT, created_at TIMESTAMP)");

        Timestamp expected = Timestamp.valueOf("2026-02-12 10:00:00");
        String sql = "INSERT INTO " + fq(t) + " VALUES (?, ?)";
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setInt(1, 1);
            ps.setTimestamp(2, expected, UTC_CALENDAR);
            ps.executeUpdate();
        }

        try (ResultSet rs = query("SELECT id, created_at FROM " + fq(t))) {
            assertTrue(rs.next());
            assertEquals(1, rs.getInt(1));
            assertEquals(expected, rs.getTimestamp(2, UTC_CALENDAR));
            assertFalse(rs.next());
        } finally {
            dropIfExists(t);
        }
    }

    @Test
    @Order(8)
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

    @Test
    @Order(9)
    void statementExecuteUpdateReturnsRowCounts() throws SQLException {
        String t = uniqueTable("counts");
        dropIfExists(t);
        try {
            try (Statement st = conn.createStatement()) {
                st.execute("CREATE TABLE " + fq(t) + " (id INT, val TEXT)");
                assertEquals(2, st.executeUpdate("INSERT INTO " + fq(t) + " VALUES (1, 'a'), (2, 'b')"));
                assertEquals(1, st.executeUpdate("UPDATE " + fq(t) + " SET val = 'z' WHERE id = 2"));
                assertEquals(1, st.executeUpdate("DELETE FROM " + fq(t) + " WHERE id = 1"));
            }

            try (ResultSet rs = query("SELECT id, val FROM " + fq(t) + " ORDER BY id")) {
                assertTrue(rs.next());
                assertEquals(2, rs.getInt(1));
                assertEquals("z", rs.getString(2));
                assertFalse(rs.next());
            }
        } finally {
            dropIfExists(t);
        }
    }

    @Test
    @Order(10)
    void metadataAndResultSetMetadataAreExposed() throws SQLException {
        String t = uniqueTable("meta");
        dropIfExists(t);
        try {
            exec("CREATE TABLE " + fq(t) + " (id INT, name TEXT, created_at TIMESTAMP)");
            exec("INSERT INTO " + fq(t) + " VALUES (1, 'alpha', TIMESTAMP '2026-02-12 10:00:00')");

            assertTrue(conn.isValid(2));

            DatabaseMetaData meta = conn.getMetaData();
            boolean sawCatalog = false;
            try (ResultSet rs = meta.getCatalogs()) {
                while (rs.next()) {
                    if (ALIAS.equals(rs.getString("TABLE_CAT"))) {
                        sawCatalog = true;
                        break;
                    }
                }
            }
            assertTrue(sawCatalog, "catalog list should include " + ALIAS);

            boolean sawSchema = false;
            try (ResultSet rs = meta.getSchemas(ALIAS, SCHEMA)) {
                while (rs.next()) {
                    if (ALIAS.equals(rs.getString("TABLE_CATALOG"))
                            && SCHEMA.equals(rs.getString("TABLE_SCHEM"))) {
                        sawSchema = true;
                        break;
                    }
                }
            }
            assertTrue(sawSchema, "schema list should include " + ALIAS + "." + SCHEMA);

            try (ResultSet rs = meta.getTables(ALIAS, SCHEMA, t, new String[] {"BASE TABLE"})) {
                assertTrue(rs.next());
                assertEquals(ALIAS, rs.getString("TABLE_CAT"));
                assertEquals(SCHEMA, rs.getString("TABLE_SCHEM"));
                assertEquals(t, rs.getString("TABLE_NAME"));
                assertEquals("BASE TABLE", rs.getString("TABLE_TYPE"));
                assertFalse(rs.next());
            }

            try (ResultSet rs = meta.getColumns(ALIAS, SCHEMA, t, null)) {
                String[] expectedNames = {"id", "name", "created_at"};
                int[] expectedTypes = {Types.INTEGER, Types.VARCHAR, Types.TIMESTAMP};
                int index = 0;
                while (rs.next()) {
                    assertTrue(index < expectedNames.length);
                    assertEquals(expectedNames[index], rs.getString("COLUMN_NAME"));
                    assertEquals(expectedTypes[index], rs.getInt("DATA_TYPE"));
                    index++;
                }
                assertEquals(expectedNames.length, index);
            }

            try (ResultSet rs = meta.getPrimaryKeys(ALIAS, SCHEMA, t)) {
                assertFalse(rs.next());
            }

            try (ResultSet rs = meta.getImportedKeys(ALIAS, SCHEMA, t)) {
                assertFalse(rs.next());
            }

            try (ResultSet rs = meta.getExportedKeys(ALIAS, SCHEMA, t)) {
                assertFalse(rs.next());
            }

            try (ResultSet rs = meta.getCrossReference(ALIAS, SCHEMA, t, ALIAS, SCHEMA, t)) {
                assertFalse(rs.next());
            }

            try (ResultSet rs = query("SELECT id, name, created_at FROM " + fq(t) + " ORDER BY id")) {
                ResultSetMetaData rsmd = rs.getMetaData();
                assertEquals(3, rsmd.getColumnCount());
                assertEquals("id", rsmd.getColumnLabel(1));
                assertEquals(Types.INTEGER, rsmd.getColumnType(1));
                assertEquals("name", rsmd.getColumnLabel(2));
                assertEquals(Types.VARCHAR, rsmd.getColumnType(2));
                assertEquals("created_at", rsmd.getColumnLabel(3));
                assertEquals(Types.TIMESTAMP, rsmd.getColumnType(3));

                assertTrue(rs.next());
                assertEquals(1, rs.getInt("id"));
                assertEquals("alpha", rs.getString("name"));
                assertEquals(
                        Timestamp.valueOf("2026-02-12 10:00:00"),
                        rs.getTimestamp("created_at", UTC_CALENDAR));
                assertFalse(rs.next());
            }
        } finally {
            dropIfExists(t);
        }
    }
}
