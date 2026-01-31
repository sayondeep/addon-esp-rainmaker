#!/bin/bash

# Build script that reads BUILD_FROM from build.yaml and version from config.yaml
# Auto-detects host platform if architecture not specified
# Usage: ./build.sh [architecture]
# Example: ./build.sh                    # Auto-detect platform, read version from config.yaml
# Example: ./build.sh amd64               # Build for specific platform, read version from config.yaml
# Example: ./build.sh aarch64             # Build for specific platform, read version from config.yaml

set -e

# Extract version from config.yaml
extract_version() {
    if command -v yq &> /dev/null; then
        yq eval ".version" config.yaml
    elif command -v python3 &> /dev/null; then
        python3 -c "import yaml; print(yaml.safe_load(open('config.yaml'))['version'])"
    else
        # Fallback: use grep and sed
        grep "^version:" config.yaml | sed 's/version: "\(.*\)"/\1/' | sed 's/version: \(.*\)/\1/'
    fi
}

# Auto-detect host architecture
detect_arch() {
    local host_arch=$(uname -m)
    case "$host_arch" in
        x86_64) echo "amd64" ;;
        aarch64|arm64) echo "aarch64" ;;
        armv7l) echo "armv7" ;;
        armv6l) echo "armhf" ;;
        i386|i686) echo "i386" ;;
        *) echo "unknown" ;;
    esac
}

# Read version from config.yaml
VERSION=$(extract_version)
if [ -z "$VERSION" ]; then
    echo "❌ Could not extract version from config.yaml"
    exit 1
fi

# Use provided architecture or auto-detect
if [ -n "$1" ] && [[ "$1" =~ ^(amd64|aarch64|armv7|armhf|i386)$ ]]; then
    ARCH="$1"
else
    # Auto-detect if no valid architecture provided
    ARCH=$(detect_arch)
    if [ "$ARCH" = "unknown" ]; then
        echo "❌ Could not auto-detect architecture. Please specify: amd64, aarch64, armv7, armhf, or i386"
        exit 1
    fi
fi

IMAGE_NAME="sayondeep/esp-rainmaker-addon"

# Map architecture names to docker platform names
declare -A PLATFORM_MAP=(
    ["amd64"]="linux/amd64"
    ["aarch64"]="linux/aarch64"
    ["armv7"]="linux/arm/v7"
    ["armhf"]="linux/arm/v6"
    ["i386"]="linux/386"
)

PLATFORM="${PLATFORM_MAP[$ARCH]}"

if [ -z "$PLATFORM" ]; then
    echo "❌ Unknown architecture: $ARCH"
    echo "Supported: amd64, aarch64, armv7, armhf, i386"
    exit 1
fi

# Extract BUILD_FROM from build.yaml using yq or grep/sed
if command -v yq &> /dev/null; then
    BUILD_FROM=$(yq eval ".build_from.$ARCH" build.yaml)
elif command -v python3 &> /dev/null; then
    BUILD_FROM=$(python3 -c "import yaml; print(yaml.safe_load(open('build.yaml'))['build_from']['$ARCH'])")
else
    # Fallback: use grep and sed (less reliable but works)
    BUILD_FROM=$(grep -A 10 "build_from:" build.yaml | grep "  $ARCH:" | sed 's/.*: "\(.*\)"/\1/')
fi

if [ -z "$BUILD_FROM" ]; then
    echo "❌ Could not extract BUILD_FROM for $ARCH from build.yaml"
    exit 1
fi

echo "🏗️  Building for $ARCH ($PLATFORM)"
echo "   Host platform: $(uname -m)"
echo "   Version: $VERSION (from config.yaml)"
echo "   Base image: $BUILD_FROM"
echo "   Tag: ${IMAGE_NAME}:${ARCH}-${VERSION}"
echo ""

docker buildx build \
  --platform "$PLATFORM" \
  --build-arg BUILD_FROM="$BUILD_FROM" \
  --tag "${IMAGE_NAME}:${ARCH}-${VERSION}" \
  --push \
  .

echo ""
echo "✅ Build completed: ${IMAGE_NAME}:${ARCH}-${VERSION}"
