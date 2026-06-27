# 14-Day Execution Plan — Qwen Cloud Hackathon

**Start:** 2026-06-11 (Mié) | **Deadline:** 2026-07-09 (Jue) 23:59 UTC
**Track:** MemoryAgent | **Repo:** qwen-hackathon-memory-agent

---

## Semana 1: Foundation (Días 1-7)

### Día 1 — Mié 11 Jun — **Kickoff & Scaffold** ✓
- [x] Decidir track: **MemoryAgent**
- [x] Idea: **AgentOS Personal** (memoria cross-session + skills reales)
- [x] Repo creado: `qwen-hackathon-memory-agent`
- [x] Scaffold completo: pyproject.toml, config.yaml, Docker, CI, Makefile
- [x] Core modules: config, memory (models, DB, repo), Qwen client, skills base + 6 skills, agent loop, CLI
- [x] Tests unitarios + integración
- [x] Docs: SPEC.md, README.md

**Entregable:** Repo funcional con `make install && make dev` corriendo

---

### Día 2 — Jue 12 Jun — **Qwen Integration & Memory Polish**
- [ ] Configurar Qwen API key real en `.env`
- [ ] Probar `agentos chat` con Qwen Cloud (chat + embeddings)
- [ ] Verificar function calling con skills registradas
- [ ] Pulir memory retrieval: hybrid search scoring, context assembly tokens
- [ ] Agregar métricas básicas: latencia, tokens, recall
- [ ] Test end-to-end: user input → embed → retrieve → reason → act → memorize

**Entregable:** AgentOS responde usando Qwen + memoria + al menos 1 skill

---

### Día 3 — Vie 13 Jun — **WhatsApp Bridge Integration**
- [ ] Conectar Baileys bridge existente (`~/.hermes/scripts/whatsapp-bridge`) a AgentOS
- [ ] Webhook: WhatsApp → `/api/v1/chat` → AgentOS → respuesta
- [ ] Soporte voz: audio → faster-whisper → AgentOS → edge-tts → audio reply
- [ ] Session management: mantener `session_id` por chat de WhatsApp
- [ ] Probar: "recordá X" en WhatsApp → "qué te dije?" en terminal

**Entregable:** Memoria compartida entre terminal ↔ WhatsApp

---

### Día 4 — Sáb 14 Jun — **Telegram + Voice (Local)**
- [ ] Bot de Telegram con python-telegram-bot
- [ ] Mismo webhook pattern que WhatsApp
- [ ] Hotkey Hyprland (Super+B) → faster-whisper → AgentOS → edge-tts → mpv
- [ ] UI minimal status modal (12s auto-close + Esc) como pediste
- [ ] Probar flujo completo voz → agente → voz

**Entregable:** 4 canales funcionando: terminal, WhatsApp, Telegram, voz local

---

### Día 5 — Dom 15 Jun — **Skills Hardening & Real-World Testing**
- [ ] git_ops: test en ERP-AI real (status, diff, commit, push, PR)
- [ ] filesystem: test read/write/search en proyectos reales
- [ ] web_search: test DuckDGo HTML scraping + extract
- [ ] n8n_trigger: conectar a tu n8n local, disparar workflow real
- [ ] scheduler: recordatorios persistentes cross-session
- [ ] code_intel: find_symbol, run_tests, lint en ERP-AI
- [ ] Fix bugs, edge cases, errores de permisos/paths

**Entregable:** 6 skills probadas en proyectos reales sin mocks

---

### Día 6 — Lun 16 Jun — **Consolidation Pipeline & Observability**
- [ ] Implementar `consolidate_project()`: LLM extrae facts de eventos antiguos
- [ ] Programar cron job diario (24h) para consolidación
- [ ] Logging estructurado (JSON): requests, tool calls, latencias, errores
- [ ] Health endpoint: `/health` → DB, ChromaDB, Qwen API, skills
- [ ] Métricas Prometheus: `agentos_requests_total`, `agentos_latency_seconds`, `agentos_memory_events`

**Entregable:** Memoria se auto-organiza; observabilidad lista para producción

---

### Día 7 — Mar 17 Jun — **Midpoint Review & Demo Interno**
- [ ] **Demo interno completo** (5 min) grabando pantalla
- [ ] Checklist de arquitectura vs SPEC.md
- [ ] Identificar gaps críticos para Semana 2
- [ ] Ajustar scope si necesario (cortar features no esenciales)
- [ ] Commit: `feat: midpoint - core loop + 6 skills + 4 channels working`

**Entregable:** Demo interno funcionando; plan ajustado para Semana 2

---

## Semana 2: Polish & Deploy (Días 8-14)

### Día 8 — Mié 18 Jun — **Testing & CI/CD**
- [ ] Tests unitarios > 80% coverage (memory, skills, config)
- [ ] Tests de integración: memory repo, agent loop, Qwen client
- [ ] GitHub Actions: lint + typecheck + test + build + push to ACR
- [ ] Configurar secrets en GitHub: QWEN_API_KEY, ALIYUN_REGISTRY_*, STAGING_*
- [ ] Verificar pipeline completo: push → CI → deploy staging

**Entregable:** CI/CD verde; deploy automático a staging en Alibaba Cloud

