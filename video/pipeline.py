#!/usr/bin/env python3
"""Pipeline video: dal girato all'MP4 finale 1080x1920 con sottotitoli impressi.

Passi (ognuno è un sottocomando, vedi CLAUDE.md per la procedura completa):

  normalizza NOME SORGENTE   audio normalizzato a -14 LUFS (loudnorm a due passate)
  trascrivi NOME             faster-whisper large-v3, italiano, timestamp per parola
  proponi-tagli NOME         genera tagli.json (pause, riempitivi, ripetizioni)
  tagli NOME                 mostra la lista tagli corrente
  sottotitoli NOME           genera NOME.srt e sottotitoli.ass (timeline già tagliata)
  bozza NOME                 primi 15 s tagliati + sottotitoli, per approvazione
  taglia NOME                NOME_tagliato.mp4 (1080x1920, senza sottotitoli)
  imprimi NOME               NOME_finale.mp4 (sottotitoli impressi)

Dipendenze: ffmpeg/ffprobe (con libass) e, solo per `trascrivi`, faster-whisper.
Tutto il resto è libreria standard. I file di lavoro stanno in video/lavori/NOME/.
"""

import argparse
import json
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

RADICE = Path(__file__).resolve().parent
LAVORI = RADICE / "lavori"

LARGHEZZA, ALTEZZA = 1080, 1920
LUFS, PICCO, LRA = -14.0, -1.5, 11.0
FPS_STANDARD = [Fraction(24000, 1001), Fraction(24), Fraction(25), Fraction(30000, 1001),
                Fraction(30), Fraction(50), Fraction(60000, 1001), Fraction(60)]
DISSOLVENZA_AUDIO = 0.008  # micro-dissolvenza a ogni giunta, evita i "click"

RIEMPITIVO = re.compile(r"^(e+h+m+|e+h{2,}|u+h*m+|m{2,}|m+h+m*|h+m+)$")
FINE_FRASE = (".", "?", "!", "…")

STILE_PREDEFINITO = {
    "cliente": "",
    "font": "Inter",
    "cartella_font": None,          # cartella con i .ttf/.otf del cliente (relativa al file di stile)
    "grassetto": True,
    "dimensione": 72,               # px su un fotogramma alto 1920
    "colore_testo": "#FFFFFF",
    "colore_contorno": "#000000",
    "spessore_contorno": 4,
    "ombra": 0,
    "sfondo": None,                 # es. {"colore": "#000000", "opacita": 0.6} per il riquadro
    "colore_evidenza": None,        # colore della parola pronunciata; None = nessuna evidenza
    "maiuscolo": False,
    "rimuovi_punteggiatura": False,  # toglie , . ; : dal testo impresso (non dal .srt)
    "allineamento": "basso",        # basso | centro | alto
    "margine_verticale_px": 420,
    "margine_laterale_px": 90,
    "max_caratteri_riga": 22,
    "max_righe": 2,
    "max_parole": None,
}


def errore(msg):
    sys.exit(f"ERRORE: {msg}")


def esegui(cmd, **kw):
    print("  $ " + " ".join(str(c) for c in cmd[:6]) + (" …" if len(cmd) > 6 else ""), flush=True)
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def cartella(nome):
    d = LAVORI / nome
    if not d.is_dir():
        errore(f"lavoro '{nome}' inesistente: parti da `normalizza {nome} SORGENTE`")
    return d


