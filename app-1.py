from flask import Flask, request, jsonify
import anthropic
import requests
import base64
import datetime
import os
import re
import random
import json
import threading

app = Flask(__name__)

# ============================================================
#  CONFIGURARE
# ============================================================
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_KEY', '')
WP_URL        = os.environ.get('WP_URL', 'https://parohiacetate2.ro')
WP_USER       = os.environ.get('WP_USER', 'cetate2AI')
WP_PASS       = os.environ.get('WP_PASS', '')
TG_TOKEN      = os.environ.get('TG_TOKEN', '')
TG_CHAT_ID    = os.environ.get('TG_CHAT_ID', '')

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
pending_articol = {}

# ============================================================
#  CATEGORII WORDPRESS (ID-uri reale)
# ============================================================
CAT_POSTARI_NOI = 41
CAT_PREDICA     = 42
CAT_TRAIESTE    = 45
CAT_CATEHEZE    = 40

# ============================================================
#  AN OMAGIAL - cache, se reinnoieste la 1 ianuarie
# ============================================================
_an_omagial_cache = {}

def get_an_omagial():
    an_curent = datetime.datetime.now().year
    if _an_omagial_cache.get('an') == an_curent:
        return _an_omagial_cache.get('titlu', '')
    titlu = _cauta_an_omagial(an_curent)
    _an_omagial_cache['an'] = an_curent
    _an_omagial_cache['titlu'] = titlu
    return titlu

def _cauta_an_omagial(an):
    headers = {'User-Agent': 'Mozilla/5.0'}
    surse = ['https://basilica.ro', 'https://patriarhia.ro', 'https://doxologia.ro']
    for url in surse:
        try:
            r = requests.get(url, headers=headers, timeout=8)
            for pat in [r'[Aa]nul [Oo]magial[^<\n]{5,120}', r'[Aa]n [Oo]magial[^<\n]{5,120}']:
                m = re.search(pat, r.text)
                if m:
                    titlu = re.sub(r'<[^>]+>', '', m.group(0)).strip()
                    titlu = re.sub(r'\s+', ' ', titlu)
                    if len(titlu) > 15:
                        return titlu[:120]
        except:
            continue
    fallback = {
        2024: "Anul omagial al pastoratiei persoanelor vulnerabile",
        2025: "Anul omagial al preotilor parohiali si al misionarilor",
        2026: "Anul omagial al rugaciunii in viata crestina",
        2027: "Anul omagial al Sfintei Scripturi",
    }
    return fallback.get(an, f"Anul omagial {an}")

# ============================================================
#  ZILE SPECIALE
# ============================================================
ZILE_SPECIALE = {
    (1,1):   "Ziua Mondiala a Pacii",
    (1,18):  "Saptamana de Rugaciune pentru Unitatea Crestinilor",
    (2,2):   "Ziua Vietii Consacrate",
    (2,8):   "Duminica Ortodoxa a Bibliei",
    (3,25):  "Ziua Internationala a Bunei Vestiri",
    (5,15):  "Ziua Internationala a Familiei",
    (6,1):   "Ziua Internationala a Copilului",
    (9,1):   "Ziua de Rugaciune pentru Ocrotirea Creatiei",
    (10,4):  "Ziua Mondiala a Animalelor - creatia lui Dumnezeu",
    (12,1):  "Ziua Nationala a Romaniei - rugaciune pentru neam si tara",
    (12,10): "Ziua Internationala a Drepturilor Omului",
}

def get_zi_speciala(dt=None):
    if dt is None:
        dt = datetime.datetime.now()
    return ZILE_SPECIALE.get((dt.month, dt.day))