---

### Día 9 — Jue 19 Jun — **Production Deploy & Hardening**
- [ ] Provision ECS en Alibaba Cloud (2 vCPU, 4GB, Ubuntu 22.04)
- [ ] Configurar ACR, SSL cert, dominion (ej: `agentos.tu-dominio.com`)
- [ ] Deploy con `docker-compose.prod.yml`
- [ ] Verificar health checks, logs en SLS, métricas en ARMS
- [ ] Load test básico: 10 requests concurrentes, medir P95 < 3s
- [ ] Backup strategy: snapshot EBS diario + export DB semanal

**Entregable:** AgentOS corriendo en producción con HTTPS, logs, métricas

---

### Día 10 — Vie 20 Jun — **Demo Script & Recording**
- [ ] Escribir script final de 5 min (ver SPEC.md §9)
- [ ] Ensayar 3-5 veces, cronometrar
- [ ] Grabar en 1080p/60fps (OBS o similar)
- [ ] Editar: cortes limpios, subtítulos en español, zoom en terminal
- [ ] Subir a YouTube (unlisted) + Google Drive backup

**Entregable:** Video demo ≤ 5 min, listo para submission

---

### Día 11 — Sáb 21 Jun — **Deck (10 Slides) + README Polish**
- [ ] Slide 1: Title + Team (Paul + Anahi)
- [ ] Slide 2: Problem (contexto perdido = productividad perdida)
- [ ] Slide 3: Solution (AgentOS: memoria + acción)
- [ ] Slide 4: Architecture diagram
- [ ] Slide 5: Memory model (episódica/semántica/procedimental)
- [ ] Slide 6: Demo highlights (4 canales, 6 skills)
- [ ] Slide 7: Qwen Cloud usage (chat + embeddings + function calling)
- [ ] Slide 8: Alibaba Cloud deploy (ECS + ACR + SLS + ARMS)
- [ ] Slide 9: Roadmap (multi-user, plugins, marketplace)
- [ ] Slide 10: Ask + Contact
- [ ] Exportar PDF + PNGs
- [ ] README: GIFs demo, badges, quick start, arquitectura ASCII

**Entregable:** Deck PDF + README listo para Devpost

---

### Día 12 — Dom 22 Jun — **Blog Post + Submission Prep**
- [ ] Escribir blog post técnico (para Blog Post Winner $1k):
  - "Building a Persistent Memory Agent with Qwen Cloud"
  - Arquitectura, código clave, lecciones aprendidas
  - ~2000 palabras, English + Spanish
- [ ] Publicar en dev.to / medium / personal blog
- [ ] Revisar Devpost submission form: todos los campos
- [ ] Preparar screenshots/GIFs para Devpost gallery

**Entregable:** Blog post publicado; assets Devpost listos

---

### Día 13 — Lun 23 Jun — **Submit Early! (No esperar al día 9 Jul)**
- [ ] Submit en Devpost:
  - Repo URL
  - Video URL (YouTube)
  - Deck PDF
  - Descripción completa
  - Tags: `memoryagent`, `qwen-cloud`, `alibaba-cloud`
- [ ] Verificar: repo público, video accessible, deck descargable
- [ ] Compartir en redes (LinkedIn, X, Discord communities) para visibilidad

**Entregable:** **SUBMITTED** 🎉

---

### Día 14 — Mar 24 Jun — **Buffer & Celebrate**
- [ ] Buffer para fixes de último minuto si Devpost pide cambios
- [ ] Responder preguntas de jueces si contactan
- [ ] Documentar lessons learned en `RETROSPECTIVE.md`
- [ ] Planear siguientes features (post-hackathon)
- [ ] **Celebrar** 🍻

---

## Daily Rituals (Every Day)

| Time | Activity |
|---|---|
| 08:00 | Review yesterday's commit, plan today |
| 08:30-12:30 | Deep work (no notifications) |
| 12:30 | Almuerzo + caminar |
| 13:30-18:00 | Deep work / calls / pairing |
| 18:00 | Gym / Marinera / descanso |
| 20:00 | Light review: tests, commit, push |
| 22:00 | Sleep |

---

## Risk Buffer

| Risk | Buffer Day |
|---|---|
| Qwen API issues | Día 2-3 |
| WhatsApp bridge breaks | Día 3-4 |
| Deploy Alibaba Cloud fails | Día 9-10 |
| Demo recording issues | Día 10-11 |
| Devpost submission bugs | Día 13 |

**Regla:** Si algo toma > 4h sin progreso → escalar, pedir ayuda, o cortar feature.

---

## Success Metrics

| Metric | Target |
|---|---|
| Memory recall accuracy | > 90% en queries reales |
| End-to-end latency (P95) | < 3s |
| Skills success rate | > 95% |
| Demo video views (first week) | > 500 |
| Devpost completeness | 100% fields filled |
| Blog post reads | > 200 |

---

## Post-Hackathon Roadmap (Ideas)

- Multi-user support (familias, equipos)
- Plugin marketplace para skills
- Web dashboard (React + WebSocket)
- Mobile app (React Native / Flutter)
- Fine-tuned embedding modelo para código
- Integración con Obsidian (tu vault)
- Shared memory entre agentes (Agent Society)