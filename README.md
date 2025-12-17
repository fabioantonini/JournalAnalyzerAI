# JournalAnalyzerAI
Streamlit-based incident analysis tool for journalctl logs.
Uploads a systemd journal export, filters events by target services, and uses an OpenAI-powered two-pass analysis to reconstruct timelines, detect anomalies, propose root-cause hypotheses, and generate a Jira-ready technical summary.
Supports OPENAI_API_KEY from environment with optional UI override.
