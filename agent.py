import streamlit as st
import os
import subprocess
import json
import shutil
from pathlib import Path
import logging
import ollama
import lancedb
from ddgs import DDGS

# --- BASIC SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = Path("arxiv_data")
PAPERS_DIR = DATA_DIR / "papers"
DB_URI = DATA_DIR / "lancedb"
SEARCH_RESULT_FILE = "arastirma_sonuclari.json"

LLM_MODEL_NAME = "phi3:3.8b"
EMBEDDING_MODEL_NAME = "embeddinggemma:latest"

# --- HELPER FUNCTIONS & TOOLS ---
def setup_directories(): os.makedirs(PAPERS_DIR, exist_ok=True)
setup_directories()
def run_search_script(query: str) -> str:
    try:
        if not os.path.exists("search_arxiv.py"): return "Error: 'search_arxiv.py' not found."
        st.toast(f"🔍 Searching Arxiv for: '{query}'")
        subprocess.run(["python", "search_arxiv.py", "--query", query, "--limit", "5"], check=True, timeout=300)
        return f"Search for '{query}' completed."
    except Exception as e:
        logger.error(f"Error in search script for query '{query}': {e}")
        st.error(f"An error occurred while searching for '{query}'. Please check the console logs.")
        return f"Error during search for '{query}'."
def run_extract_script() -> str:
    try:
        if not os.path.exists("extract_paper_sections.py"): return "Error: 'extract_paper_sections.py' not found."
        if not os.path.exists(SEARCH_RESULT_FILE): return "Warning: Search result file not found, skipping extraction."
        st.toast("📄 Processing papers...")
        cmd = ["python", "extract_paper_sections.py", "--json-file", SEARCH_RESULT_FILE, "--output-dir", str(PAPERS_DIR)]
        subprocess.run(cmd, check=True, timeout=600)
        count = len(list(PAPERS_DIR.glob("*.json")))
        return f"Extraction complete. Processed {count} papers."
    except Exception as e: return f"Error in extraction script: {e}"
def duckduckgo_search(query: str, max_results: int = 3) -> str:
    st.toast(f"🌐 Searching the web for: '{query}'")
    try:
        results = DDGS().text(query, max_results=max_results)
        return "\n".join(f"- {res['title']}: {res['body']}" for res in results)
    except Exception as e: return f"DuckDuckGo search error: {e}"

# --- Vector Database (RAG) Management ---
def load_papers_into_db():
    json_files = list(PAPERS_DIR.glob("*.json"))
    if not json_files: return False
    MIN_CONTENT_LENGTH = 300; FORBIDDEN_TITLES = {'references', 'citations', 'quick links', 'arxivlabs', 'access paper'}; ERROR_SUBSTRINGS = ["fatal error", "abruptly"]
    valid_texts_to_embed = [] ; skipped_papers_count = 0
    for path in json_files:
        with open(path, 'r', encoding='utf-8') as f: data = json.load(f)
        paper_id = data.get('paper_id', 'Unknown'); link = data.get('link', '')
        is_paper_valid = False; paper_sections = []
        for section in data.get("sections", []):
            title = section.get("title", "").lower(); content = section.get("content", "")
            if any(e in content.lower() for e in ERROR_SUBSTRINGS) or title in FORBIDDEN_TITLES or len(content) < MIN_CONTENT_LENGTH: continue
            paper_sections.append(f"Source: {paper_id} (Link: {link})\nSection: {section.get('title', 'Untitled')}\n\n{content}")
            is_paper_valid = True
        if is_paper_valid: valid_texts_to_embed.extend(paper_sections)
        else: skipped_papers_count += 1
    if skipped_papers_count > 0: st.toast(f"Skipped {skipped_papers_count} poorly parsed paper(s).", icon="⚠️")
    if not valid_texts_to_embed: return False
    embeddings = []; progress_bar = st.progress(0, text=f"Generating embeddings...")
    for i, text in enumerate(valid_texts_to_embed):
        response = ollama.embeddings(model=EMBEDDING_MODEL_NAME, prompt=text); embeddings.append(response["embedding"])
        progress_bar.progress((i + 1) / len(valid_texts_to_embed), text=f"Embedding chunk {i + 1}/{len(valid_texts_to_embed)}")
    progress_bar.empty()
    data_to_add = [{"vector": emb, "text": txt} for emb, txt in zip(embeddings, valid_texts_to_embed)]
    db = lancedb.connect(DB_URI); db.create_table("papers", data=data_to_add, mode="overwrite")
    st.toast("✅ Knowledge base updated!"); return True