# ============================================================
#  BLOC RESURSE HTML - apare in fiecare articol publicat
# ============================================================
def get_bloc_resurse():
    an_omagial = get_an_omagial()
    return f"""
<div style="background:linear-gradient(135deg,#f9f5f0,#fdf8f3);border-left:4px solid #8B0000;
padding:18px 22px;margin:32px 0 20px 0;border-radius:0 8px 8px 0;font-size:14px;line-height:2.2;">
<p style="margin:0 0 6px 0;font-weight:bold;color:#8B0000;font-size:15px;letter-spacing:0.3px;">
Resurse duhovnicesti</p>
<p style="margin:0 0 5px 0;">
<a href="https://doxologia.ro/rugaciuni/rugaciunile-diminetii" target="_blank"
style="color:#5a2d0c;text-decoration:none;font-weight:500;">Rugaciunile diminetii</a>
&nbsp;&nbsp;|&nbsp;&nbsp;
<a href="https://doxologia.ro/rugaciuni/rugaciunile-serii" target="_blank"
style="color:#5a2d0c;text-decoration:none;font-weight:500;">Rugaciunile serii</a>
&nbsp;&nbsp;|&nbsp;&nbsp;
<a href="https://doxologia.ro/viata-bisericii/acatiste-paraclise/paraclisul-maicii-domnului"
target="_blank" style="color:#5a2d0c;text-decoration:none;font-weight:500;">
Paraclisul Maicii Domnului</a>
</p>
<p style="margin:0 0 5px 0;">
<a href="https://calendar.patriarhia.ro" target="_blank"
style="color:#5a2d0c;text-decoration:none;">Calendar Ortodox Patriarhia Romana</a>
&nbsp;&nbsp;|&nbsp;&nbsp;
<a href="https://doxologia.ro/calendar-ortodox" target="_blank"
style="color:#5a2d0c;text-decoration:none;">Doxologia.ro</a>
&nbsp;&nbsp;|&nbsp;&nbsp;
<a href="https://www.mitropolia-ardealului.ro" target="_blank"
style="color:#5a2d0c;text-decoration:none;">Arhiepiscopia Sibiului</a>
</p>
<p style="margin:0 0 5px 0;">
<a href="https://www.edituradeiosis.ro" target="_blank"
style="color:#5a2d0c;text-decoration:none;">Editura Deisis Sibiu</a>
&nbsp;&nbsp;|&nbsp;&nbsp;
<a href="https://catedrala-sibiu.ro" target="_blank"
style="color:#5a2d0c;text-decoration:none;">Catedrala Mitropolitana Sibiu</a>
&nbsp;&nbsp;|&nbsp;&nbsp;
<a href="https://basilica.ro" target="_blank"
style="color:#5a2d0c;text-decoration:none;">Basilica.ro</a>
</p>
<p style="margin:8px 0 0 0;font-style:italic;color:#8B0000;font-size:13px;border-top:1px solid #ddd;
padding-top:8px;">
{an_omagial} - Patriarhia Romana</p>
</div>
"""

# ============================================================
#  HELPERS DATA
# ============================================================
def get_azi():
    return datetime.datetime.now()

def get_zi_romana(dt=None):
    if dt is None:
        dt = get_azi()
    zile = ['Luni','Marti','Miercuri','Joi','Vineri','Sambata','Duminica']
    luni = ['','ianuarie','februarie','martie','aprilie','mai','iunie',
            'iulie','august','septembrie','octombrie','noiembrie','decembrie']
    return f"{zile[dt.weekday()]}, {dt.day} {luni[dt.month]} {dt.year}"

def get_tip_zi(dt=None):
    if dt is None:
        dt = get_azi()
    ziua = (dt.month, dt.day)
    zi_sapt = dt.weekday()

    saptamana_mare = [(4,6),(4,7),(4,8),(4,9),(4,10),(4,11)]
    if ziua in saptamana_mare:
        return 'saptamana_mare'

    sarbatori = {
        (1,1),(1,6),(1,7),(2,2),(3,25),(8,6),(8,15),
        (9,8),(9,14),(11,8),(11,30),(12,6),(12,25),(12,26)
    }
    if ziua in sarbatori:
        return 'sarbatoare'

    azi_date = dt.date() if hasattr(dt, 'date') else dt
    posturi = [
        (datetime.date(2026,2,23), datetime.date(2026,4,11)),
        (datetime.date(2026,6,15), datetime.date(2026,6,28)),
        (datetime.date(2026,8,1),  datetime.date(2026,8,14)),
        (datetime.date(2026,11,15),datetime.date(2026,12,24)),
    ]
    inceputuri = [p[0] for p in posturi]
    in_post = any(s <= azi_date <= e for s,e in posturi)

    if azi_date in inceputuri:
        return 'inceput_post'
    if zi_sapt == 6:
        return 'duminica'
    if in_post:
        return 'post'
    return 'obisnuit'

def get_nume_saptamana_mare(dt=None):
    if dt is None:
        dt = get_azi()
    zile = {
        (4,6):  ("Lunea Mare","Iosif cel Prea Frumos si smochinul neroditor"),
        (4,7):  ("Martea Mare","Parabolele Mantuitorului si semnele sfarsitului"),
        (4,8):  ("Miercurea Mare","Ungerea cu mir la Betania si vanzarea lui Iuda"),
        (4,9):  ("Joia Mare","Cina cea de Taina si rugaciunea din Ghetsimani"),
        (4,10): ("Vinerea Mare","Patimile, Rastignirea si Moartea Domnului"),
        (4,11): ("Sambata Mare","Prohodul Domnului - intre moarte si Inviere"),
    }
    return zile.get((dt.month, dt.day), ("Saptamana Mare",""))