def leggi(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def scrivi(p, dati):
    Path(p).write_text(json.dumps(dati, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tempo(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


# --------------------------------------------------------------------------- 1. normalizza

def cmd_normalizza(a):
    sorgente = Path(a.sorgente).resolve()
    if not sorgente.is_file():
        errore(f"sorgente non trovata: {sorgente}")
    d = LAVORI / a.nome
    d.mkdir(parents=True, exist_ok=True)

    info = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(sorgente)],
        check=True, capture_output=True, text=True).stdout)
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if not video or not audio:
        errore("la sorgente deve avere una traccia video e una audio")

    media = Fraction(video.get("avg_frame_rate") or video["r_frame_rate"])
    fps = Fraction(a.fps) if a.fps else min(FPS_STANDARD, key=lambda f: abs(f - media))
    rotazione = next((abs(int(sd.get("rotation", 0))) for sd in video.get("side_data_list", [])
                      if "rotation" in sd), 0)
    larg, alt = int(video["width"]), int(video["height"])
    if rotazione in (90, 270):
        larg, alt = alt, larg
    if abs(larg / alt - LARGHEZZA / ALTEZZA) > 0.02:
        print(f"  ATTENZIONE: la sorgente è {larg}x{alt}, non 9:16: verrà ritagliata al centro.")
    if video.get("color_transfer") in ("arib-std-b67", "smpte2084"):
        print("  ATTENZIONE: sorgente HDR: i colori possono risultare slavati, verifica nella bozza.")

    filtro = f"aresample=async=1:first_pts=0,loudnorm=I={LUFS}:TP={PICCO}:LRA={LRA}"
    print("Misuro il volume (passata 1)…")
    r = esegui(["ffmpeg", "-hide_banner", "-nostats", "-i", sorgente, "-map", "0:a:0",
                "-af", filtro + ":print_format=json", "-f", "null", "-"],
               capture_output=True, text=True)
    m = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
    if "inf" in m["input_i"]:
        errore("l'audio della sorgente è muto")
    print(f"  volume d'origine {m['input_i']} LUFS → obiettivo {LUFS} LUFS")
    print("Normalizzo (passata 2)…")
    esegui(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", sorgente, "-map", "0:a:0",
            "-af", filtro + f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
            f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
            f":offset={m['target_offset']}:linear=true",
            "-ar", "48000", "-c:a", "flac", d / "audio_norm.flac"])

    scrivi(d / "lavoro.json", {
        "nome": a.nome, "sorgente": str(sorgente), "durata": float(info["format"]["duration"]),
        "fps": f"{fps.numerator}/{fps.denominator}", "larghezza": larg, "altezza": alt,
        "volume_origine_lufs": float(m["input_i"]),
    })
    print(f"Fatto: {d / 'audio_norm.flac'}")


# --------------------------------------------------------------------------- 2. trascrivi

def cmd_trascrivi(a):
    d = cartella(a.nome)
    try:
        from faster_whisper import WhisperModel
        import ctranslate2
    except ImportError:
        errore("faster-whisper non è installato. NON installarlo di iniziativa: "
               "chiedi prima a Chiara (pip install faster-whisper, modello large-v3 ≈ 3 GB).")
    gpu = ctranslate2.get_cuda_device_count() > 0
    print(f"Carico {a.modello} su {'GPU' if gpu else 'CPU'}…", flush=True)
    modello = WhisperModel(a.modello, device="cuda" if gpu else "cpu",
                           compute_type="float16" if gpu else "int8")
    segmenti, info = modello.transcribe(str(d / "audio_norm.flac"), language="it",
                                        word_timestamps=True, vad_filter=True, beam_size=5)
    out = []
    for s in segmenti:
        print(f"  [{tempo(s.start)}] {s.text.strip()}", flush=True)
        out.append({"inizio": round(s.start, 3), "fine": round(s.end, 3), "testo": s.text.strip(),
                    "parole": [{"inizio": round(w.start, 3), "fine": round(w.end, 3),
                                "parola": w.word.strip(), "prob": round(w.probability, 3)}
                               for w in (s.words or [])]})
    scrivi(d / "trascrizione.json", {"modello": a.modello, "lingua": "it",
                                     "durata": round(info.duration, 3), "segmenti": out})
    (d / "trascrizione.txt").write_text("\n".join(s["testo"] for s in out) + "\n", encoding="utf-8")
    print(f"Fatto: {d / 'trascrizione.json'}")


def parole_di(d):
    p = d / "trascrizione.json"
    if not p.exists():
        errore("manca trascrizione.json: esegui prima `trascrivi`")
    parole = [w for s in leggi(p)["segmenti"] for w in s["parole"] if w["parola"].strip()]
    if not parole:
        errore("la trascrizione non contiene parole")
    return parole


def normale(parola):
    return re.sub(r"[^\wàèéìòù']", "", parola.lower())


# --------------------------------------------------------------------------- 3. tagli

