"""Deterministic Markdown views for M1; no LLM is used during ingestion."""
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/source/Guia_Turistica_Lavalleja_Consolidada_v4(2).md"
OUT = ROOT / "data/generated"
PARSER_VERSION = "m1-deterministic-1"


def refs(text):
    return sorted({int(x) for x in re.findall(r"\[(\d+)\]", text)})


def stable(prefix, text):
    return f"{prefix}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"


def parse_blocks(lines):
    blocks, path, current = [], [], None
    def flush(end):
        nonlocal current
        if not current:
            return
        text = "\n".join(current["lines"]).strip()
        if text:
            heading_path = current["heading_path"]
            raw = f"{SOURCE}:{current['start']}:{end}:{text}"
            blocks.append({
                "block_id": stable("b", raw), "heading_path": heading_path,
                "heading_level": current["level"], "title": current["title"],
                "text": text, "start_line": current["start"], "end_line": end,
                "source_refs": refs(text), "section_type": current["section_type"],
            })
        current = None
    for number, line in enumerate(lines, 1):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            flush(number - 1)
            level, title = len(match.group(1)), match.group(2).strip()
            path = path[: level - 1] + [title]
            section_type = "faq" if "Preguntas de viaje" in " / ".join(path) else "narrative"
            current = {"start": number, "level": level, "title": title, "heading_path": path[:], "lines": [], "section_type": section_type}
        elif current is None:
            current = {"start": number, "level": 0, "title": "", "heading_path": [], "lines": [], "section_type": "preamble"}
        else:
            current["lines"].append(line)
    flush(len(lines))
    return blocks


def make_chunks(blocks, max_chars=1900, overlap=260):
    chunks = []
    for block in blocks:
        text = block["text"]
        if len(text) <= max_chars:
            pieces = [text]
        else:
            pieces, start = [], 0
            while start < len(text):
                end = min(len(text), start + max_chars)
                if end < len(text):
                    cut = text.rfind("\n", start, end)
                    if cut > start + max_chars // 2:
                        end = cut
                pieces.append(text[start:end].strip())
                if end == len(text):
                    break
                start = max(start + 1, end - overlap)
        for index, piece in enumerate(pieces):
            raw = f"{block['block_id']}:{index}:{piece}"
            chunks.append({"chunk_id": stable("c", raw), "block_id": block["block_id"], "entity_id": None,
                           "title": block["title"], "heading_path": block["heading_path"],
                           "start_line": block["start_line"], "end_line": block["end_line"],
                           "source_refs": block["source_refs"], "section_type": block["section_type"], "text": piece})
    return chunks


def parse_catalog(lines):
    start = next((i for i, x in enumerate(lines) if x.strip() == "### Directorio de establecimientos"), 0)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("### Cómo interpretar")), len(lines))
    entries, zone, current = [], "", None
    def flush(end_line):
        nonlocal current
        if not current: return
        text = "\n".join(current["lines"]).strip()
        fields = {"entity_id": stable("e", current["name"] + "\n" + text), "name": current["name"],
                  "categories": [], "zone": current["zone"], "location_text": "", "contacts": [],
                  "description": text, "status": "active", "source_refs": refs(text),
                  "start_line": current["start"], "end_line": end_line}
        for line in current["lines"]:
            s = line.strip()
            if s.startswith("Ubicación:"):
                fields["location_text"] = s.split(":", 1)[1].strip()
            elif s.startswith("Contacto:"):
                fields["contacts"].extend([x.strip() for x in s.split(":", 1)[1].split("·")])
            elif not s.startswith("#") and s and not s.startswith("Ubicación:") and not s.startswith("Contacto:"):
                fields["categories"].extend([x.strip() for x in s.split("·") if x.strip() and len(x) < 45])
        low = text.lower()
        if "temporalmente cerrado" in low: fields["status"] = "temporary_closed"
        if "históric" in low or "registro" in low: fields["status"] = "historical"
        entries.append(fields); current = None
    for i in range(start + 1, end):
        line = lines[i]
        if line.startswith("### "):
            flush(i); zone = line[4:].strip()
        elif line.startswith("#### "):
            flush(i); current = {"name": line[5:].strip(), "zone": zone, "start": i + 1, "lines": []}
        elif current:
            current["lines"].append(line)
    flush(end)
    return entries


def parse_faq(blocks):
    return [{"faq_id": stable("faq", b["title"]), "question": b["title"], "answer": b["text"],
             "start_line": b["start_line"], "end_line": b["end_line"], "source_refs": b["source_refs"]}
            for b in blocks if b["section_type"] == "faq" and b["heading_level"] == 3]


