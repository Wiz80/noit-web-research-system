# Web Research Multi-Agent System

Un sistema de investigación web profunda basado en agentes de IA utilizando CrewAI y Perplexity para realizar investigaciones comprehensivas y estructuradas.

## 🎯 Características Principales

- **Arquitectura Multi-Agente**: Dos agentes especializados trabajando en colaboración
- **Investigación Inteligente**: Evita duplicación revisando investigaciones previas
- **Múltiples Proveedores de LLM**: OpenAI, Anthropic, Google, DeepSeek
- **Investigación Web Avanzada**: Integración con Perplexity API para investigación en tiempo real
- **Almacenamiento Estructurado**: Resultados guardados en MinIO con trazabilidad completa
- **API REST Completa**: Operaciones CRUD para gestión de investigaciones
- **Base de Datos PostgreSQL**: Seguimiento completo de investigaciones y tareas

## 🏗️ Arquitectura del Sistema

### Flujo de Trabajo

1. **Agente Planificador de Investigación**:
   - Analiza la consulta de investigación
   - Busca investigaciones similares en MinIO
   - Determina si es necesaria nueva investigación
   - Crea estructura de investigación con tareas específicas

2. **Agente Ejecutor de Investigación**:
   - Ejecuta las tareas de investigación usando Perplexity API
   - Guarda los resultados en archivos Markdown en MinIO
   - Actualiza la base de datos con el progreso

3. **Sistema de Gestión**:
   - Rastrea todas las investigaciones y tareas
   - Proporciona API REST para operaciones CRUD
   - Mantiene estadísticas y métricas del sistema

### Modelos Soportados

#### Proveedores de LLM
- **OpenAI**: gpt-4o-mini (default), gpt-4o, gpt-4-turbo, gpt-3.5-turbo
- **Anthropic**: claude-3-haiku, claude-3-sonnet, claude-3-opus
- **Google**: gemini-1.5-flash, gemini-1.5-pro, gemini-pro
- **DeepSeek**: deepseek-chat, deepseek-coder

#### Modelos de Perplexity
- **sonar-pro** (default): Rendimiento balanceado y costo
- **sonar-deep-research**: Análisis profundo con investigación extensa
- **sonar-reasoning-pro**: Capacidades de razonamiento avanzado
- **sonar-reasoning**: Modelo de razonamiento estándar

## 🚀 Instalación y Configuración

### Prerrequisitos

- Python 3.11+
- PostgreSQL 15+
- MinIO o compatible S3
- API Keys requeridas

### 1. Clonar el Repositorio

```bash
git clone https://github.com/tu-usuario/noit-web-research-system.git
cd noit-web-research-system
```

### 2. Configurar Entorno Virtual

```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configurar Variables de Entorno

Copia el archivo de ejemplo y configura tus variables:

```bash
cp env.example .env
```

Edita `.env` con tus configuraciones:

```env
# Database Configuration
DATABASE_URL=postgresql://user:password@localhost:5432/web_research_db

# LLM API Keys
OPENAI_API_KEY=tu_openai_api_key
ANTHROPIC_API_KEY=tu_anthropic_api_key
GOOGLE_API_KEY=tu_google_api_key
DEEPSEEK_API_KEY=tu_deepseek_api_key

# Perplexity API
PERPLEXITY_API_KEY=tu_perplexity_api_key

# MinIO Configuration
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_NAME=research-storage
MINIO_SECURE=false
```

### 4. Configurar Servicios con Docker Compose

Para desarrollo rápido, usa Docker Compose para PostgreSQL y MinIO:

```bash
# Solo servicios de infraestructura
docker-compose up -d postgres minio

# Para incluir la aplicación también
docker-compose --profile full up -d
```

### 5. Configurar Base de Datos

```bash
# Inicializar Alembic
alembic init alembic

# Crear migración inicial
alembic revision --autogenerate -m "Initial migration"

# Ejecutar migraciones
alembic upgrade head
```

### 6. Ejecutar la Aplicación

```bash
# Desarrollo
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Producción
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 📖 Uso de la API

### Crear una Investigación

```bash
curl -X POST "http://localhost:8000/api/v1/research/" \
     -H "Content-Type: application/json" \
     -d '{
       "query": "Últimas tendencias en chatbots de IA 2024",
       "directory_path": "ai-research/chatbots",
       "llm_provider": "openai",
       "llm_model": "gpt-4o-mini",
       "perplexity_model": "sonar-pro"
     }'
```

