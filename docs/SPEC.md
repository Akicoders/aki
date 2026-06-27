# AgentOS MemoryAgent — Technical Specification

**Track:** MemoryAgent
**Hackathon:** Qwen Cloud Global AI Hackathon 2026
**Repo:** https://github.com/akidev/qwen-hackathon-memory-agent

---

## 1. Problem Statement

Desarrolladores y usuarios técnicos pierden contexto valioso entre sesiones:
- Preferencias de proyecto (package manager, linting, convenciones)
- Decisiones de arquitectura tomadas días/semanas atrás
- Contexto de código relevante para la tarea actual
- Historial de errores y soluciones

Las herramientas actuales (ChatGPT, Claude, etc.) no mantienen memoria persistente cross-session ni se integran con el workflow real del desarrollador (git, terminal, n8n, deploy).

---

## 2. Solution: AgentOS MemoryAgent

Un agente personal que **recuerda todo** entre sesiones y **ejecuta acciones reales** en tu entorno de desarrollo.

### 2.1 Core Value Proposition

| Antes (sin memoria) | Después (AgentOS) |
|---|---|
| "¿Cómo instalamos deps en ERP-AI?" → explicas cada vez | "En ERP-AI usás pnpm" → agente ejecuta `pnpm install` |
| "¿Cuál era la decisión sobre auth?" → buscas en logs/Notion | Agente recupera: "Decidimos JWT + refresh tokens, 2024-03-15" |
| Cambias de terminal → pierdes contexto | Memoria persiste: WhatsApp, Telegram, voz, terminal |

### 2.2 Target User

Paul — desarrollador full-stack en Perú, usa:
- **OS:** Arch Linux + Hyprland
- **Editor:** Neovim (LazyVim)
- **Terminal:** zsh + Powerlevel10k
- **Containers:** Docker, Docker Compose
- **Cloud:** AWS, Alibaba Cloud
- **Automation:** n8n (self-hosted)
- **Messaging:** WhatsApp (Baileys), Telegram
- **Voice:** faster-whisper + edge-tts + mpv
- **Projects:** ERP-AI (tesis), Gustos de Sabores, Sistema Ventas Online

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
                        AGENTOS CORE LOOP
└─────────────────────────────────────────────────────────────────┘
  Ingest → Retrieve → Reason → Act → Memorize
    │         │          │       │        │
    ▼         ▼          ▼       ▼        ▼
┌───────┐ ┌───────┐ ┌─────────┐ ┌─────┐ ┌────────┐
│ Voice │ │ Vector │ │ Qwen    │ │Skills│ │ Engram │
│ Text  │ │ Search │ │ Cloud   │ │      │ │ + SQL  │
│ WA/TG │ │Keyword │ │ Function│ │ 6    │ │ChromaDB│
└───────┘ └───────┘ └─────────┘ └─────┘ └────────┘
```

### 3.1 Data Flow

1. **Ingest**: Usuario envía mensaje (voz/texto/WhatsApp/Telegram)
2. **Embed**: Generar embedding del input
3. **Retrieve**: Búsqueda híbrida (vector + keyword + filtros) en memoria
4. **Context Assembly**: Armar prompt con facts + events recientes + skills
5. **Reason**: Qwen Cloud API con function calling
6. **Act**: Ejecutar skills (git, fs, web, n8n, scheduler, code_intel)
7. **Memorize**: Guardar decisiones, preferencias, outcomes como eventos/facts

---

## 4. Memory Model

### 4.1 Three-Tier Memory

| Tier | Purpose | Storage | TTL |
|---|---|---|---|
| **Episodic** | Eventos crudos: qué pasó, cuándo, quién | SQLite + ChromaDB | Permanente |
| **Semantic** | Hechos consolidados: key=value, confidence | SQLite | Permanente |
| **Procedural** | Skills registradas: qué herramientas existen | SQLite | Permanente |

### 4.2 Schema

```sql
-- Episodic events
memory_events:
  id PK, type, project, content, meta(JSON), embedding(JSON),
  timestamp, source, session_id

-- Semantic facts
memory_facts:
  id PK, key, value, scope, confidence, source_event_id FK,
  created_at, updated_at, access_count, last_accessed

-- Skills
skills:
  name PK, description, functions(JSON), enabled, config(JSON)