def get_nume_sarbatoare(dt):
    sarbatori = {
        (1,1):"Taierea Imprejur / Sf. Vasile cel Mare",
        (1,6):"Botezul Domnului",(1,7):"Soborul Sf. Ioan Botezatorul",
        (2,2):"Intampinarea Domnului",(3,25):"Buna Vestire",
        (8,6):"Schimbarea la Fata",(8,15):"Adormirea Maicii Domnului",
        (9,8):"Nasterea Maicii Domnului",(9,14):"Inaltarea Sfintei Cruci",
        (11,8):"Soborul Sfintilor Arhangheli",(11,30):"Sf. Apostol Andrei",
        (12,6):"Sf. Ierarh Nicolae",(12,25):"Nasterea Domnului",
        (12,26):"A doua zi de Craciun",
    }
    return sarbatori.get((dt.month, dt.day), "Sarbatoare")

def get_nume_post(dt):
    posturi = {
        (2,23):"Postul Mare",(6,15):"Postul Sfintilor Apostoli",
        (8,1):"Postul Adormirii Maicii Domnului",(11,15):"Postul Craciunului",
    }
    return posturi.get((dt.month, dt.day), "Postul")

# ============================================================
#  TELEGRAM
# ============================================================
def tg_send(text, chat_id=None):
    if not TG_TOKEN:
        return
    cid = chat_id or TG_CHAT_ID
    if not cid:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={'chat_id': cid, 'text': text, 'parse_mode': 'HTML'},
            timeout=10
        )
    except:
        pass

def tg_get_file(file_id):
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TG_TOKEN}/getFile?file_id={file_id}",
            timeout=10
        )
        fp = r.json()['result']['file_path']
        return requests.get(
            f"https://api.telegram.org/file/bot{TG_TOKEN}/{fp}",
            timeout=30
        ).content
    except:
        return None

def trimite_spre_aprobare(articol):
    global pending_articol
    pending_articol = articol
    preview = (
        f"<b>ARTICOL GENERAT</b>\n"
        f"<b>{articol.get('titlu_wp','')}</b>\n\n"
        f"<b>Preview Facebook:</b>\n"
        f"{str(articol.get('fb_text',''))[:500]}...\n\n"
        f"<b>Raspunde cu:</b>\n"
        f"/aproba - publica acum\n"
        f"/adaug [text] - adauga gand personal\n"
        f"/regenereaza - genereaza alt articol\n"
        f"/respinge - nu publica azi"
    )
    tg_send(preview)

# ============================================================
#  CLAUDE API
# ============================================================
def call_claude(system, user, max_tokens=3500, img_b64=None, media_type='image/jpeg'):
    content = []
    if img_b64:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": img_b64}
        })
    content.append({"type": "text", "text": user})
    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}]
    )
    return msg.content[0].text

def parse_json_robust(text):
    try:
        return json.loads(text)
    except:
        pass
    m = re.search(r'```json\s*([\s\S]*?)\s*```', text)
    if m:
        try:
            return json.loads(m.group(1))
        except:
            pass
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        try:
            return json.loads(m.group(0))
        except:
            pass
    raise ValueError("JSON invalid: " + text[:200])

# ============================================================
#  SCRAPING
# ============================================================
def scrape_sfinti():
    try:
        h = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get('https://doxologia.ro/calendar-ortodox', headers=h, timeout=10)
        m = re.findall(r'<h[23][^>]*>([^<]{10,100})</h[23]>', r.text)
        sfinti = [x.strip() for x in m if any(
            k in x.lower() for k in ['sf.','sfanta','sfantul','cuviosul','mucenic','ierarh','apostol','prooroc']
        )]
        return sfinti[:6]
    except:
        return []

def scrape_apostol_evanghelie():
    try:
        h = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get('https://doxologia.ro/lecturile-zilei', headers=h, timeout=10)
        ap, ev = '', ''
        m = re.search(r'[Aa]postol[^<]*</[^>]+>\s*<[^>]+>([^<]{30,400})', r.text)
        if m:
            ap = re.sub(r'<[^>]+>', '', m.group(1)).strip()[:400]
        m = re.search(r'[Ee]vangheli[ae][^<]*</[^>]+>\s*<[^>]+>([^<]{30,400})', r.text)
        if m:
            ev = re.sub(r'<[^>]+>', '', m.group(1)).strip()[:400]
        return ap, ev
    except:
        return '', ''

