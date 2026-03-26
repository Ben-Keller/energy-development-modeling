# EDIM MVP

Minimal single-user workbench for integrated energy-development scenario runs.

Full technical documentation is in:

- [SYSTEM_DOCUMENTATION.md](SYSTEM_DOCUMENTATION.md)

## Quickstart

### 1) Python version

Use Python `3.11`.

### 2) Backend setup

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
uvicorn api_service.main:app --reload --port 8000
```

### 3) Open the app

- `http://127.0.0.1:8000/ui/`

### 4) Queue a run

1. Select scenario and run profile.
2. Confirm **Environment setup** is ready.
3. Click **Queue run**.
4. Monitor status in the jobs panel.

### 5) Outputs

Run artifacts are written to:

- `outputs/runs/<run_id>/`

Main outputs include:

- `results.csv`
- `summary.json`
- `development_impacts.json`
- `integrated_results.json`
- `report.md`
- `exchange_bundle.zip`

## Useful commands

### Unit tests

```bash
cd backend
python -m unittest discover -s tests -p "test_*.py"
```

### Smoke checks

```bash
cd backend
source .venv/bin/activate
python tools/smoke_check.py
python tools/smoke_check.py --run-model
```

### Docker

```bash
docker compose up --build
```
