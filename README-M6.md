# M6 — SQLite persistence, HITL decisions, and FastAPI routes

See `docs/hitl-persistence-m6.md` for the API contract, PowerShell examples, checkpoint details, and security notes.

Run the app with:

```powershell
uvicorn app.main:app --reload
```

Swagger UI is available at `http://127.0.0.1:8000/docs`.

Run the M6 tests:

```powershell
pytest -v tests/test_api.py tests/test_checkpointer.py
```

Run the complete suite:

```powershell
pytest -v
```

M6 records approval durably at the write gate. The actual GitHub commit is a separate M7 milestone and is not claimed as complete here.