# --- Knowledge Base Search ---
def search_knowledge_base(query: str, limit: int = 10) -> str:
    """Performs a RAG search in the knowledge base."""
    db = lancedb.connect(DB_URI)
    if "papers" not in db.table_names():
        return ""
    table = db.open_table("papers")
    
    query_embedding = ollama.embeddings(model=EMBEDDING_MODEL_NAME, prompt=query)["embedding"]
    results = table.search(query_embedding).limit(limit).to_list()

    
    return "\n\n---\n\n".join([res['text'] for res in results])


# --- AGENT FLOWS ---

def run_llm_agent(system_prompt: str, user_prompt: str, use_json=False):
    messages = [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_prompt}]
    format_type = "json" if use_json else ""
    response = ollama.chat(model=LLM_MODEL_NAME, messages=messages, format=format_type)
    return response['message']['content']

def run_research_flow(user_input: str):
    queries_prompt = f"""Based on the user's research request, generate 2-3 diverse and effective search queries (maximum 6 words) for the Arxiv database. Respond in JSON format with a single key "queries" which is a list of strings. User Request: "{user_input}" """
    try:
        response_str = run_llm_agent("You are an expert at creating concise, diverse search queries for academic databases.", queries_prompt, use_json=True)
        search_queries = json.loads(response_str)["queries"]
    except (json.JSONDecodeError, KeyError): search_queries = [user_input]
    st.info(f"**Agent's Plan:** Starting research with the following queries:\n" + "\n".join(f"- `{q}`" for q in search_queries))
    all_papers = []; seen_links = set()
    for query in search_queries:
        run_search_script(query)
        if os.path.exists(SEARCH_RESULT_FILE):
            with open(SEARCH_RESULT_FILE, 'r', encoding='utf-8') as f: papers = json.load(f)
            for paper in papers:
                link = paper.get("tam_metin_linki")
                if link and link not in seen_links: all_papers.append(paper); seen_links.add(link)
    if all_papers:
        with open(SEARCH_RESULT_FILE, 'w', encoding='utf-8') as f: json.dump(all_papers, f, ensure_ascii=False, indent=4)
        st.toast(f"Found and combined a total of {len(all_papers)} unique papers.")
    run_extract_script(); success = load_papers_into_db()
    final_msg = f"Research completed using {len(search_queries)} queries, finding a total of {len(all_papers)} unique papers."
    if success:
        st.session_state.kb_ready = True
        final_msg += "\n\n✅ **Knowledge base updated.** You can now ask questions using the `/analysis` command."
    else: final_msg += "\n\n⚠️ Research was done, but no valid content could be loaded."
    return final_msg

def librarian_agent(user_input: str) -> str:
    st.info("`Librarian Agent:` Searching the local knowledge base...")
    keyword_prompt = f"""From the user's question, extract the core keywords to search in a vector database. Question: "{user_input}" """
    keyword_query = run_llm_agent("You are a keyword extraction specialist.", keyword_prompt)
    context = search_knowledge_base(keyword_query, limit=10)
    if not context:
        st.warning("`Librarian Agent:` Found no relevant information in the local papers.")
    return context

def web_researcher_agent(user_input: str, local_context: str) -> str:
    st.info("`Web Researcher Agent:` Planning and executing web search...")
    web_queries_prompt = f"""Based on the user's question and the information already found in our local papers, what specific, targeted questions should we ask a web search engine to fill in the gaps? Generate up to 3 concise search queries. Respond in JSON with a single key "queries". User Question: "{user_input}" Found Local Context: "{local_context[:1000]}" """
    web_context = ""
    try:
        response_str = run_llm_agent("You are a Research Planner that generates effective web search queries.", web_queries_prompt, use_json=True)
        web_queries = json.loads(response_str).get("queries", [])
        if web_queries:
            st.info(f"**Internal Step:** Searching the web with generated queries:\n" + "\n".join(f"- `{q}`" for q in web_queries))
            for query in web_queries:
                web_context += duckduckgo_search(query) + "\n\n"
        else:
            st.warning("`Web Researcher Agent:` Could not generate specific queries, falling back to a direct search.")
            web_context = duckduckgo_search(user_input)
    except (json.JSONDecodeError, KeyError):
        web_context = duckduckgo_search(user_input)
    if not web_context:
        st.warning("`Web Researcher Agent:` Found no relevant information on the web.")
    return web_context

