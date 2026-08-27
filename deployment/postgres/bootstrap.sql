\set ON_ERROR_STOP on

SELECT format('CREATE ROLE %I LOGIN', :'role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role')
\gexec

SELECT format('CREATE DATABASE eva OWNER %I', :'role')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'eva')
\gexec

\connect eva
CREATE EXTENSION IF NOT EXISTS vector;

SELECT extname, extversion
FROM pg_extension
WHERE extname = 'vector';
