CREATE ROLE jarvis_runtime LOGIN PASSWORD 'jarvis-runtime-dev';
GRANT CONNECT ON DATABASE jarvis TO jarvis_runtime;
GRANT USAGE ON SCHEMA public TO jarvis_runtime;
