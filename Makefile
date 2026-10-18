.PHONY: install run run-ui test samples clean

install:
	python -m pip install -r requirements.txt

# REST backend (FastAPI). Open http://localhost:8000/docs for interactive docs.
run:
	uvicorn api.main:app --reload

# Optional local UI (Streamlit). The primary frontend is the Lovable React app.
run-ui:
	streamlit run app/main.py

test:
	python -m pytest tests/ -v

# Regenerate sample_output/ from synthetic evidence.
samples:
	python scripts/make_sample_output.py

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache generated