def lead_analyst_agent(user_input: str, local_context: str, web_context: str) -> str:
    st.info("`Lead Analyst Agent:` Synthesizing all information and generating new insights...")
    system_prompt = """
You are a brilliant, insightful academic research analyst. Your job is to combine evidence, reason logically, and write in clear, structured Markdown.

**Additional Rules:**
- Write in academic yet natural tone (not robotic).
- Add short subtitles for each theme.
- If data is contradictory, mention it explicitly.
- When no citations available, infer cautiously and note uncertainty.
- Use bullet points when comparing ideas.
"""
    final_user_prompt = f"""**User's Question/Idea:** "{user_input}"
---
**Librarian's Findings (from papers):**
{local_context or 'The Librarian found no relevant information in the local knowledge base.'}
---
**Web Researcher's Report:**
{web_context or 'The Web Researcher found no relevant information.'}"""
    return run_llm_agent(system_prompt, final_user_prompt)

def run_analysis_flow(user_input: str):
    local_findings = librarian_agent(user_input)
    web_report = web_researcher_agent(user_input, local_findings)
    final_analysis = lead_analyst_agent(user_input, local_findings, web_report)
    return final_analysis

def run_chat_flow(user_input: str):

    # Step 1: Generating smart queries 
    queries_prompt = f"""
    The user is asking a general question or starting a conversation. Analyze their input and generate 2-3 web search queries to find helpful information for a thoughtful response.
    Respond in JSON format with a single key "queries". User Input: "{user_input}"
    """
    web_context = ""
    try:
        response_str = run_llm_agent("You are an expert at generating helpful, relevant search queries.", queries_prompt, use_json=True)
        web_queries = json.loads(response_str).get("queries", [])
        if web_queries:
            # Gives a message in Streamlit UI about the internal step
            st.info(f"**Internal Step:** Thinking and searching the web with generated queries:\n" + "\n".join(f"- `{q}`" for q in web_queries))
            for query in web_queries:
                web_context += duckduckgo_search(query) + "\n\n"
        else:
            web_context = duckduckgo_search(user_input)
    except (json.JSONDecodeError, KeyError):
        web_context = duckduckgo_search(user_input)

    # Step 2: Generating response with context
    system_prompt = """
    You are a News Aggregator and Factual Assistant.
    Your SOLE PURPOSE is to answer the user's question by summarizing the information found in the `Web Search Results`.
    - **DO NOT refuse to answer.**
    - **DO NOT apologize or say you cannot provide real-time information.**
    - **DO NOT recommend other websites.**
    - Directly synthesize the information from the `Web Search Results` into a helpful, coherent answer.
    - If the user is just saying "Hello," respond naturally as a friendly assistant.
    """
    final_user_prompt = f"""
    User's Input: "{user_input}"
    ---
    Web Search Results:
    {web_context or "No information was found on the web."}
    """
    return run_llm_agent(system_prompt, final_user_prompt)


# --- STREAMLIT UI ---
st.set_page_config(page_title="Agentic Research Team", page_icon="🧑‍🔬", layout="wide")
if "messages" not in st.session_state: st.session_state.messages = [{"role": "assistant", "content": "Welcome! I am the project manager for your research team. Please use commands to guide us.\n\n- `/search [your topic]`\n- `/analysis [your question or idea]`"}]
if "kb_ready" not in st.session_state: st.session_state.kb_ready = os.path.exists(DB_URI) and len(os.listdir(DB_URI)) > 0
with st.sidebar:
    st.header("👨‍🏫 Agent Team Control")
    st.markdown("Use commands to direct the agent team.")
    st.divider()
    kb_status = "✅ Ready" if st.session_state.kb_ready else "❌ Empty"
    st.write(f"**Knowledge Base:** {kb_status}")
    if st.button("Reset System (Deletes Data)"):
        st.session_state.clear()
        if DATA_DIR.exists(): shutil.rmtree(DATA_DIR)
        setup_directories()
        st.rerun()
st.title("🕵️‍♂️ Agentic Research Team")
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
if user_input := st.chat_input("Use /search or /analysis, or just chat..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"): st.markdown(user_input)
    with st.chat_message("assistant"):
        response_content = ""
        if user_input.lower().startswith("/search"):
            topic = user_input[len("/search"):].strip()
            if not topic: response_content = "Please provide a topic after the `/search` command."
            else: response_content = run_research_flow(topic)
        elif user_input.lower().startswith("/analysis"):
            question = user_input[len("/analysis"):].strip()
            if not st.session_state.kb_ready: response_content = "⚠️ The knowledge base is empty. Please use `/search` first."
            elif not question: response_content = "Please provide a question or idea after the `/analysis` command."
            else:
                response_content = run_analysis_flow(question)
        else:
             with st.spinner("💬 Thinking and searching the web..."):
                response_content = run_chat_flow(user_input)
        st.markdown(response_content)
        st.session_state.messages.append({"role": "assistant", "content": response_content})