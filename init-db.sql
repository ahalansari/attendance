-- Initialize the PostgreSQL database for QR Code Attendance System
-- This script sets up the database with proper permissions and configurations

-- Create the database (if using a different initialization method)
-- CREATE DATABASE attendance_db;

-- Grant privileges to the attendance_user
GRANT ALL PRIVILEGES ON DATABASE attendance_db TO attendance_user;

-- Set up extensions (if needed)
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- CREATE EXTENSION IF NOT EXISTS "postgis"; -- Only if using geographic features

-- Create any initial data or configurations here
-- Example: Default admin user setup can be done via Django fixtures instead

-- Performance optimizations for attendance tracking
-- Set up connection pooling parameters
ALTER SYSTEM SET max_connections = 200;
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;
