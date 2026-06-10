# 📚 LLMNotes

A **NotebookLM clone** built with **Python Dash** that lets you add resources (notes) and ask AI-powered questions about them using **OpenRouter** models.

## ✨ Features

- **📄 Multi-format note ingestion**: Upload Markdown, PDF, images (OCR), or paste text directly
- **🔄 Auto-conversion**: All resources are converted to Markdown with dated filenames (originals preserved in `sources/`)
- **📝 Markdown + LaTeX rendering**: View notes with full markdown formatting and math equations
- **🧠 AI Question Answering**: Search → Explore → Conclude loop using OpenRouter models
- **💾 Offline-first storage**: SQLite database with all notes stored locally
- **🔒 Privacy**: Your API key stays on your machine

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install dash dash-bootstrap-components pandas pdfminer.six Pillow pytesseract python-magic markdown requests

# 2. Set your OpenRouter API key
export OPENROUTER_API_KEY="sk-or-v1-..."

# (Optional) Choose models
export OPENROUTER_MODEL="anthropic/claude-3.5-sonnet"     # For final answers
export OPENROUTER_QUICK_MODEL="openai/gpt-4o-mini"         # For exploration

# 3. Run the app
python3 app.py

# 4. Open http://127.0.0.1:8050 in your browser
```

## 📖 Usage

### Adding Notes

| Method | How |
|--------|-----|
| **Upload** | Drag & drop or browse: `.md`, `.pdf`, `.png`, `.jpg`, `.gif`, `.bmp` |
| **Paste** | Type or paste text content directly, optionally with a title |
| **OCR** | Images are automatically OCR'd (requires `tesseract` installed) |

All uploaded files are:
1. Copied to `sources/` (original preserved)
2. Converted to Markdown with a dated filename: `YYYYMMDD_title.md`
3. Stored in `notes/` and indexed in SQLite

### Asking Questions

1. Type your question in the "Ask about your notes" input
2. The AI agent runs a **Search → Explore → Conclude** loop:
   - **🔍 Search**: Finds relevant notes via keyword matching
   - **🔎 Explore**: Analyzes the notes content for answers
   - **💡 Conclude**: Synthesizes a final markdown-formatted answer
3. Click suggestion buttons for quick questions

### Viewing Notes

- Browse all notes in the main panel
- Click **View** to see full note content with Markdown + LaTeX rendering
- Click **Delete** to remove notes

## 🏗 Architecture

```
LLMNotes/
├── app.py              # Dash UI (sidebar + main content)
├── config.py           # Paths & configuration
├── database.py         # SQLite database layer
├── utils/
│   ├── converters.py   # File conversion & text chunking
│   └── ai_agent.py     # Search → Explore → Conclude agent
├── notes/              # Converted Markdown notes
├── sources/            # Original uploaded files
└── storage/            # SQLite database
```

## 🔧 Configuration

Via environment variables:
- `OPENROUTER_API_KEY` - Your OpenRouter API key (also settable in UI)
- `OPENROUTER_MODEL` - Model for final answers (default: `anthropic/claude-3.5-sonnet`)
- `OPENROUTER_QUICK_MODEL` - Model for exploration phase (default: `openai/gpt-4o-mini`)

## 📋 Requirements

- Python 3.10+
- OpenRouter API key (free tier available at https://openrouter.ai)
- For OCR: `tesseract-ocr` system package (`apt install tesseract-ocr` on Linux)

## 🧪 Tech Stack

| Component | Technology |
|-----------|-----------|
| UI Framework | Dash + Bootstrap 5 |
| Database | SQLite3 |
| AI Backend | OpenRouter API |
| Markdown | Python `markdown` library |
| PDF Parsing | `pdfminer.six` |
| OCR | `pytesseract` + `Pillow` |