def get_imagine(tip='', query=''):
    imagini = {
        'craciun':   'https://basilica.ro/wp-content/uploads/2023/12/nasterea-domnului.jpg',
        'paste':     'https://basilica.ro/wp-content/uploads/2024/04/invierea-domnului.jpg',
        'florii':    'https://basilica.ro/wp-content/uploads/2024/04/duminica-floriilor.jpg',
        'boboteaza': 'https://basilica.ro/wp-content/uploads/2024/01/botezul-domnului.jpg',
        'post':      'https://doxologia.ro/sites/default/files/articol/2020/03/post.jpg',
        'maica':     'https://doxologia.ro/sites/default/files/articol/2019/08/adormirea.jpg',
        'cruce':     'https://basilica.ro/wp-content/uploads/2023/09/inaltarea-sfintei-cruci.jpg',
        'nicolae':   'https://doxologia.ro/sites/default/files/articol/2019/12/sfantul-nicolae.jpg',
        'andrei':    'https://basilica.ro/wp-content/uploads/2023/11/sf-apostol-andrei.jpg',
        'default':   'https://basilica.ro/wp-content/uploads/2023/10/biserica-ortodoxa.jpg',
    }
    # Incearca si doxologia
    try:
        h = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get('https://doxologia.ro/calendar-ortodox', headers=h, timeout=8)
        imgs = re.findall(r'https://[^"\']*doxologia[^"\']*\.jpg', r.text)
        if imgs:
            return imgs[0]
    except:
        pass
    q = (tip + ' ' + query).lower()
    for cheie, url in imagini.items():
        if cheie in q:
            return url
    return imagini['default']

# ============================================================
#  WORDPRESS
# ============================================================
def wp_auth():
    enc = base64.b64encode(f"{WP_USER}:{WP_PASS}".encode()).decode()
    return {'Authorization': f'Basic {enc}', 'Content-Type': 'application/json'}

def publica_articol(titlu, continut, categorii=None, featured_media=None):
    if categorii is None:
        categorii = [CAT_TRAIESTE]
    continut_final = continut + get_bloc_resurse()
    data = {
        'title': titlu,
        'content': continut_final,
        'status': 'publish',
        'categories': categorii,
        'tags': [],
    }
    if featured_media:
        data['featured_media'] = featured_media
    r = requests.post(
        f"{WP_URL}/wp-json/wp/v2/posts",
        json=data, headers=wp_auth(), timeout=30
    )
    print(f"WP: {r.status_code} - {r.text[:200]}")
    res = r.json()
    return res.get('id'), res.get('link', '')

def upload_media(data_bytes, filename, mime):
    enc = base64.b64encode(f"{WP_USER}:{WP_PASS}".encode()).decode()
    h = {
        'Authorization': f'Basic {enc}',
        'Content-Type': mime,
        'Content-Disposition': f'attachment; filename={filename}'
    }
    r = requests.post(f"{WP_URL}/wp-json/wp/v2/media", data=data_bytes, headers=h, timeout=60)
    res = r.json()
    return res.get('id'), res.get('source_url', '')

# ============================================================
#  SYSTEM PROMPT EDITORIAL
# ============================================================
SYSTEM = """Esti redactorul spiritual al Parohiei Cetate 2 Sibiu, Mitropolia Ardealului.

STILUL TAU - sinteza intre:
- Pr. Constantin Necula: caldura pastorala, umor fin, apropiere de om, referinte culturale
- Patriarhul Daniel: profunzime teologica, eleganta limbii romane, viziune misionara
- Alexandre Schmemann: teologia liturgica vie, sensul euharistic al creatiei, bucuria Invierii

REGULI ABSOLUTE:
1. Fiecare text are o MORALA clara, organica, nu impusa
2. Limbaj elevat dar accesibil - ca o predica buna, nu un tratat
3. Citate patristice vii: Sf. Ioan Gura de Aur, Sf. Vasile, Sf. Isaac Sirul, Sf. Siluan Athonitul
4. Apostolul si Evanghelia zilei sunt punctul de plecare real
5. Diacritice corecte romanesti: a-virgula, i-virgula, s-virgula, t-virgula
6. Continut WP: 450-600 cuvinte - meditatie adevarata, nu text scurt
7. Facebook: 200-280 cuvinte, ton cald-uman, cu verset si indemn

Raspunzi EXCLUSIV cu JSON valid. Fara text in afara JSON. Fara markdown."""

