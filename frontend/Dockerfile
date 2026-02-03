FROM node:18-slim AS builder

# Set environment variables to help with optional dependencies
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV CYPRESS_INSTALL_BINARY=0

# Build-time Vite envs (must be set before npm run build)
ARG VITE_API_BASE_URL=/api
ARG VITE_LDAP_ENABLED=on
ARG VITE_PERSIST_ACCESS_TOKEN=true
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_LDAP_ENABLED=${VITE_LDAP_ENABLED}
ENV VITE_PERSIST_ACCESS_TOKEN=${VITE_PERSIST_ACCESS_TOKEN}

WORKDIR /app

# Configure npm for better reliability
RUN npm config set fetch-retry-mintimeout 20000 && \
    npm config set fetch-retry-maxtimeout 120000 && \
    npm config set fetch-retries 3 && \
    npm config set audit-level moderate && \
    npm cache clean --force

# Copy package files
COPY package.json package-lock.json ./

# Install all dependencies including devDependencies (needed for TypeScript and build tools)
RUN rm -rf node_modules && \
    npm ci --include=dev --include=optional --legacy-peer-deps --verbose || \
    (echo "First install attempt failed, retrying with npm install..." && \
     rm -rf node_modules package-lock.json && \
     npm install --legacy-peer-deps --verbose)

# Verify critical build tools are installed
RUN npx tsc --version && \
    npx vite --version && \
    echo "Build tools verified successfully"

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Run stage
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY entrypoint.sh /entrypoint.sh
COPY nginx.conf /etc/nginx/nginx.conf
COPY default.conf /etc/nginx/conf.d/default.conf

RUN chmod +x /entrypoint.sh

EXPOSE 80
CMD ["/entrypoint.sh"]
