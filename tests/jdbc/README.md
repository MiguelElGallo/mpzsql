# JDBC Demo and Tests

## Start Here

If you just deployed to Azure and want a fast proof that the JDBC path works, run `AzureDemo` first. It is the simplest end-to-end check for Arrow Flight SQL over JDBC.

If you want the shortest version, use the environment-variable form below.

## Run Azure Demo

`AzureDemo` requires an endpoint and password at runtime.

### Recommended

Use environment variables. It is the most reliable way to run the demo.

```bash
export LAKEHOUSE_DEMO_ENDPOINT="ca-myapp.westus.azurecontainerapps.io:443"
export LAKEHOUSE_DEMO_PASSWORD="<password>"
export LAKEHOUSE_DEMO_USER="lakehouse"
MAVEN_OPTS="--add-opens=java.base/java.nio=ALL-UNNAMED" \
mvn -q -Dexec.mainClass=lakehouse.AzureDemo test-compile exec:java
```

### Positional args

```bash
MAVEN_OPTS="--add-opens=java.base/java.nio=ALL-UNNAMED" \
mvn -q \
  -Dexec.mainClass=lakehouse.AzureDemo \
  -Dexec.args="ca-myapp.westus.azurecontainerapps.io:443 <password> lakehouse" \
  test-compile exec:java
```

> **Note:** The `MAVEN_OPTS` flag is required for Apache Arrow on Java 17+.

If `mvn exec:java` does not pass `-Dexec.args` through as expected in your environment, use the environment-variable form above.

## Run JDBC Integration Tests

Use this after the demo if you want the repeatable test suite instead of the human-friendly walkthrough.

```bash
./run_jdbc_tests.sh
```

This starts a temporary local DuckLake-backed server using the current
`DUCKLAKE_*` environment variables, then runs the Maven JDBC suite against it.

To point the suite at an already-running Flight SQL server instead:

```bash
./run_jdbc_tests.sh grpc://127.0.0.1:31337
```
