# JDBC Demo and Tests

## Run Azure Demo

`AzureDemo` requires endpoint and password at runtime.

### Args mode

```bash
MAVEN_OPTS="--add-opens=java.base/java.nio=ALL-UNNAMED" \
mvn -q \
  -Dexec.mainClass=lakehouse.AzureDemo \
  -Dexec.args="ca-myapp.westus.azurecontainerapps.io:443 <password> lakehouse" \
  test-compile exec:java
```

> **Note:** The `MAVEN_OPTS` flag is required for Apache Arrow on Java 17+.

### Environment mode

```bash
export LAKEHOUSE_DEMO_ENDPOINT="ca-myapp.westus.azurecontainerapps.io:443"
export LAKEHOUSE_DEMO_PASSWORD="<password>"
export LAKEHOUSE_DEMO_USER="lakehouse"
MAVEN_OPTS="--add-opens=java.base/java.nio=ALL-UNNAMED" \
mvn -q -Dexec.mainClass=lakehouse.AzureDemo test-compile exec:java
```

## Run JDBC Integration Tests

```bash
./run_jdbc_tests.sh grpc://127.0.0.1:31337
```
