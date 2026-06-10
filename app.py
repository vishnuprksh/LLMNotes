"""LLMNotes - A NotebookLM Clone with Dash"""

import base64
import io
import os
import tempfile
from datetime import datetime
import json

import dash
from dash import dcc, html, Input, Output, State, callback, no_update, MATCH, ALL
import dash_bootstrap_components as dbc
import markdown as md_lib
import re

from config import (
    OPENROUTER_API_KEY, BASE_DIR, NOTES_DIR,
    SUPPORTED_EXTENSIONS
)
from database import Database
from utils.converters import (
    convert_to_markdown, add_text_as_note,
    chunk_text, sanitize_filename
)
from utils.ai_agent import LLMNotesAgent

# Initialize
db = Database()
agent = LLMNotesAgent(db)

# Dash app
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css"],
    title="LLMNotes",
    suppress_callback_exceptions=True,
    update_title=None
)

server = app.server

# ─── Markdown + LaTeX Rendering ───────────────────────────────────────────────

def render_markdown_latex(text):
    """Render markdown with LaTeX support"""
    if not text:
        return ""

    blocks = []

    def store_block(m):
        blocks.append(m.group(0))
        return f"%%LATEXBLOCK{len(blocks)-1}%%"

    def store_inline(m):
        blocks.append(m.group(0))
        return f"%%LATEXINLINE{len(blocks)-1}%%"

    text_protected = re.sub(r'\$\$(.*?)\$\$', store_block, text, flags=re.DOTALL)
    text_protected = re.sub(r'(?<!\$)\$(?!\$)([^$\n]+?)(?<!\$)\$(?!\$)', store_inline, text_protected)

    html_content = md_lib.markdown(text_protected, extensions=['fenced_code', 'tables', 'codehilite'])

    for i, b in enumerate(blocks):
        if b.startswith('$$'):
            latex_html = f'<div class="latex-block">\\[{b[2:-2]}\\]</div>'
            html_content = html_content.replace(f"%%LATEXBLOCK{i}%%", latex_html)
        else:
            latex_html = f'<span class="latex-inline">\\({b[1:-1]}\\)</span>'
            html_content = html_content.replace(f"%%LATEXINLINE{i}%%", latex_html)

    return html_content


def note_card(note):
    """Create a note card component"""
    note_id = note["id"]
    title = note["title"]
    preview = note["content_preview"][:150] if note["content_preview"] else "No preview"
    created = note["created_at"][:10] if note["created_at"] else ""
    source_type = note["source_type"]

    type_icons = {
        "md": "bi-filetype-md",
        "pdf": "bi-filetype-pdf",
        "image": "bi-file-image",
        "txt": "bi-filetype-txt",
    }
    icon = type_icons.get(source_type, "bi-file-text")

    return html.Div([
        html.Div([
            html.I(className=f"bi {icon} me-2"),
            html.Span(title, className="fw-bold"),
        ], className="d-flex align-items-center mb-1"),
        html.Small(preview, className="text-muted d-block mb-1",
                   style={"display": "-webkit-box", "WebkitLineClamp": 2,
                          "WebkitBoxOrient": "vertical", "overflow": "hidden"}),
        html.Small(f"📅 {created}", className="text-muted"),
        html.Div([
            dbc.Button("View", color="primary", size="sm",
                       id={"type": "view-note", "index": note_id}, className="me-1"),
            dbc.Button("Delete", color="danger", size="sm",
                       id={"type": "del-note", "index": note_id}),
        ], className="mt-2 d-flex gap-1")
    ], className="note-card p-3 border rounded mb-2",
       style={"background": "#f8f9fa"})


# ─── Layout ───────────────────────────────────────────────────────────────────

