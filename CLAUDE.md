# Weave

## Project Overview
Engineering Impact Dashboard — analyzes PostHog/posthog GitHub repo to identify the most impactful engineers over the last 90 days. Deployed to Streamlit Cloud from `rsanandres/weave`.

## Environment
- Python 3.11 (venv at `./venv/`)
- Key dependencies: `streamlit`, `anthropic`, `pandas`, `python-dotenv`
- Activate venv: `source venv/bin/activate`

## API Keys
- Stored locally in `.env` (gitignored)
- For Streamlit Cloud: add secrets via dashboard (Settings > Secrets) in TOML format
- Keys needed: `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`

## Deployment
- **Target**: Streamlit Cloud (public app)
- **Repo**: https://github.com/rsanandres/weave (public)
- **Branch**: `main`
- `requirements.txt` and `.python-version` are present for Streamlit Cloud compatibility
- `.gitignore` excludes: `venv/`, `.env`, `__pycache__/`, `.streamlit/`
- `data/` is committed (contains cached PR data and LLM summary)

## Development
- Run locally: `streamlit run app.py`
- Re-fetch data: `python fetch_data.py` (requires GITHUB_TOKEN in .env)
- Load env vars with `python-dotenv` or `st.secrets` for cloud
