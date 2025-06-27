#!/bin/bash

# Build ARM64 images locally on Mac for PyExec
# This is much faster than QEMU emulation in CI

set -e

REGISTRY="ghcr.io"
OWNER="kacperkwapisz"
PROJECT="pyexec"

# Version can be supplied as first argument or detected from git
VERSION_TAG="${1:-}"
# If no version specified, try to get it from git tags
if [ -z "$VERSION_TAG" ]; then
    VERSION_TAG=$(git describe --tags --exact-match 2>/dev/null || echo "dev")
fi
# Add -arm64 suffix if not already there
if [[ ! "$VERSION_TAG" =~ -arm64$ ]]; then
    VERSION_TAG="${VERSION_TAG}-arm64"
fi

# Always update latest-arm64 tag as well
LATEST_TAG="latest-arm64"

# Image names with version tags
BASE_IMAGE="${REGISTRY}/${OWNER}/${PROJECT}/pyexec-base:${VERSION_TAG}"
MAIN_IMAGE="${REGISTRY}/${OWNER}/${PROJECT}/pyexec:${VERSION_TAG}"

# Image names with latest tags
BASE_IMAGE_LATEST="${REGISTRY}/${OWNER}/${PROJECT}/pyexec-base:${LATEST_TAG}"
MAIN_IMAGE_LATEST="${REGISTRY}/${OWNER}/${PROJECT}/pyexec:${LATEST_TAG}"

# Build arguments
VERSION="${VERSION:-$(git describe --tags --exact-match 2>/dev/null || echo "dev")}"
COMMIT="${COMMIT:-$(git rev-parse HEAD)}"
BUILD_DATE="${BUILD_DATE:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# Cleanup function
cleanup() {
    echo -e "${YELLOW}🧹 Cleaning up temporary files...${NC}"
    
    # Optionally remove local Docker images to save space
    if [ "${KEEP_LOCAL_IMAGE}" != "true" ]; then
        echo -e "${YELLOW}🗑️  Removing local Docker images to save disk space...${NC}"
        docker rmi "${BASE_IMAGE}" 2>/dev/null || echo -e "${YELLOW}   ⚠️  Base versioned image not found${NC}"
        docker rmi "${MAIN_IMAGE}" 2>/dev/null || echo -e "${YELLOW}   ⚠️  Main versioned image not found${NC}"
        docker rmi "${BASE_IMAGE_LATEST}" 2>/dev/null || echo -e "${YELLOW}   ⚠️  Base latest image not found${NC}"
        docker rmi "${MAIN_IMAGE_LATEST}" 2>/dev/null || echo -e "${YELLOW}   ⚠️  Main latest image not found${NC}"
    else
        echo -e "${BLUE}📦 Keeping local Docker images (KEEP_LOCAL_IMAGE=true)${NC}"
    fi
    
    echo -e "${GREEN}✨ Cleanup completed!${NC}"
}

# Trap to ensure cleanup runs even if script fails
trap cleanup EXIT

echo -e "${BLUE}🍎 Building PyExec ARM64 images natively on Mac...${NC}"
echo -e "${BLUE}📦 Building both images in sequence:${NC}"
echo -e "${BLUE}   1. Base: ${BASE_IMAGE}${NC}"
echo -e "${BLUE}   2. Main: ${MAIN_IMAGE}${NC}"
echo -e "${BLUE}   (Both images will also be tagged as ${LATEST_TAG})${NC}"
echo -e "${YELLOW}💡 Tip: Set KEEP_LOCAL_IMAGE=true to keep the local images after push${NC}"
echo ""
echo -e "${BLUE}📋 Build Information:${NC}"
echo -e "   Version Tag: ${VERSION_TAG}"
echo -e "   Git Version: ${VERSION}"
echo -e "   Commit:      ${COMMIT}"
echo -e "   Date:        ${BUILD_DATE}"
echo ""

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running. Please start Docker Desktop.${NC}"
    exit 1
fi

# Check if logged in to registry
echo -e "${YELLOW}🔐 Checking registry authentication...${NC}"
if ! docker system info | grep -q "Username:"; then
    echo -e "${YELLOW}⚠️  You may need to login to GitHub Container Registry:${NC}"
    echo -e "${BLUE}   docker login ghcr.io -u ${OWNER}${NC}"
    echo ""
fi

# Verify we're on ARM64 Mac for optimal build speed
ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
    echo -e "${YELLOW}⚠️  Warning: Not running on ARM64 Mac. Build may be slower.${NC}"
    echo -e "${YELLOW}   Current architecture: ${ARCH}${NC}"
fi

