# Research Webhook Guide

## ¿Qué es un webhook?

Un webhook es una forma de recibir datos automáticamente cuando un evento específico ocurre. En este caso, cuando una investigación (research) se completa, el sistema enviará automáticamente los resultados a una URL que tú especifiques.

## ¿Cómo funciona?

1. **Crear Research con Callback**: Envías un request para crear una investigación incluyendo `callback_enabled: true` y `callback_url`
2. **Sistema Procesa**: El sistema ejecuta la investigación en background
3. **Callback Automático**: Cuando termina, envía automáticamente los resultados a tu URL

## Ejemplo de Request con Webhook

```bash
curl -X POST "http://localhost:8000/research/" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Latest trends in artificial intelligence 2024",
    "directory_path": "research/ai-trends-2024",
    "llm_provider": "openai",
    "llm_model": "gpt-4o-mini",
    "perplexity_model": "sonar-pro",
    "max_planning_tasks": 5,
    "callback_enabled": true,
    "callback_url": "http://localhost:8000/research/webhook/test-callback",
    "callback_data": {
      "user_id": "12345",
      "project_id": "ai-research-2024"
    }
  }'
```

## Payload del Callback

Cuando la investigación se complete, recibirás un POST request en tu `callback_url` con este payload:

```json
{
  "research_id": 24,
  "query": "Latest trends in artificial intelligence 2024",
  "status": "completed",
  "directory_path": "research/ai-trends-2024",
  "created_at": "2024-06-28T23:50:52.123456Z",
  "completed_at": "2024-06-28T23:51:03.668474Z",
  "llm_provider": "openai",
  "llm_model": "gpt-4o-mini",
  "perplexity_model": "sonar-pro",
  "research_content": "Research Query: Latest trends in artificial intelligence 2024\nTotal Tasks: 1\nCompleted Tasks: 1\n\nCompleted Research Tasks:\n1. Research task 1\n   File: research/a97b2fa2-7b3c-4a0f-a2f6-ff1f0edb9af9/0eb9c5d1-bdad-4568-be07-c0f614da2e05/20250628_235102_task_01_Research_task_1.md",
  "research_files": [
    "research/a97b2fa2-7b3c-4a0f-a2f6-ff1f0edb9af9/0eb9c5d1-bdad-4568-be07-c0f614da2e05/20250628_235102_task_01_Research_task_1.md"
  ],
  "tasks": [
    {
      "id": 123,
      "task_query": "Research task 1",
      "task_order": 1,
      "status": "completed",
      "minio_file_path": "research/a97b2fa2-7b3c-4a0f-a2f6-ff1f0edb9af9/0eb9c5d1-bdad-4568-be07-c0f614da2e05/20250628_235102_task_01_Research_task_1.md",
      "completed_at": "2024-06-28T23:51:02.796147Z"
    }
  ],
  "user_id": "12345",
  "project_id": "ai-research-2024"
}
```

## Endpoint de Prueba

Para probar el webhook, puedes usar nuestro endpoint de prueba:

```
POST http://localhost:8000/research/webhook/test-callback
```

Este endpoint:
- Recibe el callback
- Lo registra en los logs
- Devuelve una confirmación

## Tu Endpoint de Callback

Tu endpoint debe:

1. **Aceptar POST requests** con JSON payload
2. **Responder con status 200** para confirmar recepción
3. **Procesar la información** según tus necesidades

Ejemplo de endpoint en Python/FastAPI:

```python
@app.post("/webhook/research-completed")
async def receive_research_callback(payload: dict):
    # Procesar los resultados
    research_id = payload.get("research_id")
    status = payload.get("status")
    files = payload.get("research_files", [])
    
    # Tu lógica aquí
    print(f"Research {research_id} completed with status: {status}")
    print(f"Generated files: {files}")
    
    # Responder con 200
    return {"status": "received", "message": "Callback processed successfully"}
```

## Solución de Problemas

### Callback no llega

1. **Verifica la URL**: Asegúrate que `callback_url` sea accesible
2. **Verifica el puerto**: Si usas `localhost`, asegúrate que el servicio esté corriendo
3. **Revisa los logs**: Busca mensajes de error sobre el callback
4. **Prueba la conectividad**: Haz un request manual a tu endpoint

### Status incorrecto

- El callback ahora se envía DESPUÉS de actualizar el status en la base de datos
- Deberías recibir `status: "completed"` o `status: "failed"`

### Callback duplicado

- Se envía solo una vez por investigación
- El sistema marca `callback_sent: true` después del envío exitoso

## Logs Relevantes

Busca estos logs para debugging:

```
📞 Sending callback after research completion
✅ Callback sent successfully for research X
⚠️ Failed to send callback for research X
❌ Error sending callback for research X
``` 