def parse_sources(text):
    marker = text.find("## Fuentes de la guía consolidada")
    tail = text[marker:] if marker >= 0 else ""
    out = []
    for line in tail.splitlines():
        m = re.match(r"^\[(\d+)\]\s+(.+)$", line.strip())
        if not m: continue
        number, body = int(m.group(1)), m.group(2)
        urls = re.findall(r"https?://[^)\s]+", body)
        review = re.search(r"Revisión documental\s+([^\.]+)", body)
        title = re.sub(r"\s*\[[^]]+\]\([^)]*\)", "", body).split(". Revisión documental")[0].strip()
        out.append({"source_number": number, "name": title.split(".", 1)[0], "title": title, "url": urls[0] if urls else None, "review_date": review.group(1).strip() if review else None})
    return out


def write_jsonl(name, rows):
    (OUT / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def build_sqlite(blocks, chunks, catalog, sources):
    db = sqlite3.connect(OUT / "giana.sqlite3")
    db.executescript("""
      DROP TABLE IF EXISTS entities; DROP TABLE IF EXISTS entity_categories; DROP TABLE IF EXISTS entity_contacts;
      DROP TABLE IF EXISTS source_blocks; DROP TABLE IF EXISTS sources; DROP TABLE IF EXISTS chunks;
      DROP TABLE IF EXISTS source_fts; DROP TABLE IF EXISTS entity_fts;
      CREATE TABLE entities(entity_id TEXT PRIMARY KEY,name TEXT,zone TEXT,location_text TEXT,description TEXT,status TEXT,start_line INT,end_line INT);
      CREATE TABLE entity_categories(entity_id TEXT,category TEXT); CREATE TABLE entity_contacts(entity_id TEXT,contact TEXT);
      CREATE TABLE source_blocks(block_id TEXT PRIMARY KEY,title TEXT,heading_path TEXT,text TEXT,start_line INT,end_line INT,source_refs TEXT,section_type TEXT);
      CREATE TABLE chunks(chunk_id TEXT PRIMARY KEY,block_id TEXT,title TEXT,text TEXT,start_line INT,end_line INT,source_refs TEXT);
      CREATE TABLE sources(source_number INTEGER PRIMARY KEY,name TEXT,title TEXT,url TEXT,review_date TEXT);
      CREATE VIRTUAL TABLE source_fts USING fts5(block_id UNINDEXED,title,heading_path,text);
      CREATE VIRTUAL TABLE entity_fts USING fts5(entity_id UNINDEXED,name,zone,location_text,description);
    """)
    for b in blocks:
        db.execute("INSERT INTO source_blocks VALUES(?,?,?,?,?,?,?,?)", (b["block_id"], b["title"], " / ".join(b["heading_path"]), b["text"], b["start_line"], b["end_line"], json.dumps(b["source_refs"]), b["section_type"]))
        db.execute("INSERT INTO source_fts VALUES(?,?,?,?)", (b["block_id"], b["title"], " / ".join(b["heading_path"]), b["text"]))
    for c in chunks: db.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?,?)", (c["chunk_id"], c["block_id"], c["title"], c["text"], c["start_line"], c["end_line"], json.dumps(c["source_refs"])))
    for e in catalog:
        db.execute("INSERT INTO entities VALUES(?,?,?,?,?,?,?,?)", tuple(e[k] for k in ["entity_id","name","zone","location_text","description","status","start_line","end_line"]))
        db.execute("INSERT INTO entity_fts VALUES(?,?,?,?,?)", (e["entity_id"], e["name"], e["zone"], e["location_text"], e["description"]))
        for v in e["categories"]: db.execute("INSERT INTO entity_categories VALUES(?,?)", (e["entity_id"], v))
        for v in e["contacts"]: db.execute("INSERT INTO entity_contacts VALUES(?,?)", (e["entity_id"], v))
    for s in sources: db.execute("INSERT INTO sources VALUES(?,?,?,?,?)", tuple(s[k] for k in ["source_number","name","title","url","review_date"]))
    db.commit(); db.close()


def main():
    text = SOURCE.read_text(encoding="utf-8")
    lines = text.splitlines()
    blocks, chunks, catalog, sources = parse_blocks(lines), None, parse_catalog(lines), parse_sources(text)
    chunks = make_chunks(blocks)
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl("blocks.jsonl", blocks); write_jsonl("chunks.jsonl", chunks); write_jsonl("catalog.jsonl", catalog); write_jsonl("faq.jsonl", parse_faq(blocks)); write_jsonl("sources.jsonl", sources)
    (OUT / "aliases.json").write_text("{}\n", encoding="utf-8")
    build_sqlite(blocks, chunks, catalog, sources)
    manifest = {"source_path": str(SOURCE.relative_to(ROOT)), "sha256": hashlib.sha256(text.encode()).hexdigest(), "ingested_at": datetime.now(timezone.utc).isoformat(), "parser_version": PARSER_VERSION, "blocks": len(blocks), "chunks": len(chunks), "catalog": len(catalog), "faq": len(parse_faq(blocks)), "sources": len(sources)}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__": main()
