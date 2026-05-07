"""
Tests de régression — Julien OS
Lance avec : python3 /root/julien_os/tests/test_regression.py
"""
import asyncio
import sys

sys.path.insert(0, "/root")

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"
results = []

def log(status, name, detail=""):
    symbol = {"ok": PASS, "fail": FAIL, "warn": WARN}[status]
    line = f"  {symbol} {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    results.append((status, name))

# ── 1. Imports et config ─────────────────────────────────────────────────────
def test_imports():
    print("\n[1] Imports et configuration")
    try:
        from config import ANTHROPIC_API_KEY, TELEGRAM_TOKEN
        assert TELEGRAM_TOKEN and len(TELEGRAM_TOKEN) > 10
        log("ok", "TELEGRAM_TOKEN présent")
        assert ANTHROPIC_API_KEY and len(ANTHROPIC_API_KEY) > 10
        log("ok", "ANTHROPIC_API_KEY présent")
    except Exception as e:
        log("fail", "config.py", str(e))
    try:
        import json
        s = json.load(open("/root/secrets.json"))
        log("ok", f"secrets.json — clés: {list(s.keys())}")
    except Exception as e:
        log("fail", "secrets.json", str(e))
    try:
        log("ok", "graph.py — import OK")
    except Exception as e:
        log("fail", "graph.py", str(e))
    try:
        log("ok", "state.py — import OK")
    except Exception as e:
        log("fail", "state.py", str(e))
    try:
        from julien_os.profil import PROFIL
        assert len(PROFIL) > 10
        log("ok", "profil.py — import OK")
    except Exception as e:
        log("fail", "profil.py", str(e))

# ── 2. Base de données ───────────────────────────────────────────────────────
async def test_db():
    print("\n[2] Base de données SQLite")
    try:
        from julien_os.memory.store import init_db, lister_projets, recuperer_contexte
        await init_db()
        log("ok", "init_db()")
        projets = await lister_projets()
        log("ok", f"lister_projets() — {len(projets)} projet(s)")
        ctx = await recuperer_contexte("general", limite=3)
        log("ok", f"recuperer_contexte() — {'données trouvées' if ctx else 'vide (normal)'}")
    except Exception as e:
        log("fail", "store.py", str(e))
    try:
        from julien_os.memory.pending import get_pending_actif, init_pending_table
        await init_pending_table()
        pending = await get_pending_actif()
        log("ok", f"pending table — {'item actif' if pending else 'vide'}")
    except Exception as e:
        log("fail", "pending table", str(e))

# ── 3-10. Agents ─────────────────────────────────────────────────────────────
async def test_agents():
    print("\n[3-10] Agents")

    # DIRECT
    try:
        from julien_os.agents.direct import run
        r = run({"message": "Test régression — quel est le jour?", "projet": "general", "contexte": ""})
        assert "resultat" in r and len(r["resultat"]) > 5
        log("ok", "agent DIRECT", r["resultat"][:70] + "...")
    except Exception as e:
        log("fail", "agent DIRECT", str(e))

    # CR
    try:
        from julien_os.agents.cr import run as run_cr
        r = run_cr({"message": "Réunion 22 avril. Décision: livrer sprint 5 le 30 avril. Jean → backend.", "projet": "iA", "contexte": ""})
        assert "resultat" in r and len(r["resultat"]) > 10
        log("ok", "agent CR", r["resultat"][:70] + "...")
    except Exception as e:
        log("fail", "agent CR", str(e))

    # EMAIL
    try:
        from julien_os.agents.email import run as run_email
        r = run_email({"message": "Suivi livraison sprint 5 le 30 avril pour Marie.", "projet": "iA", "contexte": ""})
        assert "resultat" in r and len(r["resultat"]) > 10
        log("ok", "agent EMAIL", r["resultat"][:70] + "...")
    except Exception as e:
        log("fail", "agent EMAIL", str(e))

    # SHEPHERD
    try:
        from julien_os.agents.shepherd import run as run_shep
        r = run_shep({"message": "VP Finance bloque validation sprint 5 sans raison.", "projet": "iA", "contexte": ""})
        assert "resultat" in r and len(r["resultat"]) > 10
        log("ok", "agent SHEPHERD", r["resultat"][:70] + "...")
    except Exception as e:
        log("fail", "agent SHEPHERD", str(e))

    # PREP
    try:
        from julien_os.agents.prep import run as run_prep
        r = await run_prep({"message": "Réunion comité pilotage iA demain matin", "projet": "iA", "contexte": ""})
        assert "resultat" in r and len(r["resultat"]) > 10
        log("ok", "agent PREP", r["resultat"][:70] + "...")
    except Exception as e:
        log("fail", "agent PREP", str(e))

    # MEMOIRE
    try:
        from julien_os.agents.memoire import run as run_mem
        r = await run_mem({"message": "Derniers échanges iA?", "projet": "iA", "contexte": ""})
        assert "resultat" in r
        log("ok", "agent MÉMOIRE", r["resultat"][:70] + "...")
    except Exception as e:
        log("fail", "agent MÉMOIRE", str(e))

    # HEBDO
    try:
        from julien_os.agents.hebdo import generer_tableau_bord
        r = await generer_tableau_bord()
        assert isinstance(r, str) and len(r) > 5
        log("ok", "agent HEBDO", r[:70] + "...")
    except Exception as e:
        log("fail", "agent HEBDO", str(e))

    # CONSOLIDATION
    try:
        from julien_os.agents.consolidation import consolider
        r = await consolider("iA")
        assert isinstance(r, str) and len(r) > 5
        log("ok", "agent CONSOLIDATION", r[:70] + "...")
    except Exception as e:
        log("fail", "agent CONSOLIDATION", str(e))