def cmd_proponi(a):
    d = cartella(a.nome)
    dest = d / "tagli.json"
    if dest.exists() and not a.forza:
        errore("tagli.json esiste già (può contenere modifiche manuali): usa --forza per rigenerarlo")
    lavoro, parole = leggi(d / "lavoro.json"), parole_di(d)
    durata = lavoro["durata"]
    dette = [w for w in parole if not RIEMPITIVO.match(normale(w["parola"]))]
    if not dette:
        errore("la trascrizione contiene solo riempitivi")

    def contesto(i, in_mezzo=""):
        prima = " ".join(w["parola"] for w in dette[max(0, i - 4):i + 1])
        dopo = " ".join(w["parola"] for w in dette[i + 1:i + 5])
        return f"{prima} ✂{in_mezzo} {dopo}".strip()

    tagli = []

    def aggiungi(inizio, fine, tipo, testo, attivo=True):
        inizio, fine = max(0.0, inizio), min(durata, fine)
        if fine - inizio >= a.taglio_minimo:
            tagli.append({"inizio": round(inizio, 3), "fine": round(fine, 3), "tipo": tipo,
                          "attivo": attivo, "contesto": testo})

    if dette[0]["inizio"] - a.margine_dopo >= a.soglia_bordi:
        aggiungi(0, dette[0]["inizio"] - a.margine_dopo, "testa", contesto(-1))
    for i in range(len(dette) - 1):
        w, n = dette[i], dette[i + 1]
        riemp = [x["parola"] for x in parole if RIEMPITIVO.match(normale(x["parola"]))
                 and w["fine"] <= x["inizio"] < n["inizio"]]
        if riemp:
            aggiungi(w["fine"] + a.margine_prima, n["inizio"] - a.margine_dopo, "riempitivo",
                     contesto(i, f" [{' '.join(riemp)}]"))
        elif n["inizio"] - w["fine"] >= a.soglia_pausa:
            aggiungi(w["fine"] + a.margine_prima, n["inizio"] - a.margine_dopo, "pausa", contesto(i))
        if normale(w["parola"]) == normale(n["parola"]) and len(normale(w["parola"])) >= 2:
            # proposta non attiva: "no no", "molto molto" sono spesso voluti. Decide Chiara.
            aggiungi(w["inizio"], n["inizio"], "ripetizione",
                     f"«{w['parola']}» ripetuta — {contesto(i)}", attivo=False)
    if durata - dette[-1]["fine"] - 0.25 >= a.soglia_bordi:
        aggiungi(dette[-1]["fine"] + 0.25, durata, "coda",
                 " ".join(w["parola"] for w in dette[-4:]) + " ✂")

    tagli.sort(key=lambda t: t["inizio"])
    for i, t in enumerate(tagli, 1):
        t["id"] = i
    scrivi(dest, {"approvato": False,
                  "nota": "approvato va messo a true SOLO dopo l'ok esplicito di Chiara alla lista.",
                  "tagli": [{"id": t["id"], **{k: v for k, v in t.items() if k != "id"}} for t in tagli]})
    mostra_tagli(d)


def mostra_tagli(d):
    lavoro, dati = leggi(d / "lavoro.json"), leggi(d / "tagli.json")
    print(f"\nLISTA TAGLI — {lavoro['nome']}  (approvata: {'sì' if dati['approvato'] else 'NO'})\n")
    print(f"{'#':>3}  {'da':>8} {'a':>8} {'dur.':>6}  {'tipo':<11} {'':<3} contesto")
    for t in dati["tagli"]:
        print(f"{t['id']:>3}  {tempo(t['inizio']):>8} {tempo(t['fine']):>8} "
              f"{t['fine'] - t['inizio']:>5.2f}s  {t['tipo']:<11} "
              f"{'sì' if t['attivo'] else 'no':<3} {t['contesto']}")
    tenuti, fps = montaggio(d)
    finale = float(sum(m - k for k, m in tenuti) / fps)
    attivi = sum(1 for t in dati["tagli"] if t["attivo"])
    print(f"\n{attivi} tagli attivi su {len(dati['tagli'])} proposti · "
          f"durata {tempo(lavoro['durata'])} → {tempo(finale)} "
          f"(−{lavoro['durata'] - finale:.1f}s)\n")


def cmd_tagli(a):
    mostra_tagli(cartella(a.nome))


