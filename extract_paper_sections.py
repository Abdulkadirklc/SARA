import argparse
import json
import os
import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


# ----------------------------- Yardımcı Modeller -----------------------------
@dataclass
class Section:
    title: str
    content: str


# ---------------------------- Yardımcı Fonksiyonlar ---------------------------
def secure_filename(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return re.sub(r"_+", "_", name).strip("._")


def arxiv_to_ar5iv_html(url: str) -> Optional[str]:
    parsed = urlparse(url)
    if "arxiv.org" not in parsed.netloc:
        return None
    path = parsed.path.strip("/")
    arxiv_id: Optional[str] = None
    if path.startswith("abs/"):
        arxiv_id = path[len("abs/"):]
    elif path.startswith("pdf/"):
        arxiv_id = path[len("pdf/"):]
        if arxiv_id.endswith(".pdf"):
            arxiv_id = arxiv_id[:-4]
    else:
        # Beklenmeyen formatlar için tüm path'i id olarak kullanmayı dene
        arxiv_id = path
    if not arxiv_id:
        return None
    return f"https://ar5iv.org/html/{arxiv_id}"


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.text


def clean_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def remove_headers_and_footers(lines: List[str]) -> List[str]:
    # Sayfa başlık/altlıkları çok tekrar eder: frekans > 3 ise at
    from collections import Counter
    norm = lambda s: re.sub(r"\s+", " ", s.strip())
    counts = Counter(norm(l) for l in lines if l.strip())
    to_drop = {t for t, c in counts.items() if c >= 3 and len(t) <= 80}
    cleaned = []
    for l in lines:
        t = norm(l)
        if not t:
            cleaned.append("")
            continue
        if t in to_drop:
            cleaned.append("")
            continue
        # Tek başına sayfa numarası gibi satırları at
        if re.fullmatch(r"\d+", t):
            cleaned.append("")
            continue
        cleaned.append(l)
    return cleaned


STOP_TITLES = {
    "references", "acknowledgments", "acknowledgements", "appendix",
    "supplementary material", "bibliography"
}


def parse_sections_from_ar5iv_html(html: str) -> List[Section]:
    soup = BeautifulSoup(html, "html.parser")

    # Önce özeti yakala
    sections: List[Section] = []
    abstract_node = soup.select_one(".ltx_abstract, section.abstract, div.abstract")
    if abstract_node:
        abs_text = clean_text(abstract_node.get_text(" "))
        if abs_text:
            sections.append(Section(title="Abstract", content=abs_text))

    article = soup.find("article") or soup.body or soup
    if not article:
        return sections

    current_title: Optional[str] = None
    current_chunks: List[str] = []

    def flush():
        if current_title and current_chunks:
            content = clean_text("\n".join(current_chunks))
            if content:
                sections.append(Section(title=current_title, content=content))

    # ar5iv genellikle <h2> ana bölümler, <h3> alt bölümler
    for el in article.find_all(["h1", "h2", "h3", "h4", "p", "ul", "ol", "pre", "table", "figure"], recursive=True):
        if el.name in {"h1", "h2", "h3", "h4"}:
            title = clean_text(el.get_text(" "))
            # referans/ek sonrası kes
            if title.lower() in STOP_TITLES:
                flush()
                current_title = None
                current_chunks = []
                break
            # yeni bölüm başlat
            if current_title is not None:
                flush()
                current_chunks = []
            current_title = title
        else:
            text = clean_text(el.get_text(" "))
            if text and current_title:
                current_chunks.append(text)
    # son bölüm
    flush()

    # Eğer hiç başlık bulunamadıysa, tüm gövdeyi tek bölüm ver
    if not any(s.title != "Abstract" for s in sections):
        body_text = clean_text(article.get_text(" "))
        if body_text:
            sections.append(Section(title="Body", content=body_text))
    return sections


def extract_sections_from_arxiv_link(link: str) -> List[Section]:
    ar5iv_url = arxiv_to_ar5iv_html(link)
    if not ar5iv_url:
        raise ValueError(f"arXiv linki algılanamadı: {link}")
    html = fetch_html(ar5iv_url)
    sections = parse_sections_from_ar5iv_html(html)
    return sections


# --------------------------------- Ana Akış ---------------------------------
def process_paper(arxiv_link: str, output_dir: str = "papers") -> Optional[List[dict]]:
    os.makedirs(output_dir, exist_ok=True)

    # paper_id'yi arxiv linkinden üret
    parsed = urlparse(arxiv_link)
    pid = parsed.path.strip("/")
    if pid.startswith("abs/"):
        pid = pid[len("abs/"):]
    elif pid.startswith("pdf/"):
        pid = pid[len("pdf/"):]
        if pid.endswith(".pdf"):
            pid = pid[:-4]
    paper_id = secure_filename(pid)

    try:
        sections = extract_sections_from_arxiv_link(arxiv_link)
        sections_json = [{"title": s.title, "content": s.content} for s in sections]

        out_path = os.path.join(output_dir, f"{paper_id}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({
                "paper_id": paper_id,
                "link": arxiv_link,
                "ar5iv_url": arxiv_to_ar5iv_html(arxiv_link),
                "sections": sections_json
            }, f, ensure_ascii=False, indent=2)

        print(f"Makale işlendi: {paper_id} -> {out_path}")
        return sections_json
    except Exception as e:
        print(f"Hata (process_paper): {paper_id}: {e}")
        return None


def process_multiple_papers(json_file: str, output_dir: str = "papers", limit: Optional[int] = None) -> None:
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    sayac = 0
    for paper in data:
        link = paper.get("tam_metin_linki")
        if not link:
            continue
        if "arxiv.org" not in link:
            continue
        process_paper(link, output_dir=output_dir)
        sayac += 1
        if limit is not None and sayac >= limit:
            break


def main():
    parser = argparse.ArgumentParser(description="ArXiv PDF'lerini indirip bölümlere ayırarak JSON'a kaydeder.")
    parser.add_argument("--json-file", default="arastirma_sonuclari.json", help="Kaynak JSON dosyası")
    parser.add_argument("--output-dir", default="papers", help="Çıktı klasörü")
    parser.add_argument("--limit", type=int, default=None, help="İşlenecek makale sayısını sınırla")
    args = parser.parse_args()

    process_multiple_papers(args.json_file, output_dir=args.output_dir, limit=args.limit)


if __name__ == "__main__":
    main()