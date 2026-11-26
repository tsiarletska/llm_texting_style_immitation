#!/usr/bin/env python3
"""Style-imitation test harness (standard library only).

For every enabled model x scenario x mode x run it asks the model to write O.'s reply.
Outputs (in results/):
  results/run_<stamp>/blind.csv  item_id, scenario_id, mode, reply          <- give THIS to the friends
  results/run_<stamp>/key.csv    item_id, model name, provider, run, latency <- keep this to yourself

Modes
  examples  the system prompt contains real examples of O.'s messages
  baseline  no examples (shows what the data adds)

API keys are read from environment variables, ~/.config/cognition.env or <project>/.env
(KEY=VALUE per line, e.g. GROQ_API_KEY=...). .env is git-ignored: never commit it.

Example data is read from data/ (your own, git-ignored); if a file is missing there,
the tiny public sample in examples/ is used instead.

Usage
  python3 code/imitate.py --list-models groq
  python3 code/imitate.py --dry-run
  python3 code/imitate.py --providers groq --runs 3
"""
import argparse, csv, json, os, pathlib, random, re, sys, time, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CODE = ROOT / "code"
KEYFILE = pathlib.Path.home() / ".config" / "cognition.env"
UA = "cognition-style-test/0.1"

PROVIDERS = {  # openai-compatible ones share one code path
    "groq":      {"kind": "openai", "base": "https://api.groq.com/openai/v1",  "key": "GROQ_API_KEY"},
    "openai":    {"kind": "openai", "base": "https://api.openai.com/v1",       "key": "OPENAI_API_KEY"},
    "mistral":   {"kind": "openai", "base": "https://api.mistral.ai/v1",       "key": "MISTRAL_API_KEY"},
    "mamay":     {"kind": "openai", "base": "https://api.mamay.ai/v1", "key": "MAMAY_API_KEY"},   # INSAIT hosted MamayLM
    "runpod":    {"kind": "openai", "base_env": "VLLM_BASE_URL", "key": "RUNPOD_VLLM_KEY"},   # vLLM on a Runpod pod
    "anthropic": {"kind": "anthropic", "key": "ANTHROPIC_API_KEY"},
    "gemini":    {"kind": "gemini",    "key": "GEMINI_API_KEY"},
}


ALIASES = {"CLAUDE": "ANTHROPIC_API_KEY", "MAMAY": "MAMAY_API_KEY", "GROQ": "GROQ_API_KEY", "ANTHROPIC": "ANTHROPIC_API_KEY", "GEMINI": "GEMINI_API_KEY",
           "OPENAI": "OPENAI_API_KEY", "MISTRAL": "MISTRAL_API_KEY"}


def base_of(p):
    return p.get("base") or os.environ["VLLM_BASE_URL"].rstrip("/")


def load_keys():
    """Read KEY=VALUE lines from ~/.config/cognition.env and <project>/.env (short names allowed)."""
    for f in (KEYFILE, ROOT / ".env"):
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = ALIASES.get(k.strip(), k.strip())
                os.environ.setdefault(k, v.strip().strip('"').strip("'"))


def http(url, headers, body=None, timeout=90):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json", "User-Agent": UA, **headers})
    for attempt in range(8):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            if e.code == 429 and attempt < 7:          # rate limit: wait as long as the server asks
                m = re.search(r"try again in ([\d.]+)\s*(ms|s)", msg)
                wait = (float(m.group(1)) / (1000 if m and m.group(2) == "ms" else 1) if m else 10) + 1
                time.sleep(min(wait, 60))
                continue
            raise RuntimeError(f"HTTP {e.code}: {msg[:300]}") from None