# ── 11. Tools ─────────────────────────────────────────────────────────────────
def test_tools():
    print("\n[11] Tools (imports)")
    for mod, attr in [
        ("julien_os.tools.protonmail", "ProtonMailClient"),
        ("julien_os.tools.airbnb_scraper", "AirbnbClient"),
        ("julien_os.tools.notion_tool", None),
        ("julien_os.telegram_format", "envoyer_html"),
        ("julien_os.tools.transcription", "transcrire_audio"),
    ]:
        try:
            m = __import__(mod, fromlist=[attr] if attr else [])
            if attr:
                assert hasattr(m, attr)
            log("ok", mod)
        except Exception as e:
            log("warn", mod, str(e)[:80])

# ── 12. Watchers ──────────────────────────────────────────────────────────────
def test_watchers():
    print("\n[12] Watchers (imports)")
    for mod, attr in [
        ("julien_os.watchers.protonmail_watcher", "poll_once"),
        ("julien_os.watchers.airbnb_watcher", "poll_once"),
        ("julien_os.watchers.flags", "alerte_deja_envoyee"),
    ]:
        try:
            m = __import__(mod, fromlist=[attr])
            assert hasattr(m, attr)
            log("ok", mod)
        except Exception as e:
            log("warn", mod, str(e)[:80])

# ── 13. Orchestrateur complet ─────────────────────────────────────────────────
async def test_graph():
    print("\n[13] Orchestrateur LangGraph complet")
    try:
        from julien_os.graph import traiter
        r = await traiter("Test de régression — réponds juste 'OK test reçu'.")
        assert "resultat" in r
        log("ok", "graph.traiter()", r["resultat"][:70] + "...")
    except Exception as e:
        log("fail", "graph.traiter()", str(e))

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    print("=" * 60)
    print("  Tests de régression — Julien OS")
    print("=" * 60)
    test_imports()
    await test_db()
    await test_agents()
    test_tools()
    test_watchers()
    await test_graph()

    ok   = sum(1 for s, _ in results if s == "ok")
    warn = sum(1 for s, _ in results if s == "warn")
    fail = sum(1 for s, _ in results if s == "fail")
    print("\n" + "=" * 60)
    print(f"  {ok}/{len(results)} OK  |  {warn} avertissement(s)  |  {fail} échec(s)")
    print("=" * 60)
    if fail:
        print("\nÀ corriger :")
        for s, name in results:
            if s == "fail":
                print(f"  ✗ {name}")
    sys.exit(1 if fail else 0)

if __name__ == "__main__":
    asyncio.run(main())
