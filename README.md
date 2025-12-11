# Clinical Trials Scout

![Showcase](showcase.png)

Chat with an LLM to search clinical trials from ClinicalTrials.gov. Ask questions in plain English, get results in a table.

## What it does

- Ask questions about clinical trials ("Find breast cancer trials in California")
- Get live data from ClinicalTrials.gov API
- Filter by condition, location, status, and phase automatically
- Save your chat history
- Works on mobile

## Built with

- FastAPI + PostgreSQL
- HTMX + Tailwind CSS
- Anthropic Claude (via litellm)
- Docker

## Run it

1. Clone the repo
```bash
git clone https://github.com/alexandru-tanul/clinical-trials-scout.git
cd clinical-trials-scout
```

2. Copy the example env file
```bash
cp .env.example .env
```

3. Add your Anthropic API key to `.env`

4. Start it
```bash
docker compose up -d
```

5. Open http://localhost:8000

## Required env variables

Put these in `.env`:
- `ANTHROPIC_API_KEY` - Get it from Anthropic
- `OPENAI_API_KEY` - Get it from OpenAI
- `SESSION_SECRET` - Any random string
- `POSTGRES_PASSWORD` - Pick a password

## Optional env variables

- `MODEL` - Which Claude model to use (default: `gpt-5-nano`)
- `DEBUG` - Turn on debug mode (default: `True`)

## How it works

Uses a state machine to track response generation:
- `pending` → `analyzing` → `tool_calling` → `synthesizing` → `completed`
- Status messages change based on how long each step takes
- Everything runs async so you can use the app while responses generate

## License

Free to use for learning and personal projects.