sidebar = html.Div([
    html.H4(["📚 ", html.Span("LLMNotes", style={"fontWeight": 700})],
            className="text-center mb-4 mt-2"),
    html.Hr(),

    dbc.Label("OpenRouter API Key", className="fw-bold small"),
    dbc.Input(
        id="api-key-input",
        type="password",
        placeholder="sk-or-... (enter to set)",
        value=OPENROUTER_API_KEY,
        className="mb-3",
    ),

    dbc.Label("Model Selection", className="fw-bold small"),
    dbc.Select(
        id="model-select",
        options=[
            {"label": "DeepSeek V4 Flash", "value": "deepseek/deepseek-v4-flash"},
            {"label": "DeepSeek Chat", "value": "deepseek/deepseek-chat"},
            {"label": "Claude 3.5 Sonnet", "value": "anthropic/claude-3.5-sonnet"},
            {"label": "Claude 3 Haiku", "value": "anthropic/claude-3-haiku"},
            {"label": "GPT-4o", "value": "openai/gpt-4o"},
            {"label": "GPT-4o Mini", "value": "openai/gpt-4o-mini"},
        ],
        value="deepseek/deepseek-v4-flash",
        className="mb-3",
    ),

    html.H6("📄 Add Notes", className="fw-bold mt-3"),
    dbc.Tabs([
        dbc.Tab([
            html.Div([
                dbc.Label("Upload files", className="mt-2"),
                dcc.Upload(
                    id="upload-file",
                    children=html.Div([
                        "Drag & drop or ",
                        html.A("browse files", className="text-primary"),
                        html.Br(),
                        html.Small("MD, PDF, images", className="text-muted"),
                    ]),
                    style={
                        "border": "2px dashed #ccc", "borderRadius": "8px",
                        "padding": "30px 20px", "textAlign": "center",
                        "cursor": "pointer", "background": "#fafafa"
                    },
                    multiple=False,
                ),
            ]),
        ], label="Upload", tab_id="tab-upload"),

        dbc.Tab([
            html.Div([
                dbc.Label("Title (optional)", className="mt-2"),
                dbc.Input(id="pasted-title", placeholder="Note title", className="mb-2"),
                dbc.Label("Paste text content", className="fw-bold small"),
                dbc.Textarea(
                    id="pasted-text",
                    placeholder="Paste or type your notes here...",
                    style={"minHeight": "150px"},
                    className="mb-2",
                ),
                dbc.Button("Add Note", id="btn-add-text", color="success",
                           size="sm", className="w-100"),
            ]),
        ], label="Paste Text", tab_id="tab-paste"),
    ], id="input-tabs", active_tab="tab-upload"),

    html.Hr(),
    html.H6("💬 Ask Questions", className="fw-bold"),
    dbc.InputGroup([
        dbc.Input(id="question-input", placeholder="Ask about your notes...",
                  type="text"),
        dbc.Button("Ask", id="btn-ask", color="primary"),
    ], className="mb-2"),
    html.Div(id="suggestion-btns", className="d-flex flex-wrap gap-1 mt-1"),

    html.Hr(),
    html.Small([
        html.I(className="bi bi-info-circle me-1"),
        "Resources are converted to Markdown and stored locally.",
    ], className="text-muted d-block text-center"),
], style={
    "height": "100vh", "overflowY": "auto",
    "padding": "15px", "borderRight": "1px solid #dee2e6"
})

chat_panel_view = html.Div([
    html.H5("💬 Conversations", style={"fontWeight": 600}),
    html.Div(id="conversation-history", children=[]),
    html.Div(id="loading-output"),
])

note_viewer_view = html.Div([
    dbc.Button("← Back", id="btn-back-notes", color="secondary", size="sm", className="mb-2"),
    html.Div(id="note-content-display"),
])

main_content = html.Div([
    # Notes panel
    html.Div([
        html.H5("📝 My Notes", className="d-flex justify-content-between align-items-center mb-3",
                style={"fontWeight": 600}),
        html.Div(id="notes-list", children=[]),
    ], id="notes-panel", style={"display": "block"}),

    # Note viewer
    html.Div(note_viewer_view, id="note-viewer", style={"display": "none"}),

    # Chat panel
    html.Div(chat_panel_view, id="chat-panel", style={"display": "none"}),
], id="main-content", className="p-4")

app.layout = html.Div([
    dcc.Store(id="selected-note-id", storage_type="memory"),
    dcc.Store(id="current-view", data="notes", storage_type="memory"),
    dcc.Store(id="api-key-store", data=OPENROUTER_API_KEY, storage_type="local"),
    dcc.Store(id="model-store", data="deepseek/deepseek-v4-flash", storage_type="local"),
    dbc.Container([
        dbc.Row([
            dbc.Col(sidebar, width=3, style={"padding": "0"}),
            dbc.Col(main_content, width=9, style={"padding": "0"}),
        ], className="g-0"),
    ], fluid=True, style={"height": "100vh"}),
])


# ─── Callbacks ────────────────────────────────────────────────────────────────

@callback(
    Output("api-key-store", "data"),
    Input("api-key-input", "value"),
)
def update_api_key(key):
    if key:
        os.environ["OPENROUTER_API_KEY"] = key
        # Update agent session
        agent.session.headers.update({"Authorization": f"Bearer {key}"})
    return key or ""


@callback(
    Output("model-store", "data"),
    Input("model-select", "value"),
)
def update_model(model):
    if model:
        os.environ["OPENROUTER_MODEL"] = model
    return model or "deepseek/deepseek-v4-flash"



@callback(
    Output("notes-list", "children"),
    Input("current-view", "data"),
    Input("api-key-store", "data"),
)
def refresh_notes(view, _):
    notes = db.get_all_notes()
    if not notes:
        return html.Div([
            html.I(className="bi bi-inbox me-2"),
            "No notes yet. Upload or paste some content to get started!",
        ], className="text-muted text-center p-4")
    cards = [note_card(n) for n in notes]
    return cards


