"""AI Agent for LLMNotes - Search → Explore → Conclude loop using OpenRouter"""

import json
import re
import requests
from typing import List, Dict, Optional

from config import (
    OPENROUTER_API_KEY, OPENROUTER_BASE_URL,
    OPENROUTER_MODEL, OPENROUTER_QUICK_MODEL
)
from database import Database
from utils.converters import chunk_text


class LLMNotesAgent:
    """AI agent that searches, explores, and concludes answers from user notes."""

    def __init__(self, db: Database):
        self.db = db
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/vishnuprksh/LLMNotes",
        })

    def _call_llm(self, messages: List[Dict], model: Optional[str] = None, temperature: float = 0.3) -> str:
        """Call OpenRouter API"""
        if not OPENROUTER_API_KEY:
            return "⚠️ OpenRouter API key not configured. Set OPENROUTER_API_KEY environment variable."

        model = model or OPENROUTER_MODEL
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4096,
        }

        try:
            resp = self.session.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                json=payload,
                timeout=60
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error calling OpenRouter: {str(e)}"

    def _get_relevant_chunks(self, query: str, top_k: int = 3) -> List[Dict]:
        """
        Retrieve relevant note chunks using keyword matching.
        Falls back to simple text matching since we don't have embeddings locally.
        """
        chunks = self.db.get_all_chunks()
        if not chunks:
            return []

        query_terms = set(query.lower().split())
        scored = []

        for chunk in chunks:
            text = chunk["chunk_text"].lower()
            # Count how many query terms appear in this chunk
            matches = sum(1 for term in query_terms if term in text)
            if matches > 0:
                scored.append({
                    "score": matches,
                    "note_title": chunk["note_title"],
                    "note_filename": chunk["note_filename"],
                    "text": chunk["chunk_text"][:1500],
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def answer_question(self, question: str) -> Dict:
        """
        Main entry point: search → explore → conclude

        Returns:
        {
            "answer": str,
            "reasoning": str,
            "notes_used": [{"title": str, "filename": str}, ...],
            "phases": [
                {"phase": "search", "content": ...},
                {"phase": "explore", "content": ...},
                {"phase": "conclude", "content": ...},
            ]
        }
        """
        result = {
            "answer": "",
            "reasoning": "",
            "notes_used": [],
            "phases": []
        }

        # --- PHASE 1: SEARCH ---
        # First, search notes for relevant content
        relevant_notes = self.db.search_notes(question)
        relevant_chunks = self._get_relevant_chunks(question, top_k=5)

        # Build context from notes
        notes_context = []
        seen_titles = set()

        for note in relevant_notes:
            if note["title"] not in seen_titles:
                notes_context.append({
                    "title": note["title"],
                    "filename": note["filename"],
                    "preview": note["content_preview"][:500]
                })
                seen_titles.add(note["title"])

        # Add chunk context
        for c in relevant_chunks:
            if c["note_title"] not in seen_titles:
                notes_context.append({
                    "title": c["note_title"],
                    "filename": c["note_filename"],
                    "preview": c["text"][:500]
                })
                seen_titles.add(c["note_title"])

        result["notes_used"] = notes_context

        search_phase = {
            "phase": "search",
            "content": f"Found {len(notes_context)} relevant notes:\n" +
                       "\n".join(f"- {n['title']}" for n in notes_context)
        }
        result["phases"].append(search_phase)

        if not notes_context:
            result["answer"] = "No relevant notes found. Please add notes related to your question first."
            result["reasoning"] = "No matching content in the knowledge base."
            return result

        # Format context for the LLM
        context_str = "\n\n---\n\n".join([
            f"## Note: {n['title']}\n{n['preview']}"
            for n in notes_context
        ])

        # --- PHASE 2: EXPLORE ---
        explore_prompt = [
            {
                "role": "system",
                "content": """You are a research assistant analyzing the user's personal notes.

Your task is to EXPLORE the provided notes to find information relevant to the user's question.
Identify:
1. Which notes contain relevant information
2. What specific facts, dates, names, or data points are mentioned
3. Any connections or contradictions between notes
4. What additional information would be needed

Be thorough and cite specific content from the notes."""
            },
            {
                "role": "user",
                "content": f"## Question\n{question}\n\n## Notes Content\n{context_str}\n\nExplore these notes and find all relevant information."
            }
        ]

        explore_result = self._call_llm(explore_prompt, model=OPENROUTER_QUICK_MODEL, temperature=0.2)

        explore_phase = {
            "phase": "explore",
            "content": explore_result
        }
        result["phases"].append(explore_phase)

        # --- PHASE 3: CONCLUDE ---
        conclude_prompt = [
            {
                "role": "system",
                "content": """You are a knowledgeable assistant that synthesizes information from notes to answer questions.

Based on the exploration analysis, provide a clear, well-reasoned answer.
- Base your answer ONLY on the provided notes content
- If the notes don't contain enough information, clearly state what's missing
- Use markdown formatting for readability
- Support claims with references to specific notes
- If relevant, include LaTeX math using $$...$$ or $...$ notation

Format your answer in markdown."""
            },
            {
                "role": "user",
                "content": f"## Question\n{question}\n\n## Notes Content\n{context_str}\n\n## Exploration Analysis\n{explore_result}\n\nBased on the notes provided, give a comprehensive answer."
            }
        ]

        answer = self._call_llm(conclude_prompt, temperature=0.3)

        conclude_phase = {
            "phase": "conclude",
            "content": answer
        }
        result["phases"].append(conclude_phase)

        # Extract reasoning (first portion of explore)
        result["reasoning"] = explore_result[:1000]
        result["answer"] = answer

        # Save to conversation history
        self.db.add_conversation(
            question=question,
            answer=answer,
            reasoning=explore_result[:1000],
            notes_used=[n["title"] for n in notes_context]
        )

        return result

    def suggest_questions(self, num_suggestions: int = 3) -> List[str]:
        """Generate suggested questions based on available notes"""
        notes = self.db.get_all_notes()
        if not notes:
            return ["Add some notes to get started!"]

        summaries = "\n".join([
            f"- {n['title']}: {n['content_preview'][:100]}"
            for n in notes[:5]
        ])

        prompt = [
            {
                "role": "system",
                "content": "Generate 3 thoughtful questions a user could ask about their notes. Return ONLY a JSON array of strings."
            },
            {
                "role": "user",
                "content": f"Based on these notes, suggest {num_suggestions} questions:\n{summaries}"
            }
        ]

        result = self._call_llm(prompt, model=OPENROUTER_QUICK_MODEL, temperature=0.7)
        try:
            # Try to parse JSON
            questions = json.loads(result)
            if isinstance(questions, list) and len(questions) > 0:
                return questions[:num_suggestions]
        except:
            pass

        # Fallback: extract questions from text
        questions = re.findall(r'(?:^|\n)\s*["\']?([A-Z][^"\'?\n]*\?)', result)
        return questions[:num_suggestions] if questions else ["What information can you find in my notes?"]