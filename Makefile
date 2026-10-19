.PHONY: install run run-ui run-frontend test test-frontend samples clean

install:
	python -m pip install -r requirements.txt

# REST backend (FastAPI). Open http://localhost:8000/docs for interactive docs.
run:
	uvicorn api.main:app --reload

# Optional local UI (Streamlit). The primary frontend is the React app in frontend/.
run-ui:
	streamlit run app/main.py

# React web app (frontend/). Requires Node 22.12+ and the backend running (`make run`).
run-frontend:
	cd frontend && npm run dev

test:
	python -m pytest tests/ -v

test-frontend:
	cd frontend && npm test

# Regenerate sample_output/ from synthetic evidence.
samples:
	python scripts/make_sample_output.py

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache generated
