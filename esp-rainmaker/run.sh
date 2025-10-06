#!/usr/bin/with-contenv bashio

# Get configuration from Home Assistant
ESP_RAINMAKER_EMAIL=$(bashio::config 'email')
ESP_RAINMAKER_PASSWORD=$(bashio::config 'password')
ESP_RAINMAKER_PROFILE=$(bashio::config 'profile')
RAINMAKER_API_PORT=$(bashio::config 'api_port')

# Export environment variables
export ESP_RAINMAKER_EMAIL
export ESP_RAINMAKER_PASSWORD
export ESP_RAINMAKER_PROFILE
export RAINMAKER_API_PORT

# Create rainmaker data directory
mkdir -p /data/rainmaker
mkdir -p /root/.espressif

# Link to expected location
if [ ! -L "/root/.espressif/rainmaker" ]; then
    ln -sf /data/rainmaker /root/.espressif/rainmaker
fi

# Check if port is available
if netstat -tuln | grep -q ":${RAINMAKER_API_PORT} "; then
    bashio::log.warning "Port ${RAINMAKER_API_PORT} appears to be in use. Attempting to start anyway..."
fi

bashio::log.info "Starting ESP RainMaker addon..."
bashio::log.info "Email: ${ESP_RAINMAKER_EMAIL}"
bashio::log.info "Profile: ${ESP_RAINMAKER_PROFILE}"
bashio::log.info "API Port: ${RAINMAKER_API_PORT}"

# Start the server with proper signal handling
exec python3 /app/server.py
