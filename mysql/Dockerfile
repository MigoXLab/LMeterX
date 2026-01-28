FROM mysql:5.7

# Set environment variables
# Note: These can be overridden via docker-compose or runtime environment variables
# For production, use secrets management instead of hardcoded values
ARG MYSQL_ROOT_PASSWORD_ARG=lmeterx123
ARG MYSQL_DATABASE_ARG=lmeterx
ENV MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD_ARG}
ENV MYSQL_DATABASE=${MYSQL_DATABASE_ARG}

# Copy initialization script
COPY ../init_db.sql /docker-entrypoint-initdb.d/

# Set MySQL configuration
CMD ["mysqld", "--default-authentication-plugin=mysql_native_password", "--character-set-server=utf8mb4", "--collation-server=utf8mb4_unicode_ci", "--init-connect=SET NAMES utf8mb4"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD mysqladmin ping -h localhost -u root -p$MYSQL_ROOT_PASSWORD || exit 1

# Expose port
EXPOSE 3306