def montaggio(d):
    """Segmenti da tenere, in fotogrammi [k, m), complementari ai tagli attivi."""
    lavoro = leggi(d / "lavoro.json")
    fps, durata = Fraction(lavoro["fps"]), lavoro["durata"]
    tagli = sorted((max(0.0, t["inizio"]), min(durata, t["fine"]))
                   for t in leggi(d / "tagli.json")["tagli"] if t["attivo"] and t["fine"] > t["inizio"])
    tenuti, cursore = [], 0.0
    for inizio, fine in tagli + [(durata, durata)]:
        if inizio > cursore:
            k, m = round(cursore * fps), round(inizio * fps)
            if m - k >= 3:  # scarta frammenti più corti di 3 fotogrammi
                tenuti.append((k, m))
        cursore = max(cursore, fine)
    if not tenuti:
        errore("i tagli attivi eliminano tutto il video")
    return tenuti, fps


def richiedi_approvazione(d):
    if not (d / "tagli.json").exists():
        errore("manca tagli.json: esegui prima `proponi-tagli`")
    if not leggi(d / "tagli.json")["approvato"]:
        errore("lista tagli non approvata. Mostrala a Chiara (`tagli NOME`), aspetta il suo ok, "
               "poi imposta \"approvato\": true in tagli.json.")


# --------------------------------------------------------------------------- 4. sottotitoli

def carica_stile(d, percorso):
    lavoro = leggi(d / "lavoro.json")
    percorso = percorso or lavoro.get("stile")
    if not percorso:
        errore("indica la guida di stile del cliente con --stile video/stili/CLIENTE.json")
    percorso = Path(percorso).resolve()
    if not percorso.is_file():
        errore(f"file di stile non trovato: {percorso}")
    dati = {k: v for k, v in leggi(percorso).items() if not k.startswith("_")}
    ignote = set(dati) - set(STILE_PREDEFINITO)
    if ignote:
        errore(f"chiavi sconosciute in {percorso.name}: {', '.join(sorted(ignote))}")
    stile = {**STILE_PREDEFINITO, **dati}
    if stile["allineamento"] not in ("basso", "centro", "alto"):
        errore("allineamento deve essere basso, centro o alto")
    if percorso.name.startswith("_"):
        print("  ATTENZIONE: stai usando lo stile di ESEMPIO, non la guida di un cliente.")
    if stile["cartella_font"]:
        stile["cartella_font"] = str((percorso.parent / stile["cartella_font"]).resolve())
        if not Path(stile["cartella_font"]).is_dir():
            errore(f"cartella_font inesistente: {stile['cartella_font']}")
    else:
        trovato = subprocess.run(["fc-match", "-f", "%{family}", stile["font"]],
                                 capture_output=True, text=True).stdout
        if stile["font"].lower() not in trovato.lower():
            print(f"  ATTENZIONE: font «{stile['font']}» non installato, ffmpeg userebbe «{trovato}». "
                  "Metti i file del font in una cartella e indicala in cartella_font.")
    lavoro["stile"] = str(percorso)
    scrivi(d / "lavoro.json", lavoro)
    return stile


def parole_montate(d):
    """Parole riportate sulla timeline del video tagliato."""
    tenuti, fps = montaggio(d)
    segmenti, scarto = [], Fraction(0)
    for k, m in tenuti:
        segmenti.append((float(k / fps), float(m / fps), float(scarto)))
        scarto += (m - k) / fps
    out, ultimo = [], 0.0
    for w in parole_di(d):
        if RIEMPITIVO.match(normale(w["parola"])):
            continue
        centro = (w["inizio"] + w["fine"]) / 2
        for inizio, fine, sc in segmenti:
            if inizio <= centro < fine:
                t0 = max(ultimo, sc + max(w["inizio"], inizio) - inizio)
                t1 = max(t0 + 0.05, sc + min(w["fine"], fine) - inizio)
                out.append({"t0": t0, "t1": t1, "testo": w["parola"].strip()})
                ultimo = t0
                break
    return out, float(scarto)


def a_capo(testi, max_car, max_righe):
    """Divide le parole in righe (liste di indici); None se non ci stanno."""
    righe, riga, lung = [], [], 0
    for i, t in enumerate(testi):
        if riga and lung + 1 + len(t) > max_car:
            righe.append(riga)
            riga, lung = [], 0
        lung += len(t) + (1 if riga else 0)
        riga.append(i)
    righe.append(riga)
    if len(righe) > max_righe or (len(testi) > 1 and any(
            len(" ".join(testi[i] for i in r)) > max_car for r in righe)):
        return None
    if len(righe) == 2:  # bilancia le due righe
        def sbilancio(c):
            return abs(len(" ".join(testi[:c])) - len(" ".join(testi[c:])))
        validi = [c for c in range(1, len(testi)) if len(" ".join(testi[:c])) <= max_car
                  and len(" ".join(testi[c:])) <= max_car]
        c = min(validi, key=sbilancio)
        righe = [list(range(c)), list(range(c, len(testi)))]
    return righe