### Obtener Resultados de Investigación

```bash
curl "http://localhost:8000/api/v1/research/1"
```

### Listar Investigaciones

```bash
# Todas las investigaciones
curl "http://localhost:8000/api/v1/research/"

# Con filtros
curl "http://localhost:8000/api/v1/research/?status=completed&limit=10"
```

### Buscar Investigaciones

```bash
curl "http://localhost:8000/api/v1/research/search/query?q=chatbots"
```

### Obtener Modelos Disponibles

```bash
curl "http://localhost:8000/api/v1/research/models/available"
```

### Estadísticas del Sistema

```bash
curl "http://localhost:8000/api/v1/research/statistics/overview"
```

## 🔧 Configuración Avanzada

### Configuración de LLMs

```python
# En tu archivo de configuración
LLM_CONFIGS = {
    "openai": {
        "default_model": "gpt-4o-mini",
        "temperature": 0.1,
        "max_tokens": 4000
    },
    "anthropic": {
        "default_model": "claude-3-haiku-20240307",
        "temperature": 0.1,
        "max_tokens": 4000
    }
}
```

### Configuración de Perplexity

```python
PERPLEXITY_CONFIGS = {
    "sonar-pro": {
        "max_tokens": 4000,
        "temperature": 0.1,
        "timeout": 120
    },
    "sonar-deep-research": {
        "max_tokens": 6000,
        "temperature": 0.05,
        "timeout": 180
    }
}
```

## 📊 Monitoreo y Logging

El sistema utiliza structured logging con las siguientes características:

- **Formato JSON**: Para fácil parsing y análisis
- **Request IDs**: Trazabilidad completa de requests
- **Métricas de Rendimiento**: Tiempo de ejecución de agentes
- **Health Checks**: Endpoints de salud para monitoreo

```bash
# Ver logs en tiempo real
tail -f logs/app.log | jq .

# Health check
curl http://localhost:8000/health
```

## 🧪 Testing

```bash
# Ejecutar tests
pytest

# Con cobertura
pytest --cov=app tests/

# Tests específicos
pytest tests/test_research_flow.py -v
```

## 🔒 Seguridad

### Mejores Prácticas

1. **Variables de Entorno**: Nunca hardcodear API keys
2. **Validación de Entrada**: Todas las entradas son validadas con Pydantic
3. **Rate Limiting**: Implementar limits en producción
4. **CORS**: Configurar apropiadamente para producción
5. **HTTPS**: Usar siempre en producción

### Configuración de Producción

```yaml
# docker-compose.prod.yml
services:
  web-research-api:
    environment:
      - APP_ENV=production
      - API_HOST=0.0.0.0
      - API_PORT=8000
    deploy:
      replicas: 3
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G
```

## 📁 Estructura del Proyecto

```
noit-web-research-system/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application
│   ├── config.py              # Configuration settings
│   ├── database.py            # Database connection
│   ├── models.py              # SQLAlchemy models
│   ├── schemas.py             # Pydantic schemas
│   ├── agents/                # CrewAI agents
│   │   ├── research_planner_agent.py
│   │   └── research_executor_agent.py
│   ├── api/                   # API routes
│   │   └── research_routes.py
│   ├── flows/                 # CrewAI flows
│   │   └── research_flow.py
│   └── services/              # Business logic services
│       ├── llm_service.py
│       ├── perplexity_service.py
│       ├── minio_service.py
│       └── research_service.py
├── alembic/                   # Database migrations
├── tests/                     # Test files
├── docker-compose.yml         # Development services
├── Dockerfile                 # Container definition
├── requirements.txt           # Python dependencies
├── alembic.ini               # Alembic configuration
└── README.md                 # Este archivo
```

## 🤝 Contribución

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto está licenciado bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para detalles.

## 📞 Soporte

- **Documentación**: `/docs` endpoint de la API
- **Issues**: GitHub Issues
- **Email**: research@infinitylab.com

## 🚧 Roadmap

- [ ] Integración con más APIs de investigación (Tavily, OpenAI Web Search)
- [ ] Dashboard web para gestión visual
- [ ] Sistema de templates de investigación
- [ ] API de webhooks para notificaciones
- [ ] Integración con sistemas de análisis de datos
- [ ] Soporte para investigación colaborativa
- [ ] Optimización de costos de API calls
- [ ] Sistema de cache inteligente
- [ ] Métricas avanzadas y analytics

---

**Desarrollado por InfinityLab Research Team** 🚀