@callback(
    Output("current-view", "data"),
    Input("btn-back-notes", "n_clicks"),
    State("current-view", "data"),
    prevent_initial_call=True,
)
def go_back_to_notes(_, view):
    return "notes"


@callback(
    Output("selected-note-id", "data"),
    Input({"type": "view-note", "index": ALL}, "n_clicks"),
    State("current-view", "data"),
    prevent_initial_call=True,
)
def select_note(n_clicks, view):
    if not any(n_clicks):
        return no_update
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update
    trigger = ctx.triggered[0]
    if not trigger.get("value"):
        return no_update
    # Extract note ID from the trigger's id
    try:
        trigger_id = json.loads(trigger["prop_id"].split(".")[0])
        return trigger_id.get("index")
    except:
        return no_update


@callback(
    Output("notes-panel", "style"),
    Output("note-viewer", "style"),
    Output("chat-panel", "style"),
    Input("current-view", "data"),
)
def toggle_views(view):
    if view == "notes":
        return {"display": "block"}, {"display": "none"}, {"display": "none"}
    elif view == "note":
        return {"display": "none"}, {"display": "block"}, {"display": "none"}
    elif view == "chat":
        return {"display": "none"}, {"display": "none"}, {"display": "block"}
    return {"display": "block"}, {"display": "none"}, {"display": "none"}


@callback(
    Output("note-content-display", "children"),
    Input("selected-note-id", "data"),
    prevent_initial_call=True,
)
def display_note_content(note_id):
    if not note_id:
        return html.Div("Select a note to view")

    note = db.get_note(note_id)
    if not note:
        return html.Div("Note not found")

    content_html = render_markdown_latex(note["content"] or "")
    return html.Div([
        html.H4(note["title"], style={"fontWeight": 600}),
        html.Small([
            f"Source: {note['source_filename'] or 'Direct input'} | ",
            f"Type: {note['source_type']} | ",
            f"Created: {note['created_at'][:10]}",
        ], className="text-muted d-block mb-3"),
        html.Hr(),
        dcc.Markdown(
            content_html,
            dangerously_allow_html=True,
            className="note-content",
            style={"lineHeight": "1.7"}
        ),
    ])


@callback(
    Output({"type": "del-note", "index": MATCH}, "children"),
    Input({"type": "del-note", "index": MATCH}, "n_clicks"),
    State({"type": "del-note", "index": MATCH}, "id"),
    prevent_initial_call=True,
)
def delete_note(n_clicks, btn_id):
    if not n_clicks:
        return no_update
    note_id = btn_id["index"]
    note = db.get_note(note_id)
    if note:
        # Delete from DB
        db.delete_note(note_id)
        # Delete file if exists
        note_path = os.path.join(NOTES_DIR, note["filename"])
        if os.path.exists(note_path):
            os.remove(note_path)
    return "Deleted"


@callback(
    Output("upload-file", "children"),
    Input("upload-file", "contents"),
    State("upload-file", "filename"),
    prevent_initial_call=True,
)
def handle_upload(contents, filename):
    if contents is None:
        return no_update

    content_type, content_string = contents.split(",")
    decoded = base64.b64decode(content_string)

    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return html.Div([
            html.I(className="bi bi-exclamation-triangle text-danger me-2"),
            f"Unsupported format: {ext}. Use MD, PDF, or images.",
        ])

    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(decoded)
        tmp_path = tmp.name

    try:
        title = os.path.splitext(filename)[0]
        content, note_filename, source_filename = convert_to_markdown(tmp_path, title)

        # Chunk and store
        chunks = chunk_text(content)

        # Add to database
        note_id = db.add_note(
            title=title,
            filename=note_filename,
            source_filename=source_filename,
            source_type=ext[1:] if ext != '.md' else 'md',
            content=content,
        )

        if chunks:
            db.store_chunks(note_id, chunks)

        return html.Div([
            html.I(className="bi bi-check-circle text-success me-2"),
            f"✅ Added: {title}",
            html.Br(),
            html.Small(f"→ {note_filename}", className="text-muted"),
        ])
    except Exception as e:
        return html.Div([
            html.I(className="bi bi-x-circle text-danger me-2"),
            f"Error: {str(e)}",
        ])
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@callback(
    Output("btn-add-text", "children"),
    Input("btn-add-text", "n_clicks"),
    State("pasted-title", "value"),
    State("pasted-text", "value"),
    prevent_initial_call=True,
)
def add_pasted_text(n_clicks, title, text):
    if not text or not text.strip():
        return "⚠️ Need text content"

    title = title or f"pasted-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    content, note_filename, _ = add_text_as_note(text, title)
    chunks = chunk_text(content)

    note_id = db.add_note(
        title=title,
        filename=note_filename,
        source_type="txt",
        content=content,
    )
    if chunks:
        db.store_chunks(note_id, chunks)

    return "✅ Added!"


