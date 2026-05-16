#!/bin/bash
set -e

# Smart Campus ML Pipeline Deployment Script
# This script deploys the updated ML pipeline with the new prediction service

echo "================================================"
echo "Smart Campus ML Pipeline Deployment"
echo "================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "ℹ $1"
}

# Pre-deploy quality gates (lint + unit tests)
run_quality_gates() {
    if [ "${SKIP_QUALITY_GATES:-0}" = "1" ]; then
        print_warning "Skipping quality gates (SKIP_QUALITY_GATES=1)"
        return
    fi

    if ! command -v make > /dev/null 2>&1; then
        print_error "'make' is required to run lint/test quality gates."
        print_info "Install make or run with SKIP_QUALITY_GATES=1"
        exit 1
    fi

    echo ""
    print_info "Step 0: Running lint checks..."
    if make lint; then
        print_success "Lint checks passed"
    else
        print_error "Lint checks failed. Fix issues before deployment."
        exit 1
    fi

    echo ""
    print_info "Step 0b: Running unit tests..."
    if make test; then
        print_success "Unit tests passed"
    else
        print_error "Unit tests failed. Fix tests before deployment."
        exit 1
    fi
}

# Check if docker is running
if ! docker info > /dev/null 2>&1; then
    print_error "Docker is not running. Please start Docker and try again."
    exit 1
fi

print_success "Docker is running"

# Step 0: quality gates
run_quality_gates

# Step 1: Build services
echo ""
print_info "Step 1: Building services..."
docker-compose build ml-prediction
print_success "ML Prediction service built"

docker-compose build flink-jobmanager flink-taskmanager
print_success "Flink services rebuilt"

# Step 2: Start services
echo ""
print_info "Step 2: Starting services..."
docker-compose up -d mlflow influxdb postgres kafka
sleep 10
print_success "Core services started"

docker-compose up -d ml-prediction
sleep 5
print_success "ML Prediction service started"

# Step 3: Check prediction service health
echo ""
print_info "Step 3: Checking prediction service health..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if curl -s http://localhost:8001/health > /dev/null 2>&1; then
        print_success "Prediction service is healthy"
        break
    fi
    attempt=$((attempt + 1))
    echo -n "."
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    print_error "Prediction service failed to start. Check logs with: docker logs campus-ml-prediction"
    exit 1
fi

# Step 4: Check if models are loaded
echo ""
print_info "Step 4: Checking loaded models..."
models_response=$(curl -s http://localhost:8001/models)
echo "$models_response" | python3 -m json.tool

if echo "$models_response" | grep -q '"models"'; then
    print_success "Models endpoint is working"
else
    print_warning "Models may not be loaded yet. This is normal on first run."
    print_info "You need to train and promote models to Production in MLflow"
fi

# Step 5: Start Flink
echo ""
print_info "Step 5: Starting Flink cluster..."
docker-compose up -d flink-jobmanager flink-taskmanager
sleep 10
print_success "Flink cluster started"

# Step 6: Display status
echo ""
echo "================================================"
echo "Deployment Status"
echo "================================================"
echo ""

# Check service status
services=("campus-mlflow" "campus-ml-prediction" "flink-jobmanager" "flink-taskmanager")
for service in "${services[@]}"; do
    if docker ps | grep -q "$service"; then
        print_success "$service is running"
    else
        print_error "$service is not running"
    fi
done

# Display URLs
echo ""
echo "================================================"
echo "Service URLs"
echo "================================================"
echo ""
echo "MLflow UI:           http://localhost:5000"
echo "Prediction Service:  http://localhost:8001"
echo "Prediction Health:   http://localhost:8001/health"
echo "Prediction Models:   http://localhost:8001/models"
echo "Flink UI:            http://localhost:8081"
echo "API Docs:            http://localhost:8000/docs"
echo ""

# Next steps
echo "================================================"
echo "Next Steps"
echo "================================================"
echo ""
echo "1. Train models (if not done yet):"
echo "   ./scripts/train_ml_models.sh"
echo ""
echo "2. Promote models to Production in MLflow UI:"
echo "   http://localhost:5000"
echo ""
echo "3. Submit Flink prediction job:"
echo "   docker exec flink-jobmanager ./bin/flink run \\"
echo "     -py /opt/flink/jobs/prediction.py \\"
echo "     -pyexec /usr/local/bin/python3"
echo ""
echo "4. Monitor logs:"
echo "   docker logs -f campus-ml-prediction"
echo "   docker logs -f flink-taskmanager"
echo ""
echo "5. Test prediction API:"
echo "   curl http://localhost:8001/health"
echo ""

print_success "Deployment complete!"
