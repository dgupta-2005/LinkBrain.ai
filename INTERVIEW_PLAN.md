# Project Implementation Plan: LinkBrain AI (Hack the Thread)

This document provides a detailed technical breakdown of the LinkBrain AI system, designed to help you explain the project's architecture and feature implementation during interviews.

## System Overview
**LinkBrain AI** is an intelligent link management platform that captures, summarizes, and categorizes social media content (Instagram, Twitter, YouTube) using AI. It bridges the gap between passive consumption on social apps and organized knowledge management.

---

## 🏗️ Core Architecture

The system follows a modern decoupled architecture with a focus on real-time processing and AI integration.

### 1. Backend (The Engine)
Built with **FastAPI**, the backend handles web requests, database transactions, and background task management.

- **Tech Stack**: FastAPI, SQLModel (ORM), SQLite, JWT.
- **Key Implementation Details**:
    - **Async Lifespan**: Uses FastAPI's `lifespan` to initialize the database and start the Telegram bot as a concurrent background task.
    - **SQLModel ORM**: Combines Pydantic's data validation with SQLAlchemy's database power, ensuring type safety from the DB to the API.
    - **Stateless Auth**: Implements JWT-based authentication. Tokens are stored in **HTTP-only cookies** for security against XSS attacks.
    - **Database Schema**: 
        - `User`: Manages authentication and Telegram account linking.
        - `SavedItem`: Stores extracted metadata, AI summaries, and link URLs.
        - `CustomBucket`: Allows users to dynamically extend the platform's filtering logic.

### 2. AI System (The Intelligence)
The AI layer is responsible for turning raw URLs into structured knowledge.

- **Tech Stack**: Google Gemini (via `google-generativeai`), Microlink API, YouTube oEmbed API.
- **Key Implementation Details**:
    - **Metadata Extraction Relay**:
        1. **Stage 1**: Checks for general metadata via Microlink.
        2. **Stage 2**: If it's a YouTube link, it uses the official oEmbed endpoint to get the exact video title and author (bypassing scrapers).
    - **"Safe Mode" Hallucination Prevention**: If metadata extraction fails for protected social links (e.g., private Instagram posts), the system detects this and inhibits the AI. Instead of guessing, it prompts the user to "edit manually," ensuring data integrity.
    - **Multi-Model Reliability**: Iterates through a prioritized list of Gemini models (Flash-lite -> Pro -> Flash) to handle rate limits or regional outages gracefully.
    - **Zero-Shot Prompting**: Uses a structured prompt that forces the AI to output **Pure JSON**, facilitating easy parsing by the Python backend.

### 3. Frontend (The Interface)
A clean, dashboard-style interface for managing saved knowledge.

- **Tech Stack**: HTML5, Vanilla CSS3, Jinja2 Templates.
- **Key Implementation Details**:
    - **Dynamic Filtering**: Server-side filtering and sorting for high performance with large datasets.
    - **Responsive Design**: Designed for both desktop and mobile viewing.
    - **CRUD Operations**: Users can edit existing AI summaries or categories if they want to fine-tune the organization.
    - **Bucket System**: Automatically aggregates links into "Buckets" based on the platform or AI-suggested categories.

### 4. Bot Integration (The Input)
The primary entry point for users to save content without leaving their social apps.

- **Tech Stack**: `python-telegram-bot` (Async).
- **Key Implementation Details**:
    - **Account Linking**: A unique 6-digit `link_code` generated in the web dashboard allows users to bind their Telegram `chat_id` to their web account.
    - **Passive Capture**: Listeners monitor for URLs in incoming messages, triggering the AI pipeline automatically.

---

## 🛠️ Key Libraries & Technical Imports

| Library | Purpose in this Project |
| :--- | :--- |
| `fastapi` | High-performance async web framework for the API and dashboard. |
| `sqlmodel` | Handles database interactions with Python classes instead of raw SQL. |
| `google-generativeai` | Connects to Gemini models for NLP tasks (summarization/categorization). |
| `python-telegram-bot` | Manages the real-time interaction between the user and the bot. |
| `bcrypt` / `passlib` | Securely hashes user passwords using industry-standard salts. |
| `pyjwt` | Generates secure tokens to keep users logged in across sessions. |
| `microlink` / `requests` | Fetches metadata (title, description) from external websites. |

---

## 🚀 Interview Talking Points (Key Features)

### 1. "How do you handle AI hallucinations?"
> "I implemented a multi-stage validation pipeline. Before sending a link to Gemini, we use tools like Microlink and oEmbed to extract ground-truth metadata. If we detect that a link is blocked or generic (like a login page), we trigger a 'Safe Mode' that skips AI generation, preventing the model from hallucinating a context it can't see."

### 2. "Why use FastAPI over Flask/Django?"
> "FastAPI was chosen for its native support for `asyncio`, which is critical for our project since we run a Telegram bot and handle multiple external API calls (Gemini, Microlink) concurrently. It also provides automatic Swagger documentation and Pydantic validation out of the box."

### 3. "How does the categorization work?"
> "We use a hybrid approach. The backend identifies the platform based on the domain (deterministic), while Gemini analyzes the extracted title and description to map the content to professional tags like 'Machine Learning', 'Productivity', or 'Finance' (probabilistic)."

### 4. "How is the data organized?"
> "The system uses a 'Bucket' concept. We have hardcoded buckets for top platforms like Instagram and YouTube, but I also implemented 'Custom Buckets' allowing users to create their own organizational silos based on their specific needs."

---

## 📋 Verification Plan

### Automated Testing
- [ ] Run `pytest` for authentication flow (if implemented).
- [ ] Verify AI API connectivity via `ai_agent.py` script.

### Manual Verification
- [ ] Register a new user and verify link code generation.
- [ ] Link a Telegram bot and send an Instagram Reel link.
- [ ] Check if the link appears in the web dashboard with the correct summary and category.