def blocchi_sottotitoli(parole, durata, stile):
    max_car, max_righe = stile["max_caratteri_riga"], stile["max_righe"]

    def ci_sta(gruppo):
        return (not stile["max_parole"] or len(gruppo) <= stile["max_parole"]) and (
            len(gruppo) == 1 or a_capo([w["testo"] for w in gruppo], max_car, max_righe) is not None)

    def lunghezza(gruppo):
        return len(" ".join(w["testo"] for w in gruppo))

    def dividi(frase, obiettivo=None):
        """Spezza una frase in blocchi; con `obiettivo` chiude ogni blocco appena lo raggiunge."""
        gruppi, cur = [], []
        for w in frase:
            if cur and (not ci_sta(cur + [w]) or (obiettivo and lunghezza(cur) >= obiettivo)):
                gruppi.append(cur)
                cur = []
            cur.append(w)
        return gruppi + [cur]

    # 1) frasi: si chiudono su punteggiatura forte o su una pausa
    frasi, cur = [], []
    for w in parole:
        if cur and (w["t0"] - cur[-1]["t1"] > 0.6 or cur[-1]["testo"].endswith(FINE_FRASE)):
            frasi.append(cur)
            cur = []
        cur.append(w)
    if cur:
        frasi.append(cur)
    # 2) ogni frase nel minor numero di blocchi, di lunghezza simile (niente parole orfane)
    blocchi = []
    for frase in frasi:
        gruppi = dividi(frase)
        if len(gruppi) > 1:
            bilanciati = dividi(frase, lunghezza(frase) / len(gruppi) - 3)
            if len(bilanciati) == len(gruppi):
                gruppi = bilanciati
        for g in gruppi:
            righe = a_capo([w["testo"] for w in g], max_car, max_righe)
            blocchi.append({"parole": g, "righe": righe or [list(range(len(g)))]})
    for i, b in enumerate(blocchi):
        b["inizio"] = b["parole"][0]["t0"]
        limite = blocchi[i + 1]["parole"][0]["t0"] if i + 1 < len(blocchi) else durata
        b["fine"] = max(b["inizio"] + 0.05, min(limite, max(b["parole"][-1]["t1"] + 0.15, b["inizio"] + 0.4)))
    return blocchi


