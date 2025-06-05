#!/usr/bin/env python3
"""Initialize database with proper SIP server tables."""
import asyncio
import asyncpg
import os
import sys
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_database_schema(database_url: str):
    """Create complete database schema for SIP server."""
    
    logger.info("Connecting to database...")
    conn = await asyncpg.connect(database_url)
    
    try:
        # Create Kamailio core tables
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS version (
                table_name VARCHAR(32) NOT NULL,
                table_version INTEGER DEFAULT 0 NOT NULL,
                CONSTRAINT version_table_name_idx UNIQUE (table_name)
            );
        """)
        
        # Subscriber table for authentication
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriber (
                id SERIAL PRIMARY KEY NOT NULL,
                username VARCHAR(64) DEFAULT '' NOT NULL,
                domain VARCHAR(64) DEFAULT '' NOT NULL,
                password VARCHAR(25) DEFAULT '' NOT NULL,
                email_address VARCHAR(64) DEFAULT '' NOT NULL,
                ha1 VARCHAR(64) DEFAULT '' NOT NULL,
                ha1b VARCHAR(64) DEFAULT '' NOT NULL,
                rpid VARCHAR(64) DEFAULT NULL,
                CONSTRAINT subscriber_account_idx UNIQUE (username, domain)
            );
        """)
        
        # Location table for user registration
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS location (
                id SERIAL PRIMARY KEY NOT NULL,
                ruid VARCHAR(64) DEFAULT '' NOT NULL,
                username VARCHAR(64) DEFAULT '' NOT NULL,
                domain VARCHAR(64) DEFAULT NULL,
                contact VARCHAR(512) DEFAULT '' NOT NULL,
                received VARCHAR(128) DEFAULT NULL,
                path VARCHAR(512) DEFAULT NULL,
                expires TIMESTAMP WITHOUT TIME ZONE DEFAULT '2030-05-28 21:32:15' NOT NULL,
                q REAL DEFAULT 1.0 NOT NULL,
                callid VARCHAR(255) DEFAULT 'Default-Call-ID' NOT NULL,
                cseq INTEGER DEFAULT 1 NOT NULL,
                last_modified TIMESTAMP WITHOUT TIME ZONE DEFAULT '2000-01-01 00:00:01' NOT NULL,
                flags INTEGER DEFAULT 0 NOT NULL,
                cflags INTEGER DEFAULT 0 NOT NULL,
                user_agent VARCHAR(255) DEFAULT '' NOT NULL,
                socket VARCHAR(64) DEFAULT NULL,
                methods INTEGER DEFAULT NULL,
                instance VARCHAR(255) DEFAULT NULL,
                reg_id INTEGER DEFAULT 0 NOT NULL,
                server_id INTEGER DEFAULT 0 NOT NULL,
                connection_id INTEGER DEFAULT 0 NOT NULL,
                keepalive INTEGER DEFAULT 0 NOT NULL,
                partition INTEGER DEFAULT 0 NOT NULL
            );
        """)
        
        # Dialog table for active calls
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dialog (
                id SERIAL PRIMARY KEY NOT NULL,
                hash_entry INTEGER NOT NULL,
                hash_id INTEGER NOT NULL,
                callid VARCHAR(255) NOT NULL,
                from_uri VARCHAR(128) NOT NULL,
                from_tag VARCHAR(64) NOT NULL,
                to_uri VARCHAR(128) NOT NULL,
                to_tag VARCHAR(64) NOT NULL,
                caller_cseq VARCHAR(20) NOT NULL,
                callee_cseq VARCHAR(20) NOT NULL,
                caller_route_set TEXT,
                callee_route_set TEXT,
                caller_contact VARCHAR(128) NOT NULL,
                callee_contact VARCHAR(128) NOT NULL,
                caller_sock VARCHAR(64) NOT NULL,
                callee_sock VARCHAR(64) NOT NULL,
                state INTEGER NOT NULL,
                start_time INTEGER NOT NULL,
                timeout INTEGER DEFAULT 0 NOT NULL,
                sflags INTEGER DEFAULT 0 NOT NULL,
                iflags INTEGER DEFAULT 0 NOT NULL,
                toroute_name VARCHAR(32),
                req_uri VARCHAR(128) NOT NULL,
                xdata TEXT
            );
        """)
        
        # Dispatcher table for SIP trunk management
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dispatcher (
                id SERIAL PRIMARY KEY NOT NULL,
                setid INTEGER DEFAULT 0 NOT NULL,
                destination VARCHAR(192) DEFAULT '' NOT NULL,
                flags INTEGER DEFAULT 0 NOT NULL,
                priority INTEGER DEFAULT 0 NOT NULL,
                attrs VARCHAR(128) DEFAULT '' NOT NULL,
                description VARCHAR(64) DEFAULT '' NOT NULL
            );
        """)
        
        # Dialog variables table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dialog_vars (
                id SERIAL PRIMARY KEY NOT NULL,
                hash_entry INTEGER NOT NULL,
                hash_id INTEGER NOT NULL,
                dialog_key VARCHAR(128) NOT NULL,
                dialog_value VARCHAR(512) NOT NULL
            );
        """)
        
        # Address table for permissions module
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS address (
                id SERIAL PRIMARY KEY NOT NULL,
                grp INTEGER DEFAULT 1 NOT NULL,
                ip_addr VARCHAR(50) NOT NULL,
                mask INTEGER DEFAULT 32 NOT NULL,
                port INTEGER DEFAULT 0 NOT NULL,
                tag VARCHAR(64)
            );
        """)
        
        # Trusted table for permissions module
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trusted (
                id SERIAL PRIMARY KEY NOT NULL,
                src_ip VARCHAR(50) NOT NULL,
                proto VARCHAR(4) NOT NULL,
                from_pattern VARCHAR(64) DEFAULT NULL,
                ruri_pattern VARCHAR(64) DEFAULT NULL,
                tag VARCHAR(64) DEFAULT NULL,
                priority INTEGER DEFAULT 0 NOT NULL
            );
        """)
        
        # Call detail records for our application
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS call_records (
                id SERIAL PRIMARY KEY NOT NULL,
                call_id VARCHAR(255) UNIQUE NOT NULL,
                from_number VARCHAR(50) NOT NULL,
                to_number VARCHAR(50) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                status VARCHAR(20) NOT NULL,
                start_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                end_time TIMESTAMP WITHOUT TIME ZONE,
                duration INTEGER,
                recording_url VARCHAR(500),
                transcription JSONB,
                metadata JSONB,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
            );
        """)
        
        # SMS records
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sms_records (
                id SERIAL PRIMARY KEY NOT NULL,
                message_id VARCHAR(255) UNIQUE NOT NULL,
                from_number VARCHAR(50) NOT NULL,
                to_number VARCHAR(50) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                message TEXT NOT NULL,
                status VARCHAR(20) NOT NULL,
                segments INTEGER DEFAULT 1,
                error_message VARCHAR(500),
                metadata JSONB,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                delivered_at TIMESTAMP WITHOUT TIME ZONE
            );
        """)
        
        # Registered numbers
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS registered_numbers (
                id SERIAL PRIMARY KEY NOT NULL,
                number VARCHAR(50) UNIQUE NOT NULL,
                display_name VARCHAR(100),
                username VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                domain VARCHAR(100) NOT NULL,
                capabilities JSONB DEFAULT '["voice", "sms"]',
                active BOOLEAN DEFAULT TRUE,
                metadata JSONB,
                registered_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                last_seen TIMESTAMP WITHOUT TIME ZONE
            );
        """)
        
        # Blocked numbers
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blocked_numbers (
                id SERIAL PRIMARY KEY NOT NULL,
                number VARCHAR(50) UNIQUE NOT NULL,
                reason VARCHAR(500),
                blocked_by VARCHAR(100),
                blocked_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                expires_at TIMESTAMP WITHOUT TIME ZONE
            );
        """)
        
        # Configuration table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS configuration (
                id SERIAL PRIMARY KEY NOT NULL,
                key VARCHAR(100) UNIQUE NOT NULL,
                value JSONB NOT NULL,
                description VARCHAR(500),
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                updated_by VARCHAR(100)
            );
        """)
        
        # Webhook logs
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS webhook_logs (
                id SERIAL PRIMARY KEY NOT NULL,
                event_type VARCHAR(50) NOT NULL,
                url VARCHAR(500) NOT NULL,
                payload JSONB NOT NULL,
                response_status INTEGER,
                response_body TEXT,
                attempts INTEGER DEFAULT 1,
                success BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                delivered_at TIMESTAMP WITHOUT TIME ZONE
            );
        """)
        
        # API users
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS api_users (
                id SERIAL PRIMARY KEY NOT NULL,
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                api_key VARCHAR(255) UNIQUE,
                is_active BOOLEAN DEFAULT TRUE,
                is_admin BOOLEAN DEFAULT FALSE,
                last_login TIMESTAMP WITHOUT TIME ZONE,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
            );
        """)
        
        # Create indexes
        logger.info("Creating indexes...")
        
        await conn.execute("CREATE INDEX IF NOT EXISTS location_account_contact_idx ON location (username, domain, contact);")
        await conn.execute("CREATE INDEX IF NOT EXISTS location_expires_idx ON location (expires);")
        await conn.execute("CREATE INDEX IF NOT EXISTS dialog_hash_idx ON dialog (hash_entry, hash_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS call_records_time_idx ON call_records (start_time, end_time);")
        await conn.execute("CREATE INDEX IF NOT EXISTS call_records_numbers_idx ON call_records (from_number, to_number);")
        await conn.execute("CREATE INDEX IF NOT EXISTS sms_records_time_idx ON sms_records (created_at);")
        await conn.execute("CREATE INDEX IF NOT EXISTS sms_records_numbers_idx ON sms_records (from_number, to_number);")
        await conn.execute("CREATE INDEX IF NOT EXISTS webhook_logs_time_idx ON webhook_logs (created_at);")
        await conn.execute("CREATE INDEX IF NOT EXISTS blocked_numbers_expires_idx ON blocked_numbers (expires_at);")
        
        # Insert version information
        logger.info("Updating version table...")
        version_data = [
            ('subscriber', 7),
            ('location', 9),
            ('dialog', 7),
            ('dialog_vars', 1),
            ('dispatcher', 4),
            ('address', 6),
            ('trusted', 6),
            ('call_records', 1),
            ('sms_records', 1),
            ('registered_numbers', 1),
            ('blocked_numbers', 1),
            ('configuration', 1),
            ('webhook_logs', 1),
            ('api_users', 1)
        ]
        
        for table_name, version in version_data:
            await conn.execute("""
                INSERT INTO version (table_name, table_version) 
                VALUES ($1, $2) 
                ON CONFLICT (table_name) 
                DO UPDATE SET table_version = $2
            """, table_name, version)
        
        # Insert default admin user
        logger.info("Creating default admin user...")
        import hashlib
        password_hash = hashlib.sha256("admin123".encode()).hexdigest()
        
        await conn.execute("""
            INSERT INTO api_users (username, email, password_hash, is_admin, api_key)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (username) DO NOTHING
        """, "admin", "admin@olib.ai", password_hash, True, "test-api-key-change-in-production")
        
        # Insert default configuration
        logger.info("Setting default configuration...")
        config_items = [
            ('sip_domains', '["sip.olib.local"]', 'Configured SIP domains'),
            ('rtp_port_start', '10000', 'RTP port range start'),
            ('rtp_port_end', '20000', 'RTP port range end'),
            ('max_concurrent_calls', '1000', 'Maximum concurrent calls'),
            ('enable_recording', 'false', 'Enable call recording'),
            ('enable_transcription', 'false', 'Enable call transcription'),
            ('rate_limit', '{"calls_per_minute": 60, "sms_per_minute": 100}', 'Rate limiting configuration')
        ]
        
        for key, value, description in config_items:
            await conn.execute("""
                INSERT INTO configuration (key, value, description)
                VALUES ($1, $2, $3)
                ON CONFLICT (key) DO NOTHING
            """, key, value, description)
        
        logger.info("✅ Database schema created successfully!")
        
    except Exception as e:
        logger.error(f"❌ Error creating database schema: {e}")
        raise
    finally:
        await conn.close()

async def main():
    """Main initialization function."""
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        sys.exit(1)
    
    try:
        await create_database_schema(database_url)
        logger.info("🎉 Database initialization completed!")
    except Exception as e:
        logger.error(f"💥 Database initialization failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())