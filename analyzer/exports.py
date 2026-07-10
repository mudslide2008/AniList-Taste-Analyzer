
from __future__ import annotations
import csv, json
from datetime import datetime

def write_csv(rows, path):
    fields=["id","title","romaji","rating","rating100","score_format","status","format","episodes","duration","year","source","genres","tags","studios","community_score","popularity","started","completed","repeat","url"]
    with path.open("w",encoding="utf-8-sig",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields); writer.writeheader()
        for row in sorted(rows,key=lambda r:(-(r.get("rating") or 0),r["title"].lower())):
            export={key:row.get(key,"") for key in fields}
            for key in ("genres","tags","studios"): export[key]=" | ".join(export[key])
            writer.writerow(export)

def write_json(user, rows, path):
    with path.open("w",encoding="utf-8") as handle:
        json.dump({"generated_at":datetime.now().isoformat(),"user":user,"anime":rows},handle,ensure_ascii=False,indent=2)
