# SARA: Semi-Agentic Search Agent

This project is an agentic research assistant that searches, extracts, and analyzes academic papers from arXiv using a multi-agent workflow. It combines local paper search, section extraction, vector database (RAG) embedding, and web search to provide synthesized answers to user queries.

## Features
- Search arXiv for papers using custom queries (via arxivxplorer.com)
- Extract structured sections from arXiv papers (using ar5iv.org HTML)
- Embed paper sections into a LanceDB vector database using Ollama embeddings
- Perform RAG (Retrieval-Augmented Generation) search over local papers
- Supplement answers with DuckDuckGo web search
- Multi-agent workflow: Librarian, Web Researcher, Lead Analyst
- Streamlit-based interactive chat UI

## File Overview
- `agent.py`: Main Streamlit app, agent logic, RAG, embedding, and chat interface
- `search_arxiv.py`: Scrapes arxivxplorer.com for papers matching a query
- `extract_paper_sections.py`: Extracts and saves structured sections from arXiv papers using ar5iv.org

## Setup Instructions

### 1. Install Conda (if not already installed)
Download and install Miniconda or Anaconda from [conda.io](https://docs.conda.io/en/latest/miniconda.html).

### 2. Create and Activate Environment
```bash
conda create -n arxiv_agent python=3.10
conda activate arxiv_agent
```

### 3. Install Ollama (for LLM and Embeddings)
- Download and install Ollama from [ollama.com/download](https://ollama.com/download)
- Start the Ollama server:
  - Run `ollama serve` in a terminal

### 4. Install Project Dependencies
```bash
pip install -r requirements.txt
```

### 5. Install Playwright Browsers (for arxiv scraping)
```bash
python -m playwright install
```

### 6. Run the Streamlit App
```bash
streamlit run agent.py
```

## Usage
- Use `/search [topic]` to search arXiv and build the local knowledge base
- Use `/analysis [question]` to analyze and synthesize answers using local and web data
- Or just chat for web-based answers

## Notes
- Ollama must be running for LLM and embedding features
- LanceDB is used for vector storage (no external DB setup needed)
- All data is stored locally in the `arxiv_data` folder

## Requirements
See `requirements.txt` for Python dependencies.

## Troubleshooting
- If scraping fails, check Playwright browser installation
- If embeddings fail, ensure Ollama is running and the required models are pulled (e.g., `ollama pull phi3:3.8b`, `ollama pull embeddinggemma:latest`)
- For Windows users, run commands in Anaconda Prompt or PowerShell

## License
MIT License