# Step 1: Build base image
echo -e "${YELLOW}🔨 Step 1/2: Building base image with native ARM64...${NC}"
docker build \
    --platform linux/arm64 \
    --build-arg VERSION="${VERSION}" \
    --build-arg COMMIT="${COMMIT}" \
    --build-arg BUILD_DATE="${BUILD_DATE}" \
    -t "${BASE_IMAGE}" \
    -f Dockerfile.base \
    .

# Also tag as latest
echo -e "${YELLOW}   Tagging base image as ${LATEST_TAG}...${NC}"
docker tag "${BASE_IMAGE}" "${BASE_IMAGE_LATEST}"

# Test the built base image
echo -e "${YELLOW}🧪 Base image validation...${NC}"
BASE_SIZE=$(docker images "${BASE_IMAGE}" --format "{{.Size}}" | head -n 1)
echo -e "${GREEN}   ✓ Base image built successfully (${BASE_SIZE})${NC}"

# Step 2: Build main image
echo -e "${YELLOW}🔨 Step 2/2: Building main image with native ARM64...${NC}"
docker build \
    --platform linux/arm64 \
    --build-arg VERSION="${VERSION}" \
    --build-arg COMMIT="${COMMIT}" \
    --build-arg BUILD_DATE="${BUILD_DATE}" \
    --build-arg BASE_IMAGE="${BASE_IMAGE}" \
    -t "${MAIN_IMAGE}" \
    -f Dockerfile \
    .

# Also tag as latest
echo -e "${YELLOW}   Tagging main image as ${LATEST_TAG}...${NC}"
docker tag "${MAIN_IMAGE}" "${MAIN_IMAGE_LATEST}"

# Test the built main image
echo -e "${YELLOW}🧪 Main image validation...${NC}"
MAIN_SIZE=$(docker images "${MAIN_IMAGE}" --format "{{.Size}}" | head -n 1)
echo -e "${GREEN}   ✓ Main image built successfully (${MAIN_SIZE})${NC}"

# Show image details
echo -e "${BLUE}📊 Image Details:${NC}"
docker images | grep "${PROJECT}" | sort

# Push images
echo -e "${YELLOW}🚀 Pushing images to registry...${NC}"
echo -e "${YELLOW}   Pushing base image (version tag)...${NC}"
docker push "${BASE_IMAGE}"

echo -e "${YELLOW}   Pushing base image (latest tag)...${NC}"
docker push "${BASE_IMAGE_LATEST}"

echo -e "${YELLOW}   Pushing main image (version tag)...${NC}"
docker push "${MAIN_IMAGE}"

echo -e "${YELLOW}   Pushing main image (latest tag)...${NC}"
docker push "${MAIN_IMAGE_LATEST}"

echo ""
echo -e "${GREEN}✅ ARM64 images built and pushed successfully!${NC}"
echo -e "${GREEN}🎯 Version-tagged images:${NC}"
echo -e "   Base: ${BASE_IMAGE}"
echo -e "   Main: ${MAIN_IMAGE}"
echo -e "${GREEN}🎯 Latest-tagged images:${NC}"
echo -e "   Base: ${BASE_IMAGE_LATEST}"
echo -e "   Main: ${MAIN_IMAGE_LATEST}"
echo ""
echo -e "${BLUE}📋 Usage Examples:${NC}"
echo -e "${BLUE}   # Run PyExec (latest):${NC}"
echo -e "   docker run -p 8080:8080 -v ./.env:/app/.env ${MAIN_IMAGE_LATEST}"
echo ""
echo -e "${BLUE}   # Run PyExec (specific version):${NC}"
echo -e "   docker run -p 8080:8080 -v ./.env:/app/.env ${MAIN_IMAGE}"
echo ""
echo -e "${BLUE}   # Use in deploy script:${NC}"
echo -e "   BASE_IMAGE=\"${BASE_IMAGE}\" MAIN_IMAGE=\"${MAIN_IMAGE}\" ./deploy.sh"
echo ""
echo -e "${BLUE}🔧 Performance Benefits:${NC}"
echo -e "${GREEN}   ✓ Native ARM64 build (no emulation)${NC}"
echo -e "${GREEN}   ✓ Much faster than CI QEMU builds${NC}"
echo -e "${GREEN}   ✓ Optimized for Apple Silicon${NC}"
echo ""
echo -e "${YELLOW}💡 Script Usage:${NC}"
echo -e "   ./build-local-arm64.sh [version]"
echo -e "   - If [version] is omitted, git tags will be used"
echo -e "   - '-arm64' suffix will be added automatically if needed"
echo ""
echo -e "${YELLOW}💡 Pro tip: You can now test ARM64-specific issues locally!${NC}" 