def call(provider, model, system, user, temperature, max_tokens, extra=None):
    p = PROVIDERS[provider]
    key = os.environ.get(p["key"])
    if not key:
        raise RuntimeError(f"{p['key']} is not set")
    if p["kind"] == "openai":
        body = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                **(extra or {})}
        r = http(base_of(p) + "/chat/completions", {"Authorization": "Bearer " + key}, body)
        return r["choices"][0]["message"]["content"]
    if p["kind"] == "anthropic":
        body = {"model": model, "max_tokens": max_tokens,   # temperature is deprecated on current Claude models
                "system": system, "messages": [{"role": "user", "content": user}]}
        r = http("https://api.anthropic.com/v1/messages",
                 {"x-api-key": key, "anthropic-version": "2023-06-01"}, body)
        return "".join(b.get("text", "") for b in r["content"])
    if p["kind"] == "gemini":
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
        r = http(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                 {"x-goog-api-key": key}, body)
        return "".join(x.get("text", "") for x in r["candidates"][0]["content"]["parts"])
    raise ValueError(provider)


def list_models(provider):
    p = PROVIDERS[provider]
    key = os.environ.get(p["key"])
    if not key:
        sys.exit(f"{p['key']} is not set")
    if p["kind"] == "openai":
        r = http(base_of(p) + "/models", {"Authorization": "Bearer " + key})
        print("\n".join(sorted(m["id"] for m in r["data"])))
    elif p["kind"] == "anthropic":
        r = http("https://api.anthropic.com/v1/models", {"x-api-key": key, "anthropic-version": "2023-06-01"})
        print("\n".join(m["id"] for m in r["data"]))
    else:
        r = http("https://generativelanguage.googleapis.com/v1beta/models", {"x-goog-api-key": key})
        print("\n".join(m["name"] for m in r["models"]))


# ---------- prompt building ----------
def data_file(name):
    """Your own data in data/ wins; otherwise fall back to the public sample in examples/."""
    own = ROOT / "data" / name
    return own if own.exists() else ROOT / "examples" / name


def load_examples():
    pairs, singles = [], []
    sd = data_file("style_data.csv")
    if sd.exists():
        for r in csv.DictReader(open(sd, encoding="utf-8")):
            if r["id"].startswith("P"):          # prompts to AI are a different register
                continue
            ctx = r["context_summary_of_other_side"].strip()
            pairs.append((r["lang"], ctx, r["o_reply"].strip()))
    ig = data_file("instagram_sample_500.csv")
    if ig.exists():
        for r in csv.DictReader(open(ig, encoding="utf-8")):
            singles.append((r["lang"], r["text"].strip()))
    return pairs, singles


def build_system(mode, lang, pairs, singles, n_pairs, n_singles, rnd):
    base = ("You are taking part in a writing-style experiment. Write the reply that a specific person, 'O.', "
            "would send in a chat. Output ONLY the message text. If O. would send several short messages, "
            "put each on its own line. No quotation marks, no explanations, no labels.")
    if mode == "baseline":
        return base + " O. is a casual texter. Reply naturally in the same language as the incoming message."
    pool_p = [p for p in pairs if p[0].startswith(lang)] or pairs
    pool_s = [s for s in singles if s[0] == lang] or singles
    ex_p = rnd.sample(pool_p, min(n_pairs, len(pool_p)))
    ex_s = rnd.sample(pool_s, min(n_singles, len(pool_s)))
    out = [base, "", "Study O.'s real messages closely: language mixing, slang, length, punctuation, capitalisation, "
           "emoji, typos, bursts of short messages. Imitate them. Do not copy any example verbatim. "
           "Square-bracket tokens such as [name] or [city] are redaction marks in the data: never output them.", ""]
    if ex_p:
        out.append("Real examples (situation summary -> O.'s message):")
    for _, ctx, reply in ex_p:
        ctx = ctx if ctx and not ctx.startswith("(") else "(O. starts the conversation)"
        out.append(f"- {ctx}\n  O.: " + reply.replace("\n", "\n      "))
    out += ["", "O.'s messages, without context:" if not ex_p else "More of O.'s messages, without context:"]
    out += [f"- {t}" for _, t in ex_s]
    return "\n".join(out)


def clean(t):
    """Strip markdown hard line breaks and stray whitespace from model output."""
    t = re.sub(r"[ \t]+\n", "\n", t.replace("\r", ""))
    return t.strip()