# ============================================================
#  GENERARE ARTICOLE
# ============================================================
def genereaza_articol_zilnic(extra_text=''):
    global pending_articol
    dt = get_azi()
    zi = get_zi_romana(dt)
    tip = get_tip_zi(dt)
    sfinti = scrape_sfinti()
    apostol, evanghelie = scrape_apostol_evanghelie()
    zi_spec = get_zi_speciala(dt)
    an_om = get_an_omagial()
    imagine_url = get_imagine(tip)

    sfinti_str = ', '.join(sfinti) if sfinti else 'Sfintii zilei'
    s_extra = f'\nGandul preotului (integreaza natural): {extra_text}' if extra_text else ''
    s_spec = f'\nZi speciala de marcat: {zi_spec}' if zi_spec else ''
    s_an = f'\nAnul omagial: {an_om}' if an_om else ''

    try:
        if tip == 'saptamana_mare':
            titlu_zi, tema_zi = get_nume_saptamana_mare(dt)
            data = _gen_saptamana_mare(zi, titlu_zi, tema_zi, apostol, evanghelie, s_extra)
            data['categorii'] = [CAT_PREDICA]

        elif tip == 'sarbatoare':
            nume = get_nume_sarbatoare(dt)
            data = _gen_sarbatoare(zi, nume, apostol, evanghelie, s_extra, s_spec, s_an)
            data['categorii'] = [CAT_PREDICA, CAT_POSTARI_NOI]
            imagine_url = get_imagine('sarbatoare', nume.lower())

        elif tip == 'inceput_post':
            nume = get_nume_post(dt)
            data = _gen_inceput_post(zi, nume, apostol, evanghelie, s_extra, s_an)
            data['categorii'] = [CAT_TRAIESTE]
            imagine_url = get_imagine('post')

        elif tip == 'duminica':
            nr = dt.isocalendar()[1]
            data = _gen_duminica(zi, sfinti_str, apostol, evanghelie,
                                  (nr % 3 == 0), s_extra, s_spec, s_an)
            data['categorii'] = [CAT_PREDICA, CAT_TRAIESTE]

        elif tip == 'post':
            data = _gen_zi_post(zi, sfinti_str, apostol, evanghelie, s_extra, s_spec)
            data['categorii'] = [CAT_TRAIESTE]

        else:
            data = _gen_zi_obisnuita(zi, sfinti_str, apostol, evanghelie, s_extra, s_spec, s_an)
            data['categorii'] = [CAT_TRAIESTE, CAT_POSTARI_NOI]

        data['imagine_url'] = imagine_url
        data['publica_wp'] = True
        trimite_spre_aprobare(data)
        return data

    except Exception as e:
        tg_send(f"Eroare generare: {str(e)}")
        return None


def _gen_zi_obisnuita(zi, sfinti, apostol, evanghelie, s_extra, s_spec, s_an):
    u = f"""Astazi este {zi}. Sfintii zilei: {sfinti}.
Apostolul zilei: {apostol or 'din lecturile zilei'}.
Evanghelia zilei: {evanghelie or 'din lecturile zilei'}.{s_spec}{s_an}{s_extra}

Genereaza articolul zilnic pentru Parohia Cetate 2 Sibiu.
JSON:
{{
  "titlu_wp": "titlu evocator si viu, nu banal",
  "continut_wp": "HTML: <h2>Apostolul si Evanghelia zilei</h2> + texte cu <blockquote> elegant + <h2>Sfintii zilei</h2> + descriere vie cu link doxologia.ro + <h2>Meditatie duhovniceasca</h2> + 300-400 cuvinte in stilul Necula-Daniel-Schmemann, cu referinta patristica concreta + <h3>Morala zilei</h3> + 1 paragraf concluzie practica de viata",
  "fb_text": "200-250 cuvinte: incepe cu Apostolul sau Evanghelia ca citat scurt + Sfintii zilei + meditatie calda stil Pr. Necula + intrebare sau indemn pentru cititor + #ParohiaCetate2Sibiu #EvanghelliaZilei #SfintiiZilei #Ortodox"
}}"""
    return parse_json_robust(call_claude(SYSTEM, u, 4000))


def _gen_duminica(zi, sfinti, apostol, evanghelie, ips, s_extra, s_spec, s_an):
    ips_html = '+ <h2>Cuvant arhieresc</h2> cu un citat inspirat din predicile IPS Laurentiu Streza' if ips else ''
    u = f"""Astazi este {zi}, Duminica. Sfintii zilei: {sfinti}.
Apostolul Duminicii: {apostol or 'din lecturile duminicale'}.
Evanghelia Duminicii: {evanghelie or 'din lecturile duminicale'}.{s_spec}{s_an}{s_extra}

Genereaza articolul duminical pentru Parohia Cetate 2 Sibiu.
JSON:
{{
  "titlu_wp": "titlu duminical profund si evocator",
  "continut_wp": "HTML: <h2>Apostolul Duminicii</h2> + blockquote + <h2>Evanghelia Duminicii</h2> + blockquote + <h2>Predica</h2> + 400-500 cuvinte: incepe cu o intrebare existentiala, desfasoara teologic cu referinte patristice, culmineaza pastoral {ips_html} + <h2>Sfintii Duminicii</h2> + <h3>Morala Duminicii</h3> + indemn concret pentru saptamana",
  "fb_text": "250-300 cuvinte: Apostol + Evanghelie scurta + meditatie calda + urare duminicala + #DuminicaOrtodoxa #ParohiaCetate2Sibiu #Evanghelie #Predica"
}}"""
    return parse_json_robust(call_claude(SYSTEM, u, 5000))