```

### 4.3 Consolidation Process

- **Trigger**: Cada 24h o cuando eventos > 10k por proyecto
- **Process**: LLM extrae facts de eventos antiguos (USER_PREFERENCE, DECISION)
- **Result**: Facts con confidence, eventos originales marcados como consolidados

---

## 5. Qwen Cloud Integration

### 5.1 API Usage

| Feature | Endpoint | Purpose |
|---|---|---|
| Chat | `/chat/completions` | Reasoning + function calling |
| Embeddings | `/embeddings` | Vector search |
| Streaming | `/chat/completions` (stream) | UX responsiva |

### 5.2 Models

- **Chat:** `qwen-max` (function calling, 32k context)
- **Embeddings:** `text-embedding-v3` (1536 dims, multilingual)

### 5.3 Function Calling Schema

Auto-generado desde skills registradas:
```json
{
  "name": "git_ops_status",
  "description": "Get git status",
  "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}
}
```

---

## 6. Skills (MVP: 6)

| Skill | Functions | Use Cases |
|---|---|---|
| **git_ops** | status, diff, commit, push, log, branch | Git workflow sin salir del chat |
| **filesystem** | read, write, append, delete, list, glob, search | Operaciones de archivos seguras |
| **web_search** | search, extract, summarize | Investigación técnica |
| **n8n_trigger** | trigger_workflow, get_status, list_workflows | Automatización real |
| **scheduler** | add_reminder, list, cancel, cron | Recordatorios y jobs recurrentes |
| **code_intel** | find_symbol, grep_ast, run_tests, lint, coverage | Análisis de código |

### 6.1 Security Model

- **Filesystem:** Solo paths bajo `~/proyectos`, `~/Documents` (configurable)
- **Git:** No auto-commit por defecto, confirma antes de push
- **n8n:** API key en env var, solo workflows permitidos

---

## 7. Interfaces

### 7.1 CLI (Primary)

```bash
agentos chat "recordá que en ERP-AI usamos pnpm"
agentos chat "cómo instalamos deps?" --project ERP-AI
agentos interactive --project ERP-AI
agentos recall "package manager" --project ERP-AI
agentos facts --project ERP-AI
agentos skills
```

### 7.2 WhatsApp Bridge

- Baileys (7.0.0-rc13) → webhook → AgentOS.chat()
- Respuesta de voz opcional (edge-tts)

### 7.3 Telegram Bot

- python-telegram-bot → webhook → AgentOS.chat()

### 7.4 Voice (Local)

- Hotkey (Hyprland) → faster-whisper STT → AgentOS → edge-tts → mpv

### 7.5 REST API (Optional)

```
POST /api/v1/chat       # Chat
GET  /api/v1/memory     # Query memory
POST /api/v1/remember   # Store fact
GET  /api/v1/skills     # List skills
GET  /health            # Health check
```

---

## 8. Deployment

### 8.1 Local Development

```bash
make install
make dev
```

### 8.2 Docker (Local)

```bash
make docker-run
```

### 8.3 Production (Alibaba Cloud)

```bash
# Build & push
make docker-build-prod
docker tag agentos-memory:latest registry.cn-hangzhou.aliyuncs.com/agentos-memory:v1.0.0
docker push registry.cn-hangzhou.aliyuncs.com/agentos-memory:v1.0.0

# Deploy
ssh root@server "cd /opt/agentos && docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d"
```

### 8.4 Infrastructure

| Component | Alibaba Cloud Service |
|---|---|
| Compute | ECS (2 vCPU, 4GB RAM) |
| Registry | Container Registry (ACR) |
| Database | SQLite en volumen persistente (ECS disk) |
| Vector DB | ChromaDB local (mismo contenedor) |
| Logs | SLS (Log Service) |
| Monitoring | ARMS / Prometheus |
| SSL | Alibaba Cloud Certificate Manager |

---

## 9. Demo Script (5 min)

| Time | Segment |
|---|---|
| 0:00-0:30 | **Problem**: "Pierdo contexto entre sesiones" |
| 0:30-1:30 | **Demo 1 - Terminal**: `agentos chat "en ERP-AI usamos pnpm"` → `agentos chat "cómo instalamos deps?"` |
| 1:30-2:30 | **Demo 2 - WhatsApp**: Mensaje de voz → respuesta con memoria |
| 2:30-3:30 | **Demo 3 - Skill real**: "creá branch feature/auth y hacé commit" → git_ops ejecuta |
| 3:30-4:15 | **Demo 4 - n8n**: "dispará workflow deploy-staging" → muestra ejecución |
| 4:15-5:00 | **Arquitectura + Memoria**: Diagrama + "esto persiste entre reinicios" |

---

## 10. Evaluation Criteria Mapping

| Hackathon Criteria | AgentOS Approach |
|---|---|
| **Innovation** | Memoria híbrida (episódica + semántica + procedimental) + skills reales |
| **Technical Depth** | Vector search + keyword + function calling + consolidation pipeline |
| **User Experience** | Multi-canal (terminal, WA, TG, voz) + streaming + CLI rico |
| **Qwen Cloud Usage** | Chat + embeddings + function calling nativo |
| **Alibaba Cloud Deploy** | ECS + ACR + SLS + ARMS + SSL |
| **Business Value** | Productividad real para desarrolladores, no demo de juguete |

---

## 11. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Qwen API rate limits | Media | Alto | Retry exponencial, cache embeddings, fallback local |
| ChromaDB memory usage | Baja | Media | Límites de colección, purga eventos consolidados |
| Skills security | Media | Alto | Allowlist paths, confirmaciones, sandbox opcional |
| Consolidation quality | Media | Media | Prompt engineering, human-in-the-loop para facts críticos |
| Demo failure | Baja | Alto | Script ensayado, fallback a video pregrabado |

---

## 12. Timeline (14 Days)

Ver `PLAN_14_DAYS.md`