@callback(
    Output("conversation-history", "children"),
    Input("btn-ask", "n_clicks"),
    State("question-input", "value"),
    prevent_initial_call=True,
)
def ask_question(n_clicks, question):
    if not question or not question.strip():
        return no_update

    # Show loading
    loading = html.Div([
        dbc.Spinner(size="sm"),
        " Thinking...",
    ], className="text-muted p-2")

    # Process through agent
    result = agent.answer_question(question)

    # Build conversation display
    items = []

    # Question
    items.append(html.Div([
        html.Div([
            html.Strong("🧑 You: ", style={"color": "#0d6efd"}),
            html.Span(question),
        ], className="mb-1 p-2 rounded",
           style={"background": "#e7f3ff"}),
    ], className="mb-3"))

    # Phases
    for phase in result.get("phases", []):
        phase_name = phase["phase"].capitalize()
        icon = {"Search": "🔍", "Explore": "🔎", "Conclude": "💡"}.get(phase_name, "📌")
        items.append(html.Div([
            html.Details([
                html.Summary(f"{icon} {phase_name} Phase",
                             style={"cursor": "pointer", "fontWeight": 500}),
                dcc.Markdown(
                    render_markdown_latex(phase["content"]),
                    dangerously_allow_html=True,
                    className="p-2 small",
                    style={"background": "#f8f9fa", "borderRadius": "4px"}
                ),
            ], className="mb-2"),
        ]))

    # Final answer
    answer = result.get("answer", "No answer generated.")
    items.append(html.Div([
        html.Div([
            html.Strong("🤖 AI: ", style={"color": "#198754"}),
        ]),
        dcc.Markdown(
            render_markdown_latex(answer),
            dangerously_allow_html=True,
            className="p-3 rounded",
            style={"background": "#f0faf0", "borderLeft": "3px solid #198754"}
        ),
    ], className="mb-3"))

    # Notes used
    if result.get("notes_used"):
        items.append(html.Div([
            html.Small("📚 Based on notes: ", className="text-muted fw-bold"),
            html.Div([
                html.Span(n["title"], className="badge bg-light text-dark me-1")
                for n in result["notes_used"]
            ], className="d-flex flex-wrap gap-1 mt-1"),
        ], className="mb-3 p-2", style={"background": "#f8f9fa", "borderRadius": "4px"}))

    return items


@callback(
    Output("suggestion-btns", "children"),
    Input("api-key-store", "data"),
)
def update_suggestions(api_key):
    if not api_key:
        return dbc.Button("Set API key for suggestions", color="secondary",
                          size="sm", disabled=True)

    suggestions = agent.suggest_questions(3)
    btns = []
    for s in suggestions:
        btns.append(
            dbc.Button(
                s, id={"type": "suggestion", "index": s},
                color="light", size="sm", className="text-start",
                style={"fontSize": "0.75rem", "whiteSpace": "normal",
                       "height": "auto", "textAlign": "left"}
            )
        )
    return btns


@callback(
    Output("question-input", "value"),
    Input({"type": "suggestion", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def fill_suggestion(n_clicks):
    if not any(n_clicks):
        return no_update
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update
    trigger = ctx.triggered[0]
    try:
        trigger_id = json.loads(trigger["prop_id"].split(".")[0])
        return trigger_id.get("index", "")
    except:
        return no_update


@callback(
    Output("current-view", "data", allow_duplicate=True),
    Input("selected-note-id", "data"),
    prevent_initial_call=True,
)
def set_view_to_note(note_id):
    if note_id:
        return "note"
    return "notes"

@callback(
    Output("current-view", "data", allow_duplicate=True),
    Input("btn-ask", "n_clicks"),
    prevent_initial_call=True,
)
def set_view_to_chat(n_clicks):
    if n_clicks:
        return "chat"
    return no_update


# ─── Run ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("  LLMNotes - NotebookLM Clone")
    print("=" * 50)
    print(f"  Notes directory: {NOTES_DIR}")
    print(f"  API Key configured: {'Yes' if OPENROUTER_API_KEY else 'No (set in UI)'}")
    print(f"  OpenRouter model: {os.environ.get('OPENROUTER_MODEL', 'default')}")
    print()
    print("  Open http://127.0.0.1:8050 in your browser")
    print("=" * 50)
    app.run(debug=True, host="0.0.0.0", port=8050)


if __name__ == "__main__":
    main()