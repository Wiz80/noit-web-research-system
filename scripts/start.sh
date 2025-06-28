#!/bin/bash

# Script de inicio para el sistema de investigación web
# Desarrollo - InfinityLab Research Team

set -e

echo "🚀 Starting Web Research Multi-Agent System..."

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Función para imprimir mensajes coloreados
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verificar si Python está instalado
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed. Please install Python 3.11 or higher."
    exit 1
fi

# Verificar versión de Python
PYTHON_VERSION=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
print_status "Python version: $PYTHON_VERSION"

# Verificar si el entorno virtual existe
if [ ! -d "venv" ]; then
    print_warning "Virtual environment not found. Creating one..."
    python3 -m venv venv
    print_status "Virtual environment created successfully."
fi

# Activar entorno virtual
print_status "Activating virtual environment..."
source venv/bin/activate

# Verificar si requirements.txt existe e instalar dependencias
if [ -f "requirements.txt" ]; then
    print_status "Installing/updating dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
else
    print_error "requirements.txt not found!"
    exit 1
fi

# Verificar archivo .env
if [ ! -f ".env" ]; then
    if [ -f "env.example" ]; then
        print_warning ".env file not found. Copying from env.example..."
        cp env.example .env
        print_warning "Please edit .env file with your API keys and configuration."
    else
        print_error ".env file not found and no env.example available!"
        exit 1
    fi
fi

# Verificar servicios de Docker Compose
print_status "Checking Docker Compose services..."

if command -v docker-compose &> /dev/null; then
    # Verificar si PostgreSQL está corriendo
    if ! docker-compose ps postgres | grep -q "Up"; then
        print_status "Starting PostgreSQL..."
        docker-compose up -d postgres
        sleep 5
    fi

    # Verificar si MinIO está corriendo
    if ! docker-compose ps minio | grep -q "Up"; then
        print_status "Starting MinIO..."
        docker-compose up -d minio
        sleep 3
    fi
    
    print_status "Infrastructure services are running."
else
    print_warning "Docker Compose not found. Make sure PostgreSQL and MinIO are running manually."
fi

# Verificar conexión a base de datos y ejecutar migraciones
print_status "Setting up database..."

# Verificar si Alembic está configurado
if [ ! -d "alembic" ]; then
    print_warning "Alembic not initialized. Initializing..."
    alembic init alembic
fi

# Ejecutar migraciones
print_status "Running database migrations..."
alembic upgrade head

# Verificar configuración de MinIO
print_status "Checking MinIO configuration..."
python3 -c "
from app.services.minio_service import minio_service
try:
    # Test MinIO connection
    minio_service._ensure_bucket_exists()
    print('✅ MinIO connection successful')
except Exception as e:
    print(f'❌ MinIO connection failed: {e}')
"

# Verificar API keys
print_status "Checking API key configuration..."
python3 -c "
from app.config import settings
import sys

issues = []

if not settings.perplexity_api_key:
    issues.append('PERPLEXITY_API_KEY not set')

if not any([settings.openai_api_key, settings.anthropic_api_key, 
           settings.google_api_key, settings.deepseek_api_key]):
    issues.append('No LLM API keys configured')

if issues:
    print('⚠️  Configuration issues:')
    for issue in issues:
        print(f'   - {issue}')
    print('Please check your .env file')
else:
    print('✅ API configuration looks good')
"

# Obtener host y puerto de configuración
export PYTHONPATH=$PWD
HOST=$(python3 -c "from app.config import settings; print(settings.api_host)")
PORT=$(python3 -c "from app.config import settings; print(settings.api_port)")

print_status "Starting FastAPI application..."
print_status "Server will be available at: http://$HOST:$PORT"
print_status "API Documentation: http://$HOST:$PORT/docs"
print_status "Health Check: http://$HOST:$PORT/health"

echo
echo "🎯 System Information:"
echo "   - Environment: $(python3 -c "from app.config import settings; print(settings.app_env)")"
echo "   - Log Level: $(python3 -c "from app.config import settings; print(settings.log_level)")"
echo "   - Database: PostgreSQL"
echo "   - Storage: MinIO"
echo "   - LLM Providers: OpenAI, Anthropic, Google, DeepSeek"
echo "   - Research API: Perplexity"
echo

echo "🚀 Launching Web Research System..."
echo "   Press Ctrl+C to stop"
echo

# Ejecutar la aplicación
uvicorn app.main:app --host $HOST --port $PORT --reload 