def _gen_sarbatoare(zi, nume, apostol, evanghelie, s_extra, s_spec, s_an):
    u = f"""Astazi este {zi} - {nume}.
Apostolul sarbatorii: {apostol or 'din lecturile sarbatorii'}.
Evanghelia sarbatorii: {evanghelie or 'din lecturile sarbatorii'}.{s_spec}{s_an}{s_extra}

Genereaza articolul de sarbatoare pentru Parohia Cetate 2 Sibiu.
Stilul: urare calda ca Patriarhul Daniel, profunzime ca Schmemann, bucurie ca Pr. Necula.
JSON:
{{
  "titlu_wp": "titlu festiv si evocator",
  "continut_wp": "HTML festiv: <h2>{nume}</h2> + semnificatia sarbatorii + <blockquote>Troparul sarbatorii</blockquote> + <blockquote>Condacul</blockquote> + <h2>Apostolul si Evanghelia sarbatorii</h2> + texte + <h2>Meditatie</h2> + 300-400 cuvinte despre taina acestei sarbatori, referinte patristice + <h3>Morala sarbatorii</h3> + urare pentru credinciosi",
  "fb_text": "200-250 cuvinte: urare in duhul Bisericii + Tropar scurt + meditatie calda + indemn la rugaciune si participare la slujba + emoji potrivite + hashtag-uri"
}}"""
    return parse_json_robust(call_claude(SYSTEM, u, 4500))


def _gen_inceput_post(zi, nume, apostol, evanghelie, s_extra, s_an):
    u = f"""Astazi este {zi} - incepe {nume}.
Apostolul zilei: {apostol or 'din lecturile postului'}.
Evanghelia zilei: {evanghelie or 'din lecturile postului'}.{s_an}{s_extra}

Genereaza articolul de inceput de post pentru Parohia Cetate 2 Sibiu.
JSON:
{{
  "titlu_wp": "titlu despre inceputul postului",
  "continut_wp": "HTML: <h2>Incepe {nume}</h2> + semnificatia duhovniceasca + Apostol si Evanghelie cu blockquote + <h2>Postul - scoala a sufletului</h2> + 350-400 cuvinte cu citate din Sf. Ioan Gura de Aur, Sf. Vasile, Sf. Isaac Sirul + sfaturi practice duhovnicesti + <h3>Morala</h3> + binecuvantare",
  "fb_text": "200 cuvinte: caldura pastorala, citat patristic, indemn concret la post + Post cu folos! + hashtag-uri"
}}"""
    return parse_json_robust(call_claude(SYSTEM, u, 4000))


def _gen_zi_post(zi, sfinti, apostol, evanghelie, s_extra, s_spec):
    u = f"""Astazi este {zi} - zi de post. Sfintii zilei: {sfinti}.
Apostolul zilei: {apostol or 'din lecturile zilei'}.
Evanghelia zilei: {evanghelie or 'din lecturile zilei'}.{s_spec}{s_extra}

Genereaza meditatie pentru zi de post, Parohia Cetate 2 Sibiu.
JSON:
{{
  "titlu_wp": "titlu meditatie de post",
  "continut_wp": "HTML: <h2>Apostolul si Evanghelia zilei</h2> + texte + <h2>Sfintii zilei</h2> + <h2>Postul ca rugaciune a trupului</h2> + 300-350 cuvinte: sensul postului dincolo de abtinere, intalnirea cu Dumnezeu prin post, citat patristic + <h3>Morala</h3>",
  "fb_text": "150-200 cuvinte: Apostol sau Evanghelie + Sfintii zilei + citat patristic + indemn scurt + hashtag-uri"
}}"""
    return parse_json_robust(call_claude(SYSTEM, u, 3500))


def _gen_saptamana_mare(zi, titlu_zi, tema_zi, apostol, evanghelie, s_extra):
    u = f"""Astazi este {zi} - {titlu_zi}. Tema: {tema_zi}.
Apostolul zilei: {apostol or 'din slujbele Saptamanii Mari'}.
Evanghelia zilei: {evanghelie or 'din slujbele Saptamanii Mari'}.{s_extra}

Genereaza articolul pentru Saptamana Patimilor, Parohia Cetate 2 Sibiu.
Ton: solemn, profund, cu nadejdea Invierii - ca la Schmemann.
JSON:
{{
  "titlu_wp": "{titlu_zi} - titlu solemn si evocator",
  "continut_wp": "HTML: <h2>{titlu_zi}</h2> + contextul biblic al zilei + Apostol si Evanghelie cu blockquote + <h2>Semnificatia liturgica</h2> + explicarea slujbei + <h2>Meditatie</h2> + 350-400 cuvinte in spiritul Triodului, referinte patristice + <h3>Morala</h3> + rugaciune de incheiere",
  "fb_text": "200 cuvinte: solemn cu nadejde + Apostol + Evanghelie + taina zilei + emoji ✝ + hashtag-uri #SaptamanaMare #ParohiaCetate2Sibiu"
}}"""
    return parse_json_robust(call_claude(SYSTEM, u, 4500))


