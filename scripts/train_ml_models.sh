#!/bin/bash
set -e

# Smart Campus ML Model Training Script
# Trains all ML models (canteen, library, energy) and registers them in MLflow

echo "================================================"
echo "Smart Campus ML Model Training"
echo "================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

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

# Check if ml-training container is running
if ! docker ps | grep -q "campus-ml-training"; then
    print_error "ML training container is not running"
    print_info "Starting ml-training container..."
    docker-compose up -d ml-training
    sleep 5
fi

print_success "ML training container is running"

# Step 1: Generate datasets (if needed)
echo ""
print_info "Step 1: Checking for training datasets..."

if docker exec campus-ml-training test -f /opt/campus/ml/datasets/canteen_congestion_2024_2025.csv; then
    print_success "Datasets already exist"
else
    print_warning "Datasets not found. Generating..."
    docker exec campus-ml-training python /opt/campus/ml/generate_datasets.py
    print_success "Datasets generated"
fi

# Step 2: Train canteen congestion model
echo ""
print_info "Step 2: Training canteen congestion model..."
docker exec campus-ml-training bash -c \
    'cd /opt/campus/ml/kedro_project && \
     MLFLOW_TRACKING_URI=http://mlflow:5000 \
     python -W ignore -m kedro run --pipeline canteen_congestion'

if [ $? -eq 0 ]; then
    print_success "Canteen model trained successfully"
else
    print_error "Canteen model training failed"
    exit 1
fi

# Step 3: Train library congestion model
echo ""
print_info "Step 3: Training library congestion model..."
docker exec campus-ml-training bash -c \
    'cd /opt/campus/ml/kedro_project && \
     MLFLOW_TRACKING_URI=http://mlflow:5000 \
     python -W ignore -m kedro run --pipeline library_congestion'

if [ $? -eq 0 ]; then
    print_success "Library model trained successfully"
else
    print_error "Library model training failed"
    exit 1
fi

# Step 4: Train energy forecast model
echo ""
print_info "Step 4: Training energy forecast model..."
docker exec campus-ml-training bash -c \
    'cd /opt/campus/ml/kedro_project && \
     MLFLOW_TRACKING_URI=http://mlflow:5000 \
     python -W ignore -m kedro run --pipeline energy_forecast'

if [ $? -eq 0 ]; then
    print_success "Energy model trained successfully"
else
    print_error "Energy model training failed"
    exit 1
fi

# Step 5: Display results
echo ""
echo "================================================"
echo "Training Complete"
echo "================================================"
echo ""
print_success "All models trained successfully!"
echo ""
echo "Next steps:"
echo ""
echo "1. Open MLflow UI: http://localhost:5000"
echo ""
echo "2. Promote models to Production:"
echo "   - Navigate to 'Models' tab"
echo "   - For each model (campus_canteen_congestion, campus_library_congestion, campus_energy_forecast):"
echo "     • Click on the model name"
echo "     • Click on the latest version"
echo "     • Click 'Stage: None' → 'Transition to Production'"
echo ""
echo "3. Restart prediction service to load new models:"
echo "   docker-compose restart ml-prediction"
echo ""
echo "4. Verify models are loaded:"
echo "   curl http://localhost:8001/models"
echo ""

print_info "Training artifacts saved to ml/kedro_project/processed/ and ml/kedro_project/models/"
