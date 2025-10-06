ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.19
FROM $BUILD_FROM

# Install build dependencies and Python packages
RUN apk update && \
    apk add --no-cache \
        python3 \
        py3-pip \
        bash \
        gcc \
        musl-dev \
        libffi-dev \
        openssl-dev \
        python3-dev \
        rust \
        cargo && \
    ln -sf python3 /usr/bin/python

# Install Python packages with --break-system-packages for Alpine 3.19+
RUN python3 -m pip install --no-cache-dir --break-system-packages \
    esp-rainmaker-cli \
    flask

# Clean up build dependencies to reduce image size
RUN apk del gcc musl-dev libffi-dev openssl-dev python3-dev rust cargo

# Set working directory
WORKDIR /app

# Copy server files
COPY run.sh server.py /app/
RUN chmod a+x /app/run.sh

# Start the application directly
CMD ["/app/run.sh"]