def _gen_din_poza(img_b64, caption=''):
    zi = get_zi_romana()
    apostol, evanghelie = scrape_apostol_evanghelie()
    s_cap = f"Textul preotului (integreaza natural): {caption}" if caption else ''
    u = f"""Astazi este {zi}. {s_cap}
Apostolul zilei: {apostol or ''}.
Evanghelia zilei: {evanghelie or ''}.

Preotul a trimis aceasta imagine. Genereaza articol inspirat.
JSON:
{{
  "titlu_wp": "titlu bazat pe evenimentul fotografiat",
  "continut_wp": "HTML 350-450 cuvinte: descrie evenimentul/momentul + context spiritual + leaga de lecturile zilei + meditatie pastorala + <h3>Morala</h3>",
  "fb_text": "200 cuvinte: calda, invitanta, context spiritual + hashtag-uri #ParohiaCetate2Sibiu #ViataParohiei"
}}"""
    return parse_json_robust(call_claude(SYSTEM, u, 3000, img_b64=img_b64))


def _gen_din_text(text):
    zi = get_zi_romana()
    apostol, evanghelie = scrape_apostol_evanghelie()
    u = f"""Astazi este {zi}.
Apostolul zilei: {apostol or ''}.
Evanghelia zilei: {evanghelie or ''}.
Preotul a trimis: "{text}"

Transforma in articol complet, integrand lecturile zilei.
JSON:
{{
  "titlu_wp": "titlu articol",
  "continut_wp": "HTML 350-400 cuvinte: mesajul preotului + Apostol + Evanghelie + context spiritual + <h3>Morala</h3>",
  "fb_text": "180-200 cuvinte + emoji + hashtag-uri #ParohiaCetate2Sibiu"
}}"""
    return parse_json_robust(call_claude(SYSTEM, u, 3000))


def _gen_din_audio(transcriptie, caption=''):
    zi = get_zi_romana()
    apostol, evanghelie = scrape_apostol_evanghelie()
    s_cap = f"Text suplimentar: {caption}" if caption else ''
    u = f"""Astazi este {zi}.
Apostolul zilei: {apostol or ''}.
Evanghelia zilei: {evanghelie or ''}.
Preotul a trimis mesaj audio (transcriptie/tema): "{transcriptie}"
{s_cap}

Transforma in articol complet pentru parohie.
JSON:
{{
  "titlu_wp": "titlu inspirat din mesajul audio",
  "continut_wp": "HTML 350-400 cuvinte: integreaza natural mesajul cu lecturile zilei + meditatie + <h3>Morala</h3>",
  "fb_text": "180-200 cuvinte + hashtag-uri #ParohiaCetate2Sibiu"
}}"""
    return parse_json_robust(call_claude(SYSTEM, u, 3000))