def colore_ass(esadecimale, opacita=1.0):
    h = esadecimale.lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        errore(f"colore non valido: {esadecimale}")
    return f"&H{round((1 - opacita) * 255):02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def genera_sottotitoli(d, percorso_stile):
    nome = leggi(d / "lavoro.json")["nome"]
    stile = carica_stile(d, percorso_stile)
    parole, durata = parole_montate(d)
    blocchi = blocchi_sottotitoli(parole, durata, stile)

    def srt_t(t):
        ms = round(t * 1000)
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    srt = []
    for i, b in enumerate(blocchi, 1):
        testo = "\n".join(" ".join(b["parole"][j]["testo"] for j in r) for r in b["righe"])
        srt.append(f"{i}\n{srt_t(b['inizio'])} --> {srt_t(b['fine'])}\n{testo}\n")
    (d / f"{nome}.srt").write_text("\n".join(srt), encoding="utf-8")

    def ass_t(t):
        cs = round(t * 100)
        return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"

    def vista(testo):
        if stile["rimuovi_punteggiatura"]:
            testo = re.sub(r"[,.;:]+(?=$|\s)", "", testo)
        if stile["maiuscolo"]:
            testo = testo.upper()
        return testo.replace("\\", "").replace("{", "(").replace("}", ")")

    def riga_ass(b, attiva=None):
        return r"\N".join(" ".join(
            (f"{{\\c{evidenza}}}{vista(b['parole'][j]['testo'])}{{\\c{primario_inline}}}" if j == attiva
             else vista(b["parole"][j]["testo"])) for j in r) for r in b["righe"])

    primario = colore_ass(stile["colore_testo"])
    def inline(esadecimale):  # &HBBGGRR& per i cambi di colore dentro la riga
        c = colore_ass(esadecimale)
        return c[:2] + c[4:] + "&"

    primario_inline = inline(stile["colore_testo"])
    evidenza = inline(stile["colore_evidenza"]) if stile["colore_evidenza"] else None
    sfondo = stile["sfondo"]
    contorno = colore_ass(sfondo["colore"], sfondo.get("opacita", 1.0)) if sfondo \
        else colore_ass(stile["colore_contorno"])
    allineamento = {"basso": 2, "centro": 5, "alto": 8}[stile["allineamento"]]
    eventi = []
    for b in blocchi:
        if evidenza:
            for j, w in enumerate(b["parole"]):
                t0 = b["inizio"] if j == 0 else w["t0"]
                t1 = b["parole"][j + 1]["t0"] if j + 1 < len(b["parole"]) else b["fine"]
                if t1 > t0:
                    eventi.append(f"Dialogue: 0,{ass_t(t0)},{ass_t(t1)},Sub,,0,0,0,,{riga_ass(b, j)}")
        else:
            eventi.append(f"Dialogue: 0,{ass_t(b['inizio'])},{ass_t(b['fine'])},Sub,,0,0,0,,{riga_ass(b)}")
    (d / "sottotitoli.ass").write_text(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {LARGHEZZA}
PlayResY: {ALTEZZA}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{stile['font']},{stile['dimensione']},{primario},{primario},{contorno},&H80000000,{-1 if stile['grassetto'] else 0},0,0,0,100,100,0,0,{3 if sfondo else 1},{stile['spessore_contorno']},{stile['ombra']},{allineamento},{stile['margine_laterale_px']},{stile['margine_laterale_px']},{stile['margine_verticale_px']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(eventi) + "\n", encoding="utf-8")
    print(f"Sottotitoli: {len(blocchi)} blocchi → {d / (nome + '.srt')}")
    return stile


def cmd_sottotitoli(a):
    d = cartella(a.nome)
    richiedi_approvazione(d)
    genera_sottotitoli(d, a.stile)


# --------------------------------------------------------------------------- 5. taglia / imprimi

CODIFICA_AUDIO = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]


def codifica_video(crf, preset):
    return ["-c:v", "libx264", "-preset", preset, "-crf", crf, "-profile:v", "high",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart"]


def taglia(d, uscita, limite=None):
    lavoro = leggi(d / "lavoro.json")
    tenuti, fps = montaggio(d)
    n = len(tenuti)
    r = f"{fps.numerator}/{fps.denominator}"
    f = [f"[0:v]fps={r}:start_time=0,scale={LARGHEZZA}:{ALTEZZA}:force_original_aspect_ratio=increase,"
         f"crop={LARGHEZZA}:{ALTEZZA},setsar=1,format=yuv420p,split={n}" + "".join(f"[v{i}]" for i in range(n)),
         f"[1:a]asplit={n}" + "".join(f"[a{i}]" for i in range(n))]
    for i, (k, m) in enumerate(tenuti):
        dur = float((m - k) / fps)
        # mezzo fotogramma di anticipo: i bordi cadono tra due fotogrammi, mai sopra uno
        f.append(f"[v{i}]trim=start={float((k - Fraction(1, 2)) / fps):.6f}:"
                 f"end={float((m - Fraction(1, 2)) / fps):.6f},setpts=PTS-STARTPTS[vt{i}]")
        f.append(f"[a{i}]atrim=start={float(k / fps):.6f}:end={float(m / fps):.6f},asetpts=PTS-STARTPTS,"
                 f"afade=t=in:d={DISSOLVENZA_AUDIO},"
                 f"afade=t=out:st={dur - DISSOLVENZA_AUDIO:.6f}:d={DISSOLVENZA_AUDIO}[at{i}]")
    f.append("".join(f"[vt{i}][at{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]")
    (d / "filtro_taglio.txt").write_text(";\n".join(f) + "\n", encoding="utf-8")
    esegui(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", lavoro["sorgente"], "-i", d / "audio_norm.flac",
            "-filter_complex_script", d / "filtro_taglio.txt", "-map", "[v]", "-map", "[a]",
            *codifica_video("16", "medium"), "-r", r, *CODIFICA_AUDIO,
            *(["-t", str(limite)] if limite else []), uscita])


def imprimi(d, ingresso, uscita, stile):
    def proteggi(p):
        return str(p).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")
    filtro = "ass=filename=sottotitoli.ass"
    if stile["cartella_font"]:
        filtro += f":fontsdir={proteggi(stile['cartella_font'])}"
    esegui(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", Path(ingresso).resolve(),
            "-vf", filtro, *codifica_video("18", "slow"), "-c:a", "copy", Path(uscita).resolve()], cwd=d)