def build_user(sc):
    return f"Situation: {sc['situation']}.\nThe other person writes:\n{sc['incoming']}\n\nWrite O.'s reply."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", help="comma list; default = all enabled in models.json")
    ap.add_argument("--models", help="comma list of model names from models.json")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--modes", default="examples,baseline")
    ap.add_argument("--label", help="name for this setting in the output (default: the mode name)")
    ap.add_argument("--id-prefix", default="R", help="prefix for item ids, so rounds never collide")
    ap.add_argument("--n-pairs", type=int, default=25)
    ap.add_argument("--n-singles", type=int, default=40)
    ap.add_argument("--scenarios", help="comma list of scenario ids; default = all")
    ap.add_argument("--rating-set", action="store_true", help="only scenarios marked rating_set (for the friends)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true", help="print one prompt and exit; no API calls")
    ap.add_argument("--list-models", metavar="PROVIDER")
    a = ap.parse_args()
    load_keys()
    if a.list_models:
        return list_models(a.list_models)

    cfg = json.load(open(CODE / "models.json"))
    scenarios = json.load(open(CODE / "scenarios.json"))
    if a.scenarios:
        want = set(a.scenarios.split(","))
        scenarios = [s for s in scenarios if s["id"] in want]
    if a.rating_set:
        scenarios = [s for s in scenarios if s.get("rating_set")]
    named = set(a.models.split(",")) if a.models else None
    models = [m for m in cfg["models"]
              if m["model"] != "FILL_ME" and (m["name"] in named if named else m["enabled"])]
    if named and not models:
        sys.exit("no model named " + a.models + " found in models.json")
    if a.providers:
        want = set(a.providers.split(","))
        models = [m for m in models if m["provider"] in want]
    pairs, singles = load_examples()
    rnd = random.Random(a.seed)

    if a.dry_run:
        sc = scenarios[0]
        print("=== SYSTEM (examples mode) ===")
        print(build_system("examples", sc["lang"], pairs, singles, a.n_pairs, a.n_singles, rnd))
        print("\n=== USER ===\n" + build_user(sc))
        print(f"\n[{len(pairs)} context pairs, {len(singles)} Instagram samples available; "
              f"{len(models)} model(s) enabled: {[m['name'] for m in models]}]")
        return

    stamp = time.strftime("%Y%m%d_%H%M%S")
    outdir = ROOT / "results" / f"run_{stamp}"
    outdir.mkdir(parents=True, exist_ok=True)
    blind, key = [], []
    n = 0
    for m in models:
        for sc in scenarios:
            for mode in a.modes.split(","):
                for run in range(1, a.runs + 1):
                    system = build_system(mode, sc["lang"], pairs, singles, a.n_pairs, a.n_singles, rnd)
                    t0 = time.time()
                    try:
                        reply = ""
                        for _try in range(3):               # reasoning models sometimes return nothing
                            reply = clean(call(m["provider"], m["model"], system, build_user(sc),
                                               cfg["temperature"], m.get("max_tokens", cfg["max_tokens"]),
                                               m.get("extra")))
                            if reply:
                                break
                    except Exception as e:
                        print(f"! {m['name']} {sc['id']} {mode} run{run}: {e}", file=sys.stderr)
                        continue
                    n += 1
                    iid = f"{a.id_prefix}{n:04d}"
                    blind.append({"item_id": iid, "scenario_id": sc["id"], "mode": a.label or mode, "reply": reply})
                    key.append({"item_id": iid, "model_name": m["name"], "provider": m["provider"],
                                "model": m["model"], "run": run, "latency_s": round(time.time() - t0, 2),
                                "n_pairs": a.n_pairs if mode == "examples" else 0,
                                "n_singles": a.n_singles if mode == "examples" else 0})
                    print(f"{iid} {m['name']:<16} {sc['id']:<14} {mode:<8} run{run} ok")
                    time.sleep(m.get("sleep", 0.3))
    random.Random(a.seed).shuffle(blind)
    with open(outdir / "blind.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["item_id", "scenario_id", "mode", "reply"])
        w.writeheader(); w.writerows(blind)
    with open(outdir / "key.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(key[0].keys()) if key else ["item_id"])
        w.writeheader(); w.writerows(key)
    print(f"\n{n} replies -> results/run_{stamp}/blind.csv (show friends) and key.csv (keep private)")


if __name__ == "__main__":
    main()
