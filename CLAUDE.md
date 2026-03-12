# Weave

## Project Overview
Streamlit app deployed to Streamlit Cloud from the `rsanandres/weave` GitHub repo.

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
- `.gitignore` excludes: `venv/`, `.env`, `data/`, `__pycache__/`, `.streamlit/secrets.toml`

## Development
- Run locally: `streamlit run <app_file>.py`
- Load env vars with `python-dotenv` or `st.secrets` for cloud