def cmd_bozza(a):
    d = cartella(a.nome)
    richiedi_approvazione(d)
    stile = genera_sottotitoli(d, a.stile)
    provvisorio, uscita = d / "_bozza_tagliato.mp4", d / f"{a.nome}_bozza{a.secondi}s.mp4"
    taglia(d, provvisorio, limite=a.secondi)
    imprimi(d, provvisorio, uscita, stile)
    provvisorio.unlink()
    print(f"Bozza pronta: {uscita}\nMostrala a Chiara e aspetta il suo ok prima di `taglia` e `imprimi`.")


def cmd_taglia(a):
    d = cartella(a.nome)
    richiedi_approvazione(d)
    uscita = d / f"{a.nome}_tagliato.mp4"
    taglia(d, uscita)
    print(f"Video tagliato (senza sottotitoli): {uscita}")


def cmd_imprimi(a):
    d = cartella(a.nome)
    richiedi_approvazione(d)
    tagliato = d / f"{a.nome}_tagliato.mp4"
    if not tagliato.exists():
        errore("manca il video tagliato: esegui prima `taglia`")
    if tagliato.stat().st_mtime < (d / "tagli.json").stat().st_mtime:
        errore("tagli.json è stato modificato dopo il taglio: riesegui `taglia`")
    stile = genera_sottotitoli(d, a.stile)
    uscita = d / f"{a.nome}_finale.mp4"
    imprimi(d, tagliato, uscita, stile)
    print(f"\nConsegna in {d}:\n  {uscita.name}  (finale, sottotitoli impressi)\n"
          f"  {tagliato.name}  (tagliato, senza sottotitoli)\n  {a.nome}.srt")


# --------------------------------------------------------------------------- CLI

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="comando", required=True)

    def comando(nome, funzione, stile=False):
        s = sub.add_parser(nome)
        s.add_argument("nome", help="nome del lavoro (cartella in video/lavori/)")
        if stile:
            s.add_argument("--stile", help="file JSON della guida di stile del cliente "
                                           "(ricordato dopo il primo uso)")
        s.set_defaults(funzione=funzione)
        return s

    s = comando("normalizza", cmd_normalizza)
    s.add_argument("sorgente")
    s.add_argument("--fps", help="forza i fotogrammi al secondo (default: quelli della sorgente)")
    s = comando("trascrivi", cmd_trascrivi)
    s.add_argument("--modello", default="large-v3")
    s = comando("proponi-tagli", cmd_proponi)
    s.add_argument("--soglia-pausa", type=float, default=0.7, help="pausa minima da tagliare (s)")
    s.add_argument("--soglia-bordi", type=float, default=0.3, help="silenzio minimo a inizio/fine (s)")
    s.add_argument("--margine-prima", type=float, default=0.12, help="respiro dopo l'ultima parola (s)")
    s.add_argument("--margine-dopo", type=float, default=0.08, help="respiro prima della parola dopo (s)")
    s.add_argument("--taglio-minimo", type=float, default=0.15, help="ignora tagli più corti (s)")
    s.add_argument("--forza", action="store_true", help="sovrascrive tagli.json esistente")
    comando("tagli", cmd_tagli)
    comando("sottotitoli", cmd_sottotitoli, stile=True)
    s = comando("bozza", cmd_bozza, stile=True)
    s.add_argument("--secondi", type=int, default=15)
    comando("taglia", cmd_taglia)
    comando("imprimi", cmd_imprimi, stile=True)

    a = p.parse_args()
    if not re.fullmatch(r"[\w-]+", a.nome):
        errore("il nome del lavoro può contenere solo lettere, numeri, - e _")
    try:
        a.funzione(a)
    except subprocess.CalledProcessError as e:
        errore(f"comando fallito ({e.returncode}): {' '.join(map(str, e.cmd[:3]))} …\n{e.stderr or ''}")


if __name__ == "__main__":
    main()
