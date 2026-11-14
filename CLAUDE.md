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
- Formato finale: **1080x1920** (9:16) per i verticali, H.264 + AAC, audio a −14 LUFS.
  Il formato si sceglie in `normalizza --formato` (`9:16`, `16:9` = 1920x1080 per YouTube,
  `1:1`, `4:5`); senza opzione: 16:9 se il girato è orizzontale, altrimenti 9:16.
- Ogni video in lavorazione va tenuto aggiornato nella dashboard **Sala Montaggio** (vedi sotto).

### Procedura

`NOME` è il nome del lavoro (lettere, numeri, `-`, `_`); i file finiscono in
`video/lavori/NOME/` (cartella ignorata da git: il girato e i render non vanno nel repo).

1. **Normalizza l'audio**
   `python3 video/pipeline.py normalizza NOME /percorso/girato.mp4`
   Loudnorm a due passate → `audio_norm.flac`. Leggi gli avvisi (sorgente non 9:16, HDR).
2. **Trascrivi**
   `python3 video/pipeline.py trascrivi NOME`
   faster-whisper `large-v3`, italiano, timestamp per parola → `trascrizione.json` e `.txt`.
   (Su CPU; in una sessione nuova il modello, circa 3 GB, va riscaricato da huggingface.)
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

### Dashboard "Sala Montaggio"

Pagina privata di Chiara: https://claude.ai/artifact/DJtcLcnkKJ9qKKVALvSY9j
(sorgente: `video/dashboard/sala-montaggio.html`; per aggiornarla ripubblica con quell'URL).
È il posto dove Chiara vede lo stato dei video, guarda le anteprime e chiede modifiche.
I dati stanno nel database della pagina e si leggono/scrivono con lo strumento `ArtifactData`.

- `video/NOME` — `titolo`, `cliente`, `formato`, `stato` (`in_montaggio` = palla a Claude,
  `in_attesa` = serve l'ok di Chiara, `da_modificare`, `approvato`, `programmato`), `fase`
  (`girato`, `trascrizione`, `tagli`, `bozza`, `render`, `programmazione`), `versione`, `messaggio`
  (cosa serve da Chiara adesso), `anteprima` + `fase_anteprima`, `versioni`
  (`[{n, fase, anteprima, cosa}]`), `tagli` + `tagli_approvati`, `tracce`
  (`[{nome, elementi: [{inizio, fine, etichetta}]}]`, tempi sul video tagliato),
  `consegna` (`[{nome, url}]`), `programmazione` (`{quando, canali, testo, stato}`:
  Chiara la compila dalla dashboard con `stato: "richiesta"`; dopo aver programmato
  davvero il post metti `stato: "fatta"` e il video in `stato: "programmato"`), `aggiornato`.
- Il campo `cliente` è l'**area di lavoro**: la dashboard si filtra per cliente, quindi
  scrivilo sempre e sempre uguale (stesso nome del file in `video/stili/`).
- `testo/NOME` — `parole: [{t0, t1, p}]` (tempi sul girato).
- `note/ID` — richieste di Chiara: `video`, `t`, `su` (su quale anteprima è il tempo:
  `girato`, `bozza`, `finale`), `versione`, `tipo`, `testo`, `stato` (`aperta`/`risolta`),
  `risposta`. Le note `tipo: "correzione"` hanno anche `originale`, `nuovo`, `i0`, `i1`
  (indici delle parole in `testo/NOME`).

Come si usa durante un lavoro:

1. A ogni passo: `python3 video/pipeline.py scheda NOME` e
   `python3 video/pipeline.py anteprima NOME --fase girato|bozza|tagliato|finale`
   (file ≤ 14 MB); carica l'anteprima come asset della pagina, poi scrivi `video/NOME`
   (da `scheda_video.json` + campi di stato) e `testo/NOME` (da `scheda_testo.json`).
2. Quando serve un ok metti `stato: "in_attesa"` e spiega in `messaggio` cosa va guardato.
3. Quando Chiara dice di aver lasciato feedback: leggi `video/NOME` e le `note` aperte.
   - I tagli spuntati/aggiunti in dashboard vanno riportati in `tagli.json`;
     `tagli_approvati: true` nella dashboard vale come ok alla lista tagli.
   - Le correzioni vanno applicate a `trascrizione.json`; le altre note al montaggio.
   - Su ogni nota scrivi `risposta` (cosa hai fatto) e `stato: "risolta"`.
4. Nuova anteprima = nuova `versione` e nuova voce in `versioni` con `cosa` è cambiato.
5. La dashboard non avvisa da sola: si leggono i feedback quando Chiara lo chiede.

Il video `esempio` nella dashboard è finto (serve a provare la pagina): si può cancellare.

### Da dove arriva il girato

I file stanno su Google Drive. Il connettore Drive serve per cercare e leggere, non per
scaricare video grandi. Per portare un video nella sessione: Chiara lo condivide con
"chiunque abbia il link" e si scarica da `drive.google.com` (host già consentiti
nell'ambiente cloud `chiaralavoro`). I video dell'app Foto vanno prima messi su Drive.

**Caricare su Drive dalla sessione cloud non funziona per i video**: ogni chiamata al
connettore porta al massimo circa 3 MB di file (verificato: un MP4 da 3,7 MB è stato
rifiutato). Il file finale va quindi inviato a Chiara in chat, oppure serve un'altra
strada decisa da lei; non aggirare il limite di iniziativa.

### Programmazione dei post

Si programma con il connettore Metricool (collegato; un brand per cliente, elenco con
`getBrandSettings`, fuso `Europe/Rome`). A Metricool serve il video a un indirizzo pubblico:
accetta link Google Drive se Drive è collegato all'account Metricool. Si programma solo un
video approvato, con giorno, ora, canali e didascalia presi dalla richiesta in dashboard,
e solo quando Chiara lo chiede.

### Guida di stile dei sottotitoli

Un file JSON per cliente in `video/stili/`, partendo da `_esempio.json`. Campi: `font`,
`cartella_font` (cartella con i file del font, se non è installato), `grassetto`,
`dimensione` (px sull'altezza del formato: 1920 per i verticali, 1080 per i 16:9), `colore_testo`, `colore_contorno`,
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
