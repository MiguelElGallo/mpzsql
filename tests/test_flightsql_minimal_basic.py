"""
Basic test suite for FlightSQL minimal server implementation.

Tests the MinimalFlightSQLServer class core functionality.
"""

from src.mpzsql.flightsql.minimal import SqlInfo


class TestSqlInfoConstants:
    """Test SqlInfo constant definitions."""

    def test_sql_info_constants_exist(self) -> None:
        """Test that all required SqlInfo constants are defined."""
        assert hasattr(SqlInfo, "FLIGHT_SQL_SERVER_NAME")
        assert hasattr(SqlInfo, "FLIGHT_SQL_SERVER_VERSION")
        assert hasattr(SqlInfo, "FLIGHT_SQL_SERVER_ARROW_VERSION")
        assert hasattr(SqlInfo, "FLIGHT_SQL_SERVER_READ_ONLY")

    def test_sql_info_values(self) -> None:
        """Test that SqlInfo constants have correct values."""
        assert SqlInfo.FLIGHT_SQL_SERVER_NAME == 0
        assert SqlInfo.FLIGHT_SQL_SERVER_VERSION == 1
        assert SqlInfo.FLIGHT_SQL_SERVER_ARROW_VERSION == 2
        assert SqlInfo.FLIGHT_SQL_SERVER_READ_ONLY == 3
