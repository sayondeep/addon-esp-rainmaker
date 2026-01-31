#!/bin/bash

# Script to create multi-arch manifest from architecture-specific tags
# Usage: ./create-manifest.sh [version]
# Example: ./create-manifest.sh 0.0.1

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

# Read version from config.yaml or use provided argument
if [ -n "$1" ]; then
    VERSION="$1"
else
    VERSION=$(extract_version)
    if [ -z "$VERSION" ]; then
        echo "❌ Could not extract version from config.yaml. Please provide version as argument."
        exit 1
    fi
fi

IMAGE_NAME="sayondeep/esp-rainmaker-addon"

echo "🔗 Creating multi-arch manifest for version $VERSION"
echo "   Image: ${IMAGE_NAME}:${VERSION}"
echo ""

# Read supported architectures from config.yaml
if command -v yq &> /dev/null; then
    ARCHS=$(yq eval '.arch[]' config.yaml)
elif command -v python3 &> /dev/null; then
    ARCHS=$(python3 -c "import yaml; print('\n'.join(yaml.safe_load(open('config.yaml'))['arch']))")
else
    # Fallback: use grep
    ARCHS=$(grep -A 10 "^arch:" config.yaml | grep "  -" | sed 's/  - //')
fi

if [ -z "$ARCHS" ]; then
    echo "❌ Could not read architectures from config.yaml"
    exit 1
fi

# Build list of architecture-specific tags
TAG_LIST=""
for ARCH in $ARCHS; do
    TAG_LIST="${TAG_LIST} ${IMAGE_NAME}:${ARCH}-${VERSION}"
done

echo "   Combining tags:${TAG_LIST}"
echo ""

# Create multi-arch manifest
docker buildx imagetools create \
  --tag "${IMAGE_NAME}:${VERSION}" \
  ${TAG_LIST}

echo ""
echo "✅ Multi-arch manifest created: ${IMAGE_NAME}:${VERSION}"
echo ""
echo "   This tag now supports: $(echo $ARCHS | tr '\n' ' ')"
echo "   Docker will automatically pull the correct architecture for each platform."
