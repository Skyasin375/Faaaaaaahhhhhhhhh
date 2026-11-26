# RBC GLORY Panel

RBC GLORY dashboard and bot service. The web interface is served from `templates/index.html`.

## Run

Install dependencies with `pip install -r requirements.txt`, then start the service using the configured process command.

## Project files

- `app.py` — bot service and account workers
- `dashboard_server.py` — HTTP dashboard and API
- `templates/index.html` — RBC GLORY frontend
- `br_evo_game.py`, `message_ids.py`, `thunderFF_pb2.py` — supporting game-service modules

Keep account JSON files and environment secrets private. The dashboard has no in-app login, so restrict access to the hosting endpoint using your deployment/network controls.
