"""
Stile QGIS (.qml) generato dalla tavolozza di Silvae Pro.

Un renderer categorizzato su una colonna di categoria (chiavi di
`palette.RISK` / `palette.CONDITION`, le stesse della barra statistiche) con
i colori `main` della palette, contorno bianco ed etichetta con l'ID albero.
Cambiando un colore in `palette.py` cambiano webapp, mappa e questo stile.

Tre varianti (`by`):
  stat        colonna `stat_bucket`: rischio ORD se calcolato, altrimenti
              condizione VTA/CPC, altrimenti NA — la casella della barra
              statistiche (predefinita)
  rischio     colonna `rischio_classe`: sole classi ARETE, vuoto = non calcolato
  condizione  colonna `cond_classe`: sola condizione VTA/CPC

Il nome della colonna si può cambiare (`field=`) per i GPKG esportati con
colonne rinominate. Nessuna dipendenza: XML scritto a mano.
"""
from xml.sax.saxutils import quoteattr

from tools import palette

STYLES = {
    'stat':       {'field': 'stat_bucket',    'title': 'Rischio ARETE / condizione VTA'},
    'rischio':    {'field': 'rischio_classe', 'title': 'Classe di rischio ARETE'},
    'condizione': {'field': 'cond_classe',    'title': 'Condizione VTA / CPC'},
}
DEFAULT_STYLE = 'stat'
NA = palette.by_key('risk', 'na')


def rgba(hex_color, alpha=255):
    """'#2d6a4f' → '45,106,79,255' (formato colore dei file QML)."""
    h = hex_color.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f'{r},{g},{b},{alpha}'


def categories(by=DEFAULT_STYLE):
    """[(valore, etichetta, colore_hex)] nell'ordine della legenda."""
    if by == 'stat':
        cats = [(f"risk:{e['key']}", f"Rischio: {e['label']}", e['main'])
                for e in palette.RISK if e['key'] != 'na']
        cats += [(f"cond:{e['key']}", f"Condizione: {e['label']}", e['main'])
                 for e in palette.CONDITION]
        cats.append(('na', NA['label'], NA['main']))
        return cats
    if by == 'rischio':
        cats = [(e['key'], e['label'], e['main']) for e in palette.RISK if e['key'] != 'na']
        cats.append(('', 'Non calcolato', NA['main']))
        return cats
    if by == 'condizione':
        cats = [(e['key'], e['label'], e['main']) for e in palette.CONDITION]
        cats.append(('', 'Non classificato', NA['main']))
        return cats
    raise ValueError(f'stile sconosciuto: {by}')


def _symbol(idx, color_hex, size_mm):
    return f'''      <symbol type="marker" name="{idx}" alpha="1" clip_to_extent="1" force_rhr="0" is_animated="0" frame_rate="10">
        <layer class="SimpleMarker" enabled="1" locked="0" pass="0">
          <Option type="Map">
            <Option name="name" type="QString" value="circle"/>
            <Option name="color" type="QString" value="{rgba(color_hex)}"/>
            <Option name="outline_color" type="QString" value="255,255,255,255"/>
            <Option name="outline_style" type="QString" value="solid"/>
            <Option name="outline_width" type="QString" value="0.3"/>
            <Option name="outline_width_unit" type="QString" value="MM"/>
            <Option name="size" type="QString" value="{size_mm}"/>
            <Option name="size_unit" type="QString" value="MM"/>
            <Option name="scale_method" type="QString" value="diameter"/>
          </Option>
        </layer>
      </symbol>'''


def qml(by=DEFAULT_STYLE, field=None, label_field='custom_id', size_mm=3.0, labels=True):
    """Testo del file .qml (simbologia + etichette) per la variante `by`."""
    style = STYLES[by]
    attr = field or style['field']
    cats = categories(by)
    cat_xml = '\n'.join(
        f'      <category value={quoteattr(v)} symbol="{i}" label={quoteattr(lbl)} render="true" type="string"/>'
        for i, (v, lbl, _c) in enumerate(cats))
    sym_xml = '\n'.join(_symbol(i, c, size_mm) for i, (_v, _l, c) in enumerate(cats))
    labeling = ''
    if labels and label_field:
        labeling = f'''  <labeling type="simple">
    <settings calculation="0">
      <text-style fieldName={quoteattr(label_field)} isExpression="0" fontSize="8" fontSizeUnit="Point" textColor="50,50,50,255" fontFamily="DejaVu Sans" namedStyle="Normal">
        <text-buffer bufferDraw="1" bufferSize="0.8" bufferSizeUnits="MM" bufferColor="255,255,255,255" bufferOpacity="0.9"/>
      </text-style>
      <placement placement="6" dist="1" distUnits="MM" quadOffset="2"/>
      <rendering scaleVisibility="1" scaleMin="0" scaleMax="5000" limitNumLabels="0" drawLabels="1"/>
    </settings>
  </labeling>
'''
    return f'''<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28" styleCategories="Symbology|Labeling" labelsEnabled="{1 if labeling else 0}">
  <!-- Silvae Pro — {style['title']} (generato da tools/palette.py; non modificare a mano) -->
  <renderer-v2 type="categorizedSymbol" attr={quoteattr(attr)} forceraster="0" symbollevels="0" enableorderby="0" referencescale="-1">
    <categories>
{cat_xml}
    </categories>
    <symbols>
{sym_xml}
    </symbols>
    <rotation/>
    <sizescale/>
  </renderer-v2>
{labeling}  <blendMode>0</blendMode>
  <featureBlendMode>0</featureBlendMode>
  <layerGeometryType>0</layerGeometryType>
</qgis>
'''
