#!/bin/bash

# Smart Campus ML Pipeline Verification Script
# Tests all components of the ML pipeline end-to-end

echo "================================================"
echo "Smart Campus ML Pipeline Verification"
echo "================================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_info() { echo -e "ℹ $1"; }

PASSED=0
FAILED=0

# Test 1: Check if services are running
echo "Test 1: Service Status"
echo "----------------------"
services=("campus-mlflow" "campus-ml-prediction" "campus-ml-training" "campus-ml-inference")
for service in "${services[@]}"; do
    if docker ps | grep -q "$service"; then
        print_success "$service is running"
        ((PASSED++))
    else
        print_error "$service is NOT running"
        ((FAILED++))
    fi
done
echo ""

# Test 2: Prediction service health
echo "Test 2: Prediction Service Health"
echo "----------------------------------"
health_response=$(curl -s http://localhost:8001/health 2>/dev/null)
if [ $? -eq 0 ]; then
    print_success "Prediction service is reachable"
    ((PASSED++))
    
    if echo "$health_response" | grep -q '"status":"healthy"'; then
        print_success "Service reports healthy status"
        ((PASSED++))
    else
        print_error "Service is not healthy"
        ((FAILED++))
    fi
    
    echo "Response: $health_response" | python3 -m json.tool 2>/dev/null || echo "$health_response"
else
    print_error "Cannot reach prediction service"
    ((FAILED++))
fi
echo ""

# Test 3: Models loaded
echo "Test 3: Model Loading"
echo "---------------------"
models_response=$(curl -s http://localhost:8001/models 2>/dev/null)
if [ $? -eq 0 ]; then
    print_success "Models endpoint is reachable"
    ((PASSED++))
    
    if echo "$models_response" | grep -q '"canteen"'; then
        print_success "Canteen model is loaded"
        ((PASSED++))
    else
        print_warning "Canteen model not loaded (may need to train and promote)"
        ((FAILED++))
    fi
    
    if echo "$models_response" | grep -q '"library"'; then
        print_success "Library model is loaded"
        ((PASSED++))
    else
        print_warning "Library model not loaded (may need to train and promote)"
        ((FAILED++))
    fi
    
    echo "Loaded models:"
    echo "$models_response" | python3 -m json.tool 2>/dev/null || echo "$models_response"
else
    print_error "Cannot reach models endpoint"
    ((FAILED++))
fi
echo ""

# Test 4: MLflow connectivity
echo "Test 4: MLflow Connectivity"
echo "---------------------------"
mlflow_response=$(curl -s http://localhost:5000/health 2>/dev/null)
if [ $? -eq 0 ]; then
    print_success "MLflow is reachable"
    ((PASSED++))
else
    print_error "Cannot reach MLflow"
    ((FAILED++))
fi
echo ""

# Test 5: API predictions endpoint
echo "Test 5: API Predictions Endpoint"
echo "---------------------------------"
api_health=$(curl -s http://localhost:8000/predictions/health 2>/dev/null)
if [ $? -eq 0 ]; then
    print_success "API predictions endpoint is reachable"
    ((PASSED++))
else
    print_warning "API predictions endpoint not reachable (API may not be running)"
    ((FAILED++))
fi
echo ""

# Test 6: Test prediction request (if models are loaded)
echo "Test 6: Test Prediction Request"
echo "--------------------------------"
if echo "$models_response" | grep -q '"canteen"'; then
    test_payload='{
        "room_id": "test_canteen",
        "room_type": "canteen",
        "building_id": "B001",
        "timestamp": "2025-01-15T14:30:00",
        "avg": 45.5,
        "capacity": 100,
        "history": [40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87],
        "context": {
            "is_weekend": 0,
            "is_holiday": 0,
            "lecture_scale": 1.0
        }
    }'
    
    pred_response=$(curl -s -X POST http://localhost:8001/predict/congestion \
        -H "Content-Type: application/json" \
        -d "$test_payload" 2>/dev/null)
    
    if [ $? -eq 0 ] && echo "$pred_response" | grep -q '"predicted_avg"'; then
        print_success "Prediction request successful"
        ((PASSED++))
        echo "Prediction response:"
        echo "$pred_response" | python3 -m json.tool 2>/dev/null || echo "$pred_response"
    else
        print_error "Prediction request failed"
        echo "Response: $pred_response"
        ((FAILED++))
    fi
else
    print_warning "Skipping prediction test (models not loaded)"
fi
echo ""

# Test 7: Check Flink job status
echo "Test 7: Flink Job Status"
echo "------------------------"
if docker ps | grep -q "flink-jobmanager"; then
    print_success "Flink JobManager is running"
    ((PASSED++))
    
    # Check if prediction job is running
    flink_jobs=$(docker exec flink-jobmanager ./bin/flink list 2>/dev/null || echo "")
    if echo "$flink_jobs" | grep -q "Congestion Prediction"; then
        print_success "Prediction job is running"
        ((PASSED++))
    else
        print_warning "Prediction job not running (may need to submit)"
        echo "Submit with: docker exec flink-jobmanager ./bin/flink run -py /opt/flink/jobs/prediction.py -pyexec /usr/local/bin/python3"
    fi
else
    print_error "Flink JobManager is not running"
    ((FAILED++))
fi
echo ""

# Test 8: Check Airflow DAGs
echo "Test 8: Airflow DAGs"
echo "--------------------"
if docker ps | grep -q "campus-airflow-webserver"; then
    print_success "Airflow webserver is running"
    ((PASSED++))
    
    # Check if DAGs are loaded
    dags=$(docker exec campus-airflow-webserver airflow dags list 2>/dev/null || echo "")
    if echo "$dags" | grep -q "ml_training"; then
        print_success "ML training DAG is loaded"
        ((PASSED++))
    else
        print_warning "ML training DAG not found"
    fi
    
    if echo "$dags" | grep -q "ml_energy_batch_inference"; then
        print_success "ML inference DAG is loaded"
        ((PASSED++))
    else
        print_warning "ML inference DAG not found"
    fi
else
    print_warning "Airflow webserver is not running"
fi
echo ""

# Summary
echo "================================================"
echo "Verification Summary"
echo "================================================"
echo ""
print_success "Passed: $PASSED tests"
if [ $FAILED -gt 0 ]; then
    print_error "Failed: $FAILED tests"
else
    print_success "Failed: 0 tests"
fi
echo ""

# Overall status
if [ $FAILED -eq 0 ]; then
    print_success "All critical tests passed! ✓"
    echo ""
    echo "Your ML pipeline is ready to use."
    echo ""
    echo "Next steps:"
    echo "1. Monitor predictions: docker logs -f campus-ml-prediction"
    echo "2. View MLflow UI: http://localhost:5000"
    echo "3. View API docs: http://localhost:8000/docs"
    exit 0
else
    print_warning "Some tests failed. Review the output above."
    echo ""
    echo "Common fixes:"
    echo "1. Train models: ./scripts/train_ml_models.sh"
    echo "2. Promote models in MLflow UI: http://localhost:5000"
    echo "3. Restart services: docker-compose restart ml-prediction"
    echo "4. Check logs: docker logs campus-ml-prediction"
    exit 1
fi