# ============================================================
#  WEBHOOK TELEGRAM
# ============================================================
@app.route('/webhook', methods=['POST'])
def webhook():
    global pending_articol
    update = request.json
    if not update:
        return jsonify({'ok': True})

    msg = update.get('message', {})
    chat_id = str(msg.get('chat', {}).get('id', ''))

    if chat_id != TG_CHAT_ID:
        return jsonify({'ok': True})

    text    = msg.get('text', '')
    photo   = msg.get('photo')
    audio   = msg.get('audio') or msg.get('voice')
    caption = msg.get('caption', '')

    # APROBARE
    if text == '/aproba':
        if not pending_articol:
            tg_send("Nu exista articol in asteptare.")
            return jsonify({'ok': True})
        art = pending_articol
        try:
            media_id = None
            # Imagine
            if art.get('img_bytes'):
                try:
                    media_id, _ = upload_media(art['img_bytes'], 'foto.jpg', 'image/jpeg')
                except:
                    pass
            elif art.get('imagine_url'):
                try:
                    ir = requests.get(art['imagine_url'], timeout=10)
                    if ir.status_code == 200:
                        media_id, _ = upload_media(ir.content, 'foto.jpg', 'image/jpeg')
                except:
                    pass

            # Audio
            bloc_audio = ''
            if art.get('audio_bytes'):
                try:
                    _, aurl = upload_media(art['audio_bytes'], 'mesaj.ogg', 'audio/ogg')
                    if aurl:
                        bloc_audio = (
                            f'<div style="margin:20px 0;">'
                            f'<audio controls style="width:100%">'
                            f'<source src="{aurl}" type="audio/ogg">'
                            f'</audio></div>'
                        )
                except:
                    pass

            continut = (bloc_audio or '') + art.get('continut_wp', '')
            cat = art.get('categorii', [CAT_TRAIESTE])

            post_id, link = publica_articol(art['titlu_wp'], continut, cat, media_id)

            if link:
                tg_send(
                    f"Publicat pe WordPress!\n{link}\n\n"
                    f"Facebook preia automat prin Zapier."
                )
            else:
                tg_send("Eroare - verificati WordPress (wp-admin).")
            pending_articol = {}

        except Exception as e:
            tg_send(f"Eroare la publicare: {str(e)}")

    elif text.startswith('/adaug '):
        extra = text[7:].strip()
        tg_send("Regenerez cu gandul tau... (30-60 sec)")
        threading.Thread(target=genereaza_articol_zilnic, args=(extra,)).start()

    elif text == '/regenereaza':
        tg_send("Generez articol nou...")
        threading.Thread(target=genereaza_articol_zilnic).start()

    elif text == '/respinge':
        pending_articol = {}
        tg_send("Articolul a fost respins.")

    elif text in ['/start', '/help']:
        tg_send(
            "<b>Bot Parohia Cetate 2 Sibiu</b>\n\n"
            "<b>Comenzi disponibile:</b>\n"
            "/genereaza - articolul zilei\n"
            "/aproba - publica articolul curent\n"
            "/adaug [text] - adauga gand personal\n"
            "/regenereaza - alt articol\n"
            "/respinge - nu publica azi\n\n"
            "<b>Trimiteti direct:</b>\n"
            "- O fotografie (cu sau fara text)\n"
            "- Un mesaj vocal sau audio\n"
            "- Text liber - devine articol"
        )

    elif text == '/genereaza':
        tg_send("Generez articolul zilei... (30-60 secunde)")
        threading.Thread(target=genereaza_articol_zilnic).start()

    elif text == '/an_omagial':
        tg_send(f"Anul omagial: {get_an_omagial()}")

    elif photo:
        tg_send("Am primit poza. Generez... (30-60 sec)")
        def proc_photo():
            try:
                fb = tg_get_file(photo[-1]['file_id'])
                if not fb:
                    tg_send("Nu am putut descarca poza.")
                    return
                data = _gen_din_poza(base64.b64encode(fb).decode(), caption)
                data['img_bytes'] = fb
                data['categorii'] = [CAT_POSTARI_NOI, CAT_TRAIESTE]
                data['publica_wp'] = True
                trimite_spre_aprobare(data)
            except Exception as e:
                tg_send(f"Eroare poza: {str(e)}")
        threading.Thread(target=proc_photo).start()

    elif audio:
        tg_send("Am primit mesajul audio. Procesez... (30-60 sec)")
        def proc_audio():
            try:
                ab = tg_get_file(audio.get('file_id'))
                if not ab:
                    tg_send("Nu am putut descarca audio.")
                    return
                transcriptie = caption or "Mesaj duhovnicesc de la preotul parohiei"
                data = _gen_din_audio(transcriptie, caption)
                data['audio_bytes'] = ab
                data['categorii'] = [CAT_POSTARI_NOI, CAT_TRAIESTE]
                data['publica_wp'] = True
                trimite_spre_aprobare(data)
            except Exception as e:
                tg_send(f"Eroare audio: {str(e)}")
        threading.Thread(target=proc_audio).start()

    elif text and not text.startswith('/'):
        tg_send("Am primit mesajul. Generez articolul... (20-30 sec)")
        def proc_text():
            try:
                data = _gen_din_text(text)
                data['categorii'] = [CAT_POSTARI_NOI, CAT_TRAIESTE]
                data['publica_wp'] = True
                trimite_spre_aprobare(data)
            except Exception as e:
                tg_send(f"Eroare: {str(e)}")
        threading.Thread(target=proc_text).start()

    return jsonify({'ok': True})

# ============================================================
#  ENDPOINT-URI HTTP (cron jobs)
# ============================================================
@app.route('/')
def home():
    return f"Bot Parohia Cetate 2 Sibiu - activ {get_azi().strftime('%d.%m.%Y %H:%M')}"

@app.route('/genereaza')
def ep_genereaza():
    threading.Thread(target=genereaza_articol_zilnic).start()
    return jsonify({'status': 'pornit', 'ora': get_azi().strftime('%H:%M')})

@app.route('/citat')
def ep_citat():
    return ep_genereaza()

@app.route('/sfinti')
def ep_sfinti():
    return ep_genereaza()

@app.route('/mitropolit')
def ep_mitropolit():
    return ep_genereaza()

@app.route('/evanghelia')
def ep_evanghelia():
    return ep_genereaza()

@app.route('/setup_webhook')
def setup_webhook():
    url = f"https://api.telegram.org/bot{TG_TOKEN}/setWebhook?url=https://bot-parohie.onrender.com/webhook"
    r = requests.get(url, timeout=10)
    return jsonify(r.json())

@app.route('/test_wp')
def test_wp():
    r = requests.get(
        f"{WP_URL}/wp-json/wp/v2/posts?per_page=1",
        headers=wp_auth(), timeout=10
    )
    return jsonify({'status': r.status_code, 'ok': r.status_code == 200})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
