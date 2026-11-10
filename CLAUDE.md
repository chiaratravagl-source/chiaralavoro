# chiaralavoro

Repo di lavoro di Chiara. Contiene:

- `index.html`, `programmasocialdisuccesso.html`, `BRIEF.md` — landing page "Social di Successo".
- `video/` — pipeline di montaggio video (vedi sotto).

## Pipeline video

**CapCut non si usa più.** La pipeline produce direttamente l'MP4 finale con `ffmpeg`,
tramite `video/pipeline.py` (solo libreria standard + ffmpeg; `faster-whisper` serve
soltanto per la trascrizione).

### Regole fisse

- **Non installare nulla senza chiedere prima a Chiara** (pacchetti pip/apt, modelli, font).
  Se manca qualcosa (`faster-whisper`, il modello `large-v3`, il font del cliente), fermati e chiedi.
- **Due approvazioni obbligatorie**, sempre esplicite e in quest'ordine:
  1. la **lista tagli**, prima di tagliare qualsiasi cosa;
  2. la **bozza dei primi 15 secondi**, prima del render completo.
- **Consegna sempre tre file**: MP4 finale con sottotitoli impressi, MP4 tagliato **senza**
  sottotitoli, file `.srt`.
- I sottotitoli seguono la **guida di stile del cliente** (`video/stili/CLIENTE.json`).
  Non inventare lo stile: se la guida del cliente non c'è, chiedila. `_esempio.json` è solo un modello.
- Formato finale: **1080x1920**, H.264 + AAC, audio a −14 LUFS.

### Procedura

`NOME` è il nome del lavoro (lettere, numeri, `-`, `_`); i file finiscono in
`video/lavori/NOME/` (cartella ignorata da git: il girato e i render non vanno nel repo).

1. **Normalizza l'audio**
   `python3 video/pipeline.py normalizza NOME /percorso/girato.mp4`
   Loudnorm a due passate → `audio_norm.flac`. Leggi gli avvisi (sorgente non 9:16, HDR).
2. **Trascrivi**
   `python3 video/pipeline.py trascrivi NOME`
   faster-whisper `large-v3`, italiano, timestamp per parola → `trascrizione.json` e `.txt`.
   Rileggi la trascrizione e correggi gli errori (nomi propri, marchi, termini tecnici)
   nel campo `parola` di `trascrizione.json`: `.srt` e sottotitoli impressi nascono da lì.
3. **Proponi i tagli e aspetta l'ok**
   `python3 video/pipeline.py proponi-tagli NOME`
   Genera `tagli.json` con pause, riempitivi ("ehm") e silenzi a inizio/fine (attivi) e
   ripetizioni (proposte ma non attive). Aggiungi a mano in `tagli.json` i tagli che lo
   script non può vedere (false partenze, frasi rifatte, divagazioni) con `"tipo": "manuale"`.
   Poi mostra a Chiara la lista completa (`python3 video/pipeline.py tagli NOME`) con la
   durata prima/dopo e **fermati**. Applica le sue correzioni (`"attivo": true/false`,
   tempi, nuovi tagli). Solo dopo il suo ok esplicito imposta `"approvato": true`.
   Senza quel flag i passi successivi si rifiutano di partire; se la lista cambia dopo
   l'ok, richiedi un nuovo ok.
4. **Bozza dei primi 15 secondi e aspetta l'ok**
   `python3 video/pipeline.py bozza NOME --stile video/stili/CLIENTE.json`
   Produce `NOME_bozza15s.mp4` (già tagliato, 1080x1920, sottotitoli impressi). Inviala
   a Chiara e **fermati**. Se chiede modifiche (stile, a capo, testo, tagli) correggi e
   rigenera la bozza finché non approva.
5. **Taglia**
   `python3 video/pipeline.py taglia NOME` → `NOME_tagliato.mp4` (senza sottotitoli).
6. **Imprimi i sottotitoli ed esporta**
   `python3 video/pipeline.py imprimi NOME` → `NOME_finale.mp4` e `NOME.srt`.
7. **Consegna** i tre file (`NOME_finale.mp4`, `NOME_tagliato.mp4`, `NOME.srt`) e controlla
   prima con `ffprobe` che il finale sia 1080x1920 e che la durata sia quella attesa.

`python3 video/pipeline.py sottotitoli NOME` rigenera solo `.srt`/`.ass` senza render.
I parametri dei tagli (soglia pausa, margini) sono opzioni di `proponi-tagli` (`--help`).

### Guida di stile dei sottotitoli

Un file JSON per cliente in `video/stili/`, partendo da `_esempio.json`. Campi: `font`,
`cartella_font` (cartella con i file del font, se non è installato), `grassetto`,
`dimensione` (px su 1920 di altezza), `colore_testo`, `colore_contorno`,
`spessore_contorno`, `ombra`, `sfondo` (`{"colore", "opacita"}` per il riquadro),
`colore_evidenza` (colore della parola pronunciata, `null` = nessuna evidenza),
`maiuscolo`, `rimuovi_punteggiatura`, `allineamento` (`basso`/`centro`/`alto`),
`margine_verticale_px`, `margine_laterale_px`, `max_caratteri_riga`, `max_righe`,
`max_parole`. Lo stile usato viene ricordato in `lavoro.json` dopo il primo `--stile`.

### Note tecniche

- Il `.srt` è sulla timeline del video **tagliato**, con maiuscole e punteggiatura naturali;
  maiuscolo forzato e punteggiatura rimossa valgono solo per i sottotitoli impressi.
- I tagli sono allineati ai fotogrammi e ogni giunta ha una micro-dissolvenza audio (8 ms).
- Sorgenti non 9:16 vengono ritagliate al centro: segnalalo a Chiara prima di procedere.
- In sessione cloud il container è temporaneo: i file in `video/lavori/` si perdono a fine
  sessione, quindi invia sempre i file di consegna a Chiara.
