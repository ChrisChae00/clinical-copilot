# Ollama Setup

Clinical Ally uses [Ollama](https://ollama.com) to run the LLM locally. All inference happens on your machine — no data leaves localhost.

---

## Install Ollama

**macOS (Homebrew)**
```bash
brew install ollama
```

**Linux**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows**
Download the installer from https://ollama.com/download and run it.

---

## Pull the model

```bash
ollama pull llama3
```

This downloads ~4 GB. Run it once; the model is cached for future sessions.

---

## Start Ollama

On macOS/Linux, Ollama starts automatically after install. To start it manually:
```bash
ollama serve
```

Ollama listens on `http://localhost:11434` by default.

---

## Verify

**Interactive chat**
```bash
ollama run llama3 "Hello, can you hear me?"
```

**REST API**
```bash
curl -s -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3","prompt":"Hello","stream":false}' \
  | python3 -m json.tool
```

Expected: JSON with a `"response"` field containing the model's reply.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `connection refused` on port 11434 | Run `ollama serve` in a terminal and keep it open |
| `model not found` error | Run `ollama pull llama3` again |
| Very slow responses | Normal on CPU — first token can take 10–30 s. GPU acceleration speeds this up significantly. |
| High RAM usage | llama3 (8B) needs ~6 GB RAM. Use `ollama pull llama3:8b-instruct-q4_0` for a smaller quantization. |
| macOS: Ollama won't start | Check System Settings → Privacy & Security for blocked software |

---

## Available models

You can swap the model by editing `MODEL` in `llm-proxy/main.py`:

```python
MODEL = "llama3"          # default — good balance
MODEL = "mistral"         # faster, slightly less accurate
MODEL = "medllama2"       # fine-tuned on medical text (larger download)
```

Run `ollama list` to see models already downloaded.
