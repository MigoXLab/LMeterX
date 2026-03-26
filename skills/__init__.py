"""
LMeterX Agent Skills — Thin MCP integration layer.

Core business logic lives in the backend service.
Skills call the following LMeterX backend APIs:
  - POST /api/skills/analyze-url     — Web URL analysis & loadtest config generation
  - POST /api/common-tasks/test      — API connectivity pre-check
  - POST /api/common-tasks           — Create loadtest tasks
  - GET  /api/common-tasks/{id}      — Get task details
  - GET  /api/common-tasks/{id}/results — Get performance results
"""

__version__ = "2.0.0"
