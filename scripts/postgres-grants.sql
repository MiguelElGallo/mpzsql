\set ON_ERROR_STOP on

SELECT pgaadauth_create_principal(:'app_identity_name', false, false)
WHERE NOT EXISTS (
  SELECT 1
  FROM pg_roles
  WHERE rolname = :'app_identity_name'
);

GRANT CONNECT ON DATABASE :"app_database_name" TO :"app_identity_name";

\connect :"app_database_name"

GRANT CREATE, USAGE ON SCHEMA public TO :"app_identity_name";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app_identity_name";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_identity_name";

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_identity_name";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"app_identity_name";
