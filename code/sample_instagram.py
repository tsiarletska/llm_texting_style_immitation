#!/usr/bin/env python3
"""Pick a balanced sample of O's Instagram messages for the style examples.

Reads  instagram_O_messages.csv  (already filtered, anonymised thread labels).
Writes instagram_sample_500.csv

Balancing: round-robin across threads so one chat (T23 is ~40% of the data) cannot dominate.
Messages that might contain a person's name (capitalised word inside a sentence) are skipped;
the remaining sample should still be skimmed by hand before it is sent to any provider.
"""
import csv, random, re, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "instagram_O_messages.csv"
OUT = ROOT / "data" / "instagram_sample_500.csv"
N, SEED, MIN_WORDS = 500, 7, 2

CAP = re.compile(r"(?<![.!?\n]\s)(?<!^)\b[A-ZА-ЯІЇЄҐ][a-zа-яіїєґ']{2,}")

rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
pool = collections.defaultdict(list)
for r in rows:
    if len(r["text"].split()) < MIN_WORDS or CAP.search(r["text"]):
        continue
    pool[r["thread"]].append(r)

rnd = random.Random(SEED)
for v in pool.values():
    rnd.shuffle(v)

picked = []
while len(picked) < N and any(pool.values()):
    for t in sorted(pool):
        if pool[t] and len(picked) < N:
            picked.append(pool[t].pop())

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(picked)

print(len(picked), "messages ->", OUT.name)
print("per thread:", dict(collections.Counter(r["thread"] for r in picked).most_common()))
print("language:", dict(collections.Counter(r["lang"] for r in picked)))
