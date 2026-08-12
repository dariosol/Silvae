"""Template delle "schede albero" per la generazione di report.

⚠️  PLACEHOLDER — struttura di base in attesa dei requisiti definitivi.

Obiettivo: permettere di generare una "scheda" (report per singolo albero,
tipicamente una pagina per albero) a partire da un *template* selezionabile.
Il template descrive quali campi mostrare e come impaginarli; la resa vera e
propria (PDF/DOCX/HTML impaginato) verrà implementata quando arriveranno i
requisiti specifici.

Come estendere quando arrivano i requisiti
------------------------------------------
1. Aggiungere/aggiornare le voci in ``REPORT_TEMPLATES`` (o caricarle da file
   utente: vedi ``register_template``).
2. Riempire ``TreeSheetTemplate.sections`` con la struttura reale della scheda
   (gruppi di campi, etichette, ordine, eventuali immagini/mappe).
3. Implementare il vero rendering in ``render_scheda`` (es. con WeasyPrint per
   il PDF o python-docx per il DOCX), sostituendo il placeholder HTML.

L'endpoint Flask (`/report/scheda`) è già cablato con lo stesso filtro per
ruolo e la stessa selezione `ids` degli export, quindi qui resta solo la
logica di template + rendering.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional
import html


# --- Formati di output supportati (per adesso solo un placeholder HTML) -------
FORMAT_HTML = "html"
FORMAT_PDF = "pdf"   # da implementare
FORMAT_DOCX = "docx"  # da implementare

_MIME_BY_FORMAT = {
    FORMAT_HTML: "text/html; charset=utf-8",
    FORMAT_PDF: "application/pdf",
    FORMAT_DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@dataclass
class TreeSheetTemplate:
    """Descrizione di un template di scheda albero.

    ``sections`` è volutamente vuoto: sarà la struttura della scheda (gruppi di
    campi, etichette, ordine) definita a partire dai requisiti. La firma è già
    predisposta per template built-in e per template caricati dall'utente.
    """
    id: str
    name: str
    description: str = ""
    fmt: str = FORMAT_HTML
    builtin: bool = True
    # Struttura della scheda — da definire con i requisiti.
    # Esempio previsto: [{"title": "Identificazione", "fields": [("Specie", "species"), ...]}, ...]
    sections: list = field(default_factory=list)
    # Renderer specifico opzionale; se None si usa ``render_scheda`` generico.
    renderer: Optional[Callable] = None

    def to_meta(self) -> dict:
        """Metadati serializzabili per il frontend (senza il renderer)."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "format": self.fmt,
            "builtin": self.builtin,
        }


# --- Registro dei template ----------------------------------------------------
# Placeholder: un solo template di base. I template reali verranno aggiunti qui
# oppure registrati a runtime con ``register_template``.
REPORT_TEMPLATES: dict[str, TreeSheetTemplate] = {
    "scheda_base": TreeSheetTemplate(
        id="scheda_base",
        name="Scheda albero (base)",
        description="Template segnaposto: una pagina per albero. "
                    "Struttura e impaginazione definitive in arrivo.",
        fmt=FORMAT_HTML,
        builtin=True,
        sections=[],
    ),
}

DEFAULT_TEMPLATE_ID = "scheda_base"


def list_templates() -> list[dict]:
    """Metadati di tutti i template disponibili (per il frontend)."""
    return [t.to_meta() for t in REPORT_TEMPLATES.values()]


def get_template(template_id: Optional[str]) -> Optional[TreeSheetTemplate]:
    """Ritorna il template richiesto, o quello di default se non specificato."""
    if not template_id:
        return REPORT_TEMPLATES.get(DEFAULT_TEMPLATE_ID)
    return REPORT_TEMPLATES.get(template_id)


def register_template(template: TreeSheetTemplate) -> None:
    """Registra (o sovrascrive) un template — punto d'ingresso per i template
    caricati dall'utente. La validazione/persistenza verrà definita coi requisiti."""
    REPORT_TEMPLATES[template.id] = template


def mimetype_for(template: TreeSheetTemplate) -> str:
    return _MIME_BY_FORMAT.get(template.fmt, "application/octet-stream")


def extension_for(template: TreeSheetTemplate) -> str:
    return template.fmt


def render_scheda(trees, template: TreeSheetTemplate) -> bytes:
    """Genera il report delle schede per gli alberi dati.

    PLACEHOLDER: produce un HTML minimale (una scheda per albero con pochi campi
    di identificazione) così che l'intero flusso richiesta→download sia già
    funzionante e testabile. Il layout definitivo, i campi e i formati
    PDF/DOCX verranno implementati a partire dai requisiti.
    """
    if template.renderer is not None:
        return template.renderer(trees, template)

    def esc(v):
        return html.escape("" if v is None else str(v))

    cards = []
    for t in trees:
        cards.append(f"""
        <section class="scheda">
          <h2>{esc(getattr(t, 'custom_id', None) or getattr(t, 'id', ''))} — {esc(getattr(t, 'species', ''))}</h2>
          <dl>
            <dt>Comune</dt><dd>{esc(getattr(t, 'city', ''))}</dd>
            <dt>Indirizzo</dt><dd>{esc(getattr(t, 'address', ''))}</dd>
            <dt>Specie</dt><dd>{esc(getattr(t, 'species', ''))}</dd>
            <dt>Condizione</dt><dd>{esc(getattr(t, 'condition', ''))}</dd>
          </dl>
          <p class="todo">Contenuto della scheda in fase di definizione.</p>
        </section>""")

    doc = f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<title>Schede albero — {esc(template.name)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 24px; color: #1a1a1a; }}
  .scheda {{ page-break-after: always; border: 1px solid #d0d0d0; border-radius: 8px;
             padding: 16px 20px; margin-bottom: 20px; }}
  .scheda h2 {{ margin: 0 0 12px; font-size: 18px; }}
  dl {{ display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 0; }}
  dt {{ font-weight: 600; color: #555; }}
  .todo {{ margin-top: 12px; color: #b45309; font-style: italic; }}
  .banner {{ background: #fef3c7; border: 1px solid #fcd34d; border-radius: 6px;
             padding: 8px 12px; margin-bottom: 20px; font-size: 13px; }}
</style></head><body>
<div class="banner">⚠️ Template <strong>{esc(template.name)}</strong> — anteprima segnaposto.
Struttura e impaginazione definitive in arrivo.</div>
{''.join(cards) if cards else '<p>Nessun albero da includere nel report.</p>'}
</body></html>"""
    return doc.encode("utf-8")
