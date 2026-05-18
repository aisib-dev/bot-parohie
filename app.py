from flask import Flask, request, jsonify
from openai import OpenAI
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
GROQ_KEY      = os.environ.get('GROQ_KEY', '')
WP_URL        = os.environ.get('WP_URL', 'https://parohiacetate2.ro')
WP_USER       = os.environ.get('WP_USER', 'cetate2AI')
WP_PASS       = os.environ.get('WP_PASS', '')
TG_TOKEN      = os.environ.get('TG_TOKEN', '')
TG_CHAT_ID    = os.environ.get('TG_CHAT_ID', '')
FB_PAGE_TOKEN = os.environ.get('FB_PAGE_TOKEN', '')
FB_PAGE_ID    = os.environ.get('FB_PAGE_ID', '')

client = OpenAI(api_key=GROQ_KEY, base_url="https://api.groq.com/openai/v1")
edit_mode = None  # 'fb' sau 'wp'

PENDING_FILE = '/tmp/pending_articol.json'

def _load_pending():
    try:
        with open(PENDING_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def _save_pending(data):
    try:
        # img_bytes si audio_bytes nu se pot serializa in JSON - salvam separat
        d = {k: v for k, v in data.items() if k not in ('img_bytes', 'audio_bytes')}
        with open(PENDING_FILE, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False)
    except:
        pass

def _clear_pending():
    try:
        os.remove(PENDING_FILE)
    except:
        pass

pending_articol = _load_pending()

# ============================================================
#  CATEGORII WORDPRESS
# ============================================================
CAT_POSTARI_NOI = 41
CAT_PREDICA     = 42
CAT_TRAIESTE    = 45
CAT_CATEHEZE    = 40

# ============================================================
#  SEMNATURA AUTOR
# ============================================================
SEMNATURA_HTML = """
<div style="margin:32px 0 8px 0;padding:18px 22px;background:#fdf8f3;
border-top:2px solid #8B0000;border-bottom:1px solid #e8ddd0;
font-family:Georgia,serif;">
<p style="margin:0;color:#8B0000;font-size:15px;font-weight:bold;letter-spacing:0.3px;">
Pr. Andrei Iancu</p>
<p style="margin:4px 0 0 0;color:#666;font-size:13px;font-style:italic;">
Parohia Cetate 2 Sibiu, Mitropolia Ardealului</p>
</div>
"""

# ============================================================
#  EXPRESII INTERZISE in textul pastoral
# ============================================================
EXPRESII_INTERZISE = [
    'energie pozitiva', 'energie pozitivă', 'vibratii', 'vibrații',
    'universul ne trimite', 'universul ne', 'zi speciala', 'zi specială',
    'spiritualitate', 'karma', 'destinul ne invata', 'destinul ne învață',
    'destin', 'spirit liber', 'mindfulness', 'meditatie transcendentala',
    'energii', 'univers', 'lege a atractiei', 'legea atracției',
]

def _contine_expresii_interzise(text):
    """Returneaza lista de expresii interzise gasite in text."""
    tl = text.lower()
    return [e for e in EXPRESII_INTERZISE if e in tl]

# ============================================================
#  ISTORIC POSTARI
# ============================================================
ISTORIC_FILE = '/tmp/istoric_postari.json'

def _load_istoric():
    try:
        with open(ISTORIC_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def _append_to_istoric(entry):
    try:
        lst = _load_istoric()
        lst.append(entry)
        lst = lst[-200:]  # pastram ultimele 200
        with open(ISTORIC_FILE, 'w', encoding='utf-8') as f:
            json.dump(lst, f, ensure_ascii=False, indent=2)
    except:
        pass

def _update_istoric_status(data_str, status):
    """Actualizeaza statusul ultimei intrari din ziua data."""
    try:
        lst = _load_istoric()
        for entry in reversed(lst):
            if entry.get('data') == data_str:
                entry['status'] = status
                break
        with open(ISTORIC_FILE, 'w', encoding='utf-8') as f:
            json.dump(lst, f, ensure_ascii=False, indent=2)
    except:
        pass

# ============================================================
#  AN OMAGIAL
# ============================================================
_an_omagial_cache = {}

def get_an_omagial():
    an = datetime.datetime.now().year
    if _an_omagial_cache.get('an') == an:
        return _an_omagial_cache.get('titlu', '')
    titlu = _cauta_an_omagial(an)
    _an_omagial_cache['an'] = an
    _an_omagial_cache['titlu'] = titlu
    return titlu

def _cauta_an_omagial(an):
    headers = {'User-Agent': 'Mozilla/5.0'}
    for url in ['https://basilica.ro', 'https://patriarhia.ro', 'https://doxologia.ro']:
        try:
            r = requests.get(url, headers=headers, timeout=8)
            for pat in [r'[Aa]nul [Oo]magial[^<\n]{5,120}', r'[Aa]n [Oo]magial[^<\n]{5,120}']:
                m = re.search(pat, r.text)
                if m:
                    t = re.sub(r'<[^>]+>', '', m.group(0)).strip()
                    t = re.sub(r'\s+', ' ', t)
                    if len(t) > 15:
                        return t[:120]
        except:
            continue
    fallback = {
        2025: "Anul omagial al preotilor parohiali si al misionarilor",
        2026: "Anul omagial al familiei crestine",
        2027: "Anul omagial al Sfintei Scripturi",
    }
    return fallback.get(an, f"Anul omagial {an}")

# ============================================================
#  CITATE FAMILIE - ANUL OMAGIAL 2026
# ============================================================
CITATE_FAMILIE = [
    # Citate biblice - verificate
    ("Biblia — Efeseni 5, 25",
     "Bărbații, iubiți pe femeile voastre, după cum și Hristos a iubit Biserica și S-a dat pe Sine pentru ea."),
    ("Biblia — Efeseni 5, 33",
     "Fiecare dintre voi să-și iubească femeia ca pe sine însuși, iar femeia să se teamă de bărbat."),
    ("Biblia — Coloseni 3, 14",
     "Peste toate acestea, îmbrăcați-vă întru dragoste, care este legătura desăvârșirii."),
    ("Biblia — Coloseni 3, 20-21",
     "Copii, ascultați de părinți întru toate, căci aceasta este bine-plăcut Domnului. Părinților, nu întărâtați pe copiii voștri, ca să nu se deznădăjduiască."),
    ("Biblia — Psalmul 127, 3",
     "Fiii tăi ca niște vlăstare de măslin împrejurul mesei tale. Iată, așa se va binecuvânta omul cel ce se teme de Domnul."),
    ("Biblia — Pilde 31, 10",
     "Cine poate găsi o femeie vrednică? Ea prețuiește mai mult decât mărgăritarele."),
    ("Biblia — Matei 19, 6",
     "Ceea ce a împreunat Dumnezeu, omul să nu despartă."),
    # Sf. Ioan Gură de Aur - Omilii la Efeseni (sursa verificabila)
    ("Sf. Ioan Gură de Aur — Omilii la Efeseni",
     "Fă din casa ta o Biserică. Primește pe Hristos, căci cel care primește un sărac Îl primește pe Hristos."),
    ("Sf. Ioan Gură de Aur — Omilii la Efeseni",
     "Nimic nu este mai puternic decât un bărbat și o femeie uniți în dragoste, când aceasta are Îl are pe Hristos în mijlocul ei."),
    # ================================================================
    # ADAUGA AICI citatele tale verificate (din carti, predici, interviuri):
    # ("IPS Laurentiu Streza", "citatul exact..."),
    # ("Pr. Constantin Necula", "citatul exact..."),
    # ================================================================
]

def get_citat_familie():
    """Returneaza un citat aleator despre familie pentru Anul Omagial 2026."""
    autor, citat = random.choice(CITATE_FAMILIE)
    return autor, citat

def get_bloc_familie():
    """Bloc HTML cu citat despre familie pentru articolele WP."""
    autor, citat = get_citat_familie()
    return (
        f'<div style="background:linear-gradient(135deg,#fff5f5,#fff8f8);border:1px solid #e8c0c0;'
        f'border-left:5px solid #8B0000;padding:20px 24px;margin:24px 0;border-radius:0 8px 8px 0;'
        f'box-shadow:0 2px 8px rgba(139,0,0,0.07);">'
        f'<p style="margin:0 0 6px 0;font-size:11px;text-transform:uppercase;letter-spacing:2px;'
        f'color:#8B0000;font-weight:700;">✦ Anul Omagial al Familiei Creștine 2026</p>'
        f'<p style="margin:0 0 10px 0;font-size:15px;font-style:italic;color:#2c0000;'
        f'line-height:1.9;font-family:Georgia,serif;">&ldquo;{citat}&rdquo;</p>'
        f'<p style="margin:0;font-size:12px;color:#8B0000;font-weight:600;">— {autor}</p>'
        f'</div>'
    )

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
    (12,1):  "Ziua Nationala a Romaniei",
    (12,10): "Ziua Internationala a Drepturilor Omului",
}

def get_zi_speciala(dt=None):
    if dt is None:
        dt = datetime.datetime.now()
    return ZILE_SPECIALE.get((dt.month, dt.day))

# ============================================================
#  BLOC RESURSE HTML
# ============================================================
def get_bloc_resurse():
    an_om = get_an_omagial()
    return f"""
<div style="background:linear-gradient(135deg,#f9f5f0,#fdf8f3);
border-left:4px solid #8B0000;padding:20px 24px;margin:28px 0;
border-radius:0 8px 8px 0;font-size:14px;line-height:2.4;">

<p style="margin:0 0 10px 0;font-weight:bold;color:#8B0000;font-size:15px;
letter-spacing:0.5px;text-transform:uppercase;font-family:Georgia,serif;">
Resurse duhovnicesti</p>

<p style="margin:0 0 8px 0;">
<a href="https://doxologia.ro/rugaciuni/rugaciunile-diminetii" target="_blank"
style="color:#5a2d0c;text-decoration:none;font-weight:600;">
Rugaciunile diminetii</a>
&nbsp; | &nbsp;
<a href="https://doxologia.ro/rugaciuni/rugaciunile-serii" target="_blank"
style="color:#5a2d0c;text-decoration:none;font-weight:600;">
Rugaciunile serii</a>
&nbsp; | &nbsp;
<a href="https://doxologia.ro/viata-bisericii/acatiste-paraclise/paraclisul-maicii-domnului"
target="_blank" style="color:#5a2d0c;text-decoration:none;font-weight:600;">
Paraclisul Maicii Domnului</a>
</p>

<p style="margin:0 0 8px 0;">
<a href="https://calendar.patriarhia.ro" target="_blank"
style="color:#5a2d0c;text-decoration:none;">Calendar Ortodox Patriarhia Romana</a>
&nbsp; | &nbsp;
<a href="https://doxologia.ro/calendar-ortodox" target="_blank"
style="color:#5a2d0c;text-decoration:none;">Doxologia.ro</a>
&nbsp; | &nbsp;
<a href="https://www.mitropolia-ardealului.ro" target="_blank"
style="color:#5a2d0c;text-decoration:none;">Arhiepiscopia Sibiului</a>
</p>

<p style="margin:0 0 0 0;">
<a href="https://www.edituradeiosis.ro" target="_blank"
style="color:#5a2d0c;text-decoration:none;">Editura Deisis Sibiu</a>
&nbsp; | &nbsp;
<a href="https://catedrala-sibiu.ro" target="_blank"
style="color:#5a2d0c;text-decoration:none;">Catedrala Mitropolitana Sibiu</a>
&nbsp; | &nbsp;
<a href="https://basilica.ro" target="_blank"
style="color:#5a2d0c;text-decoration:none;">Basilica.ro</a>
&nbsp; | &nbsp;
<a href="https://ziarullumina.ro" target="_blank"
style="color:#5a2d0c;text-decoration:none;">Ziarul Lumina</a>
&nbsp; | &nbsp;
<a href="https://www.bibliortodoxa.ro" target="_blank"
style="color:#5a2d0c;text-decoration:none;">Biblia Ortodoxa</a>
</p>

<p style="margin:10px 0 0 0;font-style:italic;color:#8B0000;font-size:13px;
border-top:1px solid #ddd;padding-top:10px;font-family:Georgia,serif;">
{an_om} &mdash; Patriarhia Romana</p>
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

def calc_paste_ortodox(year):
    """Calculeaza data Pastelui Ortodox (Gregorian) pentru orice an."""
    a = year % 4
    b = year % 7
    c = year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = ((d + e + 114) % 31) + 1
    # Data iuliana -> gregoriana (+13 zile, valabil 1900-2099)
    return datetime.date(year, month, day) + datetime.timedelta(days=13)

def get_posturi_an(year):
    """Returneaza listele de posturi pentru un an, calculate dinamic."""
    paste = calc_paste_ortodox(year)
    # Postul Mare: de luni pana sambata din Saptamana Floriilor (48 zile inainte)
    post_mare_start = paste - datetime.timedelta(days=48)
    post_mare_end   = paste - datetime.timedelta(days=8)
    # Postul Apostolilor: luni dupa Rusalii (Paste+56) pana pe 28 iunie
    rusalii = paste + datetime.timedelta(days=49)
    post_ap_start = rusalii + datetime.timedelta(days=8)
    post_ap_end   = datetime.date(year, 6, 28)
    # Postul Adormirii: 1-14 august (fix)
    post_ad_start = datetime.date(year, 8, 1)
    post_ad_end   = datetime.date(year, 8, 14)
    # Postul Craciunului: 15 nov - 24 dec (fix)
    post_cr_start = datetime.date(year, 11, 15)
    post_cr_end   = datetime.date(year, 12, 24)
    return [
        (post_mare_start, post_mare_end,   "Postul Mare"),
        (post_ap_start,   post_ap_end,     "Postul Sfintilor Apostoli"),
        (post_ad_start,   post_ad_end,     "Postul Adormirii Maicii Domnului"),
        (post_cr_start,   post_cr_end,     "Postul Craciunului"),
    ]

def get_tip_zi(dt=None):
    if dt is None:
        dt = get_azi()
    ziua    = (dt.month, dt.day)
    zi_sapt = dt.weekday()
    azi_date = dt.date() if hasattr(dt, 'date') else dt

    paste = calc_paste_ortodox(dt.year)

    # Saptamana Mare: 6 zile inainte de Paste
    saptamana_mare_dates = {paste - datetime.timedelta(days=i) for i in range(1, 7)}
    if azi_date in saptamana_mare_dates:
        return 'saptamana_mare'

    # Sarbatori mari fixe
    sarbatori = {
        (1,1),(1,6),(1,7),(2,2),(3,25),(8,6),(8,15),
        (9,8),(9,14),(11,8),(11,30),(12,6),(12,25),(12,26)
    }
    if ziua in sarbatori:
        return 'sarbatoare'

    posturi = get_posturi_an(dt.year)
    inceputuri = {p[0] for p in posturi}
    in_post = any(s <= azi_date <= e for s, e, _ in posturi)

    if azi_date in inceputuri:
        return 'inceput_post'
    if zi_sapt == 6:
        return 'duminica'
    if in_post and zi_sapt in [2, 4]:
        return 'post'
    if in_post:
        return 'post_saptamana'
    return 'obisnuit'

def get_nume_saptamana_mare(dt=None):
    if dt is None:
        dt = get_azi()
    paste = calc_paste_ortodox(dt.year)
    azi_date = dt.date() if hasattr(dt, 'date') else dt
    teme = [
        ("Lunea Mare",     "Iosif cel Prea Frumos si smochinul neroditor"),
        ("Martea Mare",    "Parabolele Mantuitorului si semnele sfarsitului"),
        ("Miercurea Mare", "Ungerea cu mir la Betania si vanzarea lui Iuda"),
        ("Joia Mare",      "Cina cea de Taina si rugaciunea din Ghetsimani"),
        ("Vinerea Mare",   "Patimile, Rastignirea si Moartea Domnului"),
        ("Sambata Mare",   "Prohodul Domnului - intre moarte si Inviere"),
    ]
    for i, (titlu, tema) in enumerate(teme):
        zi_sm = paste - datetime.timedelta(days=6 - i)
        if zi_sm == azi_date:
            return titlu, tema
    return "Saptamana Mare", ""

def get_nume_sarbatoare(dt):
    s = {
        (1,1):"Taierea Imprejur / Sf. Vasile cel Mare",
        (1,6):"Botezul Domnului",(1,7):"Soborul Sf. Ioan Botezatorul",
        (2,2):"Intampinarea Domnului",(3,25):"Buna Vestire",
        (8,6):"Schimbarea la Fata",(8,15):"Adormirea Maicii Domnului",
        (9,8):"Nasterea Maicii Domnului",(9,14):"Inaltarea Sfintei Cruci",
        (11,8):"Soborul Sfintilor Arhangheli",(11,30):"Sf. Apostol Andrei",
        (12,6):"Sf. Ierarh Nicolae",(12,25):"Nasterea Domnului",
        (12,26):"A doua zi de Craciun",
    }
    return s.get((dt.month,dt.day), "Sarbatoare")

def get_nume_post(dt):
    azi_date = dt.date() if hasattr(dt, 'date') else dt
    for start, end, nume in get_posturi_an(dt.year):
        if azi_date == start:
            return nume
    return "Postul"

# ============================================================
#  BIBLIA ORTODOXA - ID-uri carti verificate (bibliaortodoxa.ro)
# ============================================================
BIBLIA_BOOK_IDS = {
    # Vechiul Testament
    'facerea': 25, 'geneza': 25,
    'iesirea': 32, 'exodul': 32, 'exod': 32,
    'leviticul': 47, 'levitic': 47,
    'numerii': 59,
    'deuteronomul': 17, 'deuteronom': 17,
    'iosua': 41, 'iosua navi': 41,
    'judecatori': 46,
    'rut': 71,
    '1 regi': 66, 'i regi': 66,
    '2 regi': 67, 'ii regi': 67,
    '3 regi': 68, 'iii regi': 68,
    '4 regi': 69, 'iv regi': 69,
    'psalmi': 65, 'psalm': 65, 'psalmul': 65,
    'pilde': 63, 'proverbe': 63,
    'ecclesiastul': 18, 'ecclesiast': 18,
    'cantarea cantarilor': 9, 'cantari': 9,
    'isaia': 43,
    'ieremia': 31,
    'plangeri': 64,
    'iezechiel': 33, 'ezechiel': 33,
    'daniel': 16,
    # Noul Testament
    'matei': 55,
    'marcu': 53,
    'luca': 48,
    'ioan': 35,
    'faptele apostolilor': 26, 'faptele': 26, 'fapte': 26,
    'romani': 70,
    '1 corinteni': 12, 'i corinteni': 12,
    '2 corinteni': 13, 'ii corinteni': 13,
    'galateni': 29,
    'efeseni': 19,
    'filipeni': 28,
    'coloseni': 10,
    '1 tesaloniceni': 76, 'i tesaloniceni': 76,
    '2 tesaloniceni': 77, 'ii tesaloniceni': 77,
    '1 timotei': 78, 'i timotei': 78,
    '2 timotei': 79, 'ii timotei': 79,
    'tit': 80,
    'filimon': 27,
    'evrei': 22,
    'iacov': 30,
    '1 petru': 61, 'i petru': 61,
    '2 petru': 62, 'ii petru': 62,
    '1 ioan': 36, 'i ioan': 36,
    '2 ioan': 37, 'ii ioan': 37,
    '3 ioan': 38, 'iii ioan': 38,
    'iuda': 44,
    'apocalipsa': 4,
}

# ============================================================
#  ZiData - structura date liturgice zilnice
# ============================================================
def new_zi_data(dt):
    return {
        'date': dt.strftime('%Y-%m-%d'),
        'saints': [],
        'apostle': {'reference': '', 'text': ''},
        'gospel':  {'reference': '', 'text': ''},
        'selected_verse': {'reference': '', 'text': '', 'source_url': '', 'verified': False},
        'pastoral_reflection': '',
        'pastoral_variants': {},
        'sources': {
            'doxologia': 'https://doxologia.ro/calendar-ortodox',
            'biblia_ortodoxa': 'https://www.bibliaortodoxa.ro',
        },
        'warnings': [],
    }

def _parse_calendar_zi_section(section):
    """Din continutul unui div.calendar-zi extrage sfinti, apostol, evanghelie."""
    saints, ap_ref, ev_ref = [], '', ''
    for link in re.finditer(r'<a[^>]+class="([^"]*)"[^>]*>\s*([^<]{3,150}?)\s*</a>', section):
        cls, txt = link.group(1), link.group(2).strip()
        if not txt:
            continue
        if 'ev-zi' in cls:
            tl = txt.lower()
            if tl.startswith('ap.') or tl.startswith('ap '):
                ap_ref = txt
            elif tl.startswith('ev.') or tl.startswith('ev '):
                ev_ref = txt
        else:
            saints.append(txt)
    return list(dict.fromkeys(saints)), ap_ref, ev_ref

def fetch_doxologia_calendar(dt):
    """Preia calendarul ortodox complet de pe doxologia.ro.
    Structura reala: div.calendar-zi cu linkuri sfinti + linkuri class=ev-zi pentru lecturi.
    """
    zi_data = new_zi_data(dt)
    try:
        h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        r = requests.get('https://doxologia.ro/calendar-ortodox', headers=h, timeout=12)
        if r.status_code != 200:
            zi_data['warnings'].append('doxologia.ro indisponibil')
            return zi_data
        html = r.text

        # Gaseste ziua curenta: ancora href="/DD-luna" cu textul DD,
        # urmata de div.calendar-zi
        day = dt.day
        pat_day = (
            r'href="/' + str(day) + r'-[a-z\-]+"[^>]*>\s*'
            + str(day) + r'\s*</a>'
            + r'[\s\S]{0,300}?'
            + r'<div[^>]*class="[^"]*calendar-zi[^"]*"[^>]*>([\s\S]*?)</div>'
        )
        m = re.search(pat_day, html)
        if not m:
            # Fallback: primul calendar-zi din pagina (ziua curenta)
            m = re.search(r'<div[^>]*class="[^"]*calendar-zi[^"]*"[^>]*>([\s\S]*?)</div>', html)
        if not m:
            zi_data['warnings'].append('Nu s-au gasit date pe doxologia.ro')
            return zi_data

        saints, ap_ref, ev_ref = _parse_calendar_zi_section(m.group(1))
        zi_data['saints']  = saints
        zi_data['apostle'] = {'reference': ap_ref, 'text': ''}
        zi_data['gospel']  = {'reference': ev_ref, 'text': ''}

        if not saints:
            zi_data['warnings'].append('Nu s-au gasit sfinti pe doxologia.ro')
        if not ap_ref:
            zi_data['warnings'].append('Apostolul nu a putut fi extras')
        if not ev_ref:
            zi_data['warnings'].append('Evanghelia nu a putut fi extrasa')
    except Exception as e:
        zi_data['warnings'].append(f'Eroare doxologia.ro: {str(e)[:80]}')
    return zi_data

def _normalize_biblia_ref(ref):
    """Elimina prefixele liturgice din referinta biblica."""
    ref = ref.strip()
    ref = re.sub(
        r'^(?:Apostolul\s*|Apostol\s*|Ap\.\s*|Evanghelia\s*|Evanghelie\s*|Ev\.\s*)',
        '', ref, flags=re.IGNORECASE
    ).strip()
    return ref

def _lookup_book(book_raw):
    """Cauta book_id dupa numele cartii. Returneaza (book_id, key_matched)."""
    book_lower = book_raw.lower().strip()
    if book_lower in BIBLIA_BOOK_IDS:
        return BIBLIA_BOOK_IDS[book_lower], book_lower
    # Potrivire partiala: cel mai lung key care se potriveste castiga
    best_key, best_id = '', None
    for key, bid in BIBLIA_BOOK_IDS.items():
        if (key in book_lower or book_lower in key) and len(key) > len(best_key):
            best_key, best_id = key, bid
    return best_id, best_key or None

def _split_multi_chapter_ref(norm_ref):
    """
    Parseaza referinte simple si multi-capitol (separate prin ";").
    Exemplu: "Fapte 8, 40; 9, 1-19"
    Returneaza (lista_segmente, eroare_string).
    Fiecare segment: (book_id, book_name, chapter, v_start, v_end).
    """
    m = re.match(r'^([1-3]?\s*[A-Za-zÀ-žăâîșțĂÂÎȘȚ\s]+?)\s+(\d+.*)', norm_ref)
    if not m:
        return None, f"Formatul referintei nu a fost recunoscut: '{norm_ref}'"
    book_raw = m.group(1).strip()
    rest     = m.group(2).strip()

    book_id, book_key = _lookup_book(book_raw)
    if not book_id:
        return None, f"Cartea '{book_raw}' nu a fost gasita in dictionar"

    segments = []
    for seg in rest.split(';'):
        seg = seg.strip()
        sm = re.match(r'(\d+)(?:\s*[,\s]\s*(\d+)(?:\s*[-–]\s*(\d+))?)?', seg)
        if sm:
            chap  = int(sm.group(1))
            vs    = int(sm.group(2)) if sm.group(2) else None
            ve    = int(sm.group(3)) if sm.group(3) else vs
            segments.append((book_id, book_raw, chap, vs, ve))

    if not segments:
        return None, f"Niciun segment valid in '{rest}'"
    return segments, None

def fetch_biblia_ortodoxa_verse(reference):
    """Preia versete de pe bibliaortodoxa.ro cu suport multi-capitol si debug."""
    debug = {
        'ref_received':   reference,
        'ref_normalized': '',
        'book_detected':  '',
        'segments':       [],
        'urls_accessed':  [],
        'verses_found':   0,
        'reason_failure': '',
    }

    if not reference:
        debug['reason_failure'] = 'Referinta goala'
        return {
            'reference': reference, 'text': '', 'source_url': '', 'verified': False,
            'warning': 'Nu s-a putut verifica automat textul biblic pe bibliaortodoxa.ro',
            'debug': debug,
        }

    norm = _normalize_biblia_ref(reference)
    debug['ref_normalized'] = norm

    segments, err = _split_multi_chapter_ref(norm)
    if not segments:
        debug['reason_failure'] = err or 'Parsare esuata'
        return {
            'reference': reference, 'text': '', 'source_url': '', 'verified': False,
            'warning': 'Nu s-a putut verifica automat textul biblic pe bibliaortodoxa.ro',
            'debug': debug,
        }

    debug['book_detected'] = segments[0][1]
    debug['segments'] = [
        {'chapter': s[2], 'v_start': s[3], 'v_end': s[4]} for s in segments
    ]

    all_verses = []
    last_url = ''
    for book_id, book_name, chapter, v_start, v_end in segments:
        url = f'https://www.bibliaortodoxa.ro/carte.php?cap={chapter}&id={book_id}'
        last_url = url
        debug['urls_accessed'].append(url)
        try:
            h = {'User-Agent': 'Mozilla/5.0'}
            r = requests.get(url, headers=h, timeout=12)
            if r.status_code != 200:
                debug['reason_failure'] += f'HTTP {r.status_code} la cap={chapter}; '
                continue
            versete = re.findall(
                r'<tr[^>]*id=verset(\d+)[^>]*>[\s\S]*?<td[^>]*>[\s\S]*?</td>\s*<td>([\s\S]*?)</td>\s*</tr>',
                r.text
            )
            if not versete:
                debug['reason_failure'] += f'Niciun <tr id=versetN> la cap={chapter}; '
                continue
            vs = v_start if v_start is not None else 1
            ve = v_end   if v_end   is not None else 9999
            for vnum, vtext in versete:
                n = int(vnum)
                if vs <= n <= ve:
                    clean = re.sub(r'<[^>]+>', '', vtext).strip()
                    clean = re.sub(r'\s+', ' ', clean)
                    if clean:
                        all_verses.append(clean)
        except Exception as e:
            debug['reason_failure'] += f'Exceptie cap={chapter}: {str(e)[:60]}; '

    debug['verses_found'] = len(all_verses)

    if not all_verses:
        if not debug['reason_failure']:
            debug['reason_failure'] = 'Versetele cerute nu au fost gasite in pagina'
        return {
            'reference': reference, 'text': '', 'source_url': last_url, 'verified': False,
            'warning': 'Nu s-a putut verifica automat textul biblic pe bibliaortodoxa.ro',
            'debug': debug,
        }

    text = ' '.join(all_verses)[:800]
    return {
        'reference': reference,
        'text': text,
        'source_url': last_url,
        'verified': True,
        'debug': debug,
    }

def scrape_pilde_solomon():
    """Fallback: Capitol din Pilde si Intelepciunea lui Solomon"""
    pilde = [
        "Pilde 3, 1-18: Fericita este omul care a aflat intelepciunea si muritorul care a castigat priceperea.",
        "Pilde 4, 1-9: Ascultati, fiilor, invatatura parintelui vostru si luati aminte, ca sa cunoasteti intelepciunea.",
        "Pilde 8, 1-21: Nu striga oare intelepciunea? Nu-si ridica oare glasul priceperea?",
        "Pilde 10, 1-12: Un fiu intelept bucura pe tatal sau, dar un fiu nebun e mahnirea mamei sale.",
        "Pilde 15, 1-17: Un raspuns bland potoleste mania, dar un cuvant aspru ata intarata.",
        "Pilde 22, 1-16: Mai de pret decat bogatia mare este un nume bun.",
    ]
    solomon = [
        "Intelepciunea lui Solomon 1, 1-15: Iubiti dreptatea, voi cei ce carmuiti pamantul.",
        "Intelepciunea lui Solomon 3, 1-9: Sufletele drepților sunt in mana lui Dumnezeu.",
        "Intelepciunea lui Solomon 7, 24-30: Intelepciunea este mai miscatoare decat orice miscare.",
        "Intelepciunea lui Solomon 9, 1-12: Dumnezeul parintilor si Doamne al milostivirii.",
        "Intelepciunea lui Solomon 11, 21-26: In mana Ta este intreaga lume ca un graunte.",
    ]
    return random.choice(pilde), random.choice(solomon)

WIKIMEDIA_IMAGINI = {
    'craciun':   'https://upload.wikimedia.org/wikipedia/commons/8/8c/Nativity_icon_Sinai_12th_century.jpg',
    'paste':     'https://upload.wikimedia.org/wikipedia/commons/b/b4/The_Resurrection_icon_%28Greek%2C_16th_c%29.jpg',
    'florii':    'https://upload.wikimedia.org/wikipedia/commons/b/b2/Entry_into_Jerusalem_%28Pskov%2C_16c%29.jpg',
    'boboteaza': 'https://upload.wikimedia.org/wikipedia/commons/a/a5/Theophany_icon_%28Yaroslavl%2C_17th_c.%29.jpg',
    'post':      'https://upload.wikimedia.org/wikipedia/commons/5/5b/Christ_in_the_Wilderness_-_Ivan_Kramskoy_-_1872.jpg',
    'maica':     'https://upload.wikimedia.org/wikipedia/commons/1/1b/Theotokos_of_Vladimir.jpg',
    'cruce':     'https://upload.wikimedia.org/wikipedia/commons/1/17/Crucifixion_icon_sinai_10c.jpg',
    'nicolae':   'https://upload.wikimedia.org/wikipedia/commons/0/04/Saint_Nicholas_icon_%28Lipnya_church%2C_Novgorod%29.jpg',
    'schimbare': 'https://upload.wikimedia.org/wikipedia/commons/3/38/Transfiguration_by_Feofan_Grek.jpg',
    'inaltare':  'https://upload.wikimedia.org/wikipedia/commons/4/46/Ascension_icon_%28Yaroslavl%2C_16th_c%29.jpg',
    'default':   'https://upload.wikimedia.org/wikipedia/commons/d/d9/Christ_Pantocrator_mosaic_from_Hagia_Sophia.jpg',
}

def _verify_image_url(url, timeout=6):
    """Verifica daca URL-ul imaginii este accesibil. Returneaza (ok, status_code)."""
    try:
        r = requests.head(url, timeout=timeout,
                          headers={'User-Agent': 'Mozilla/5.0'},
                          allow_redirects=True)
        return r.status_code == 200, r.status_code
    except Exception as e:
        return False, str(e)[:60]

def get_imagine_doxologia(query=''):
    """Incearca sa ia imagine reala de pe doxologia.ro"""
    try:
        h = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get('https://doxologia.ro/calendar-ortodox', headers=h, timeout=10)
        imgs = re.findall(
            r'<img[^>]+src=["\']([^"\']*(?:doxologia\.ro|basilica\.ro)[^"\']*\.jpg)["\']',
            r.text
        )
        for img in imgs:
            if 'icon' not in img.lower() and 'logo' not in img.lower() and 'thumb' not in img.lower():
                ok, _ = _verify_image_url(img)
                if ok:
                    return img
    except:
        pass
    return None

def get_imagine_fallback(query=''):
    """Selecteaza URL Wikimedia dupa cuvant-cheie (fara verificare)."""
    q = query.lower()
    for k, v in WIKIMEDIA_IMAGINI.items():
        if k in q:
            return v
    return WIKIMEDIA_IMAGINI['default']

def get_imagine_with_status(query='', base_url=''):
    """
    Returneaza un dict cu URL final si stare verificare:
    {url, verified, fallback_used, tried_url, status_code, is_local}
    """
    local_static = (base_url.rstrip('/') + '/static/images/calendar-ortodox-default.jpg'
                    if base_url else '/static/images/calendar-ortodox-default.jpg')

    # 1. Incearca doxologia
    dox_url = get_imagine_doxologia(query)
    if dox_url:
        return {
            'url': dox_url, 'verified': True,
            'fallback_used': False, 'tried_url': dox_url,
            'status_code': 200, 'is_local': False,
        }

    # 2. Wikimedia fallback cu verificare
    wiki_url = get_imagine_fallback(query)
    ok, code = _verify_image_url(wiki_url)
    if ok:
        return {
            'url': wiki_url, 'verified': True,
            'fallback_used': True, 'tried_url': wiki_url,
            'status_code': code, 'is_local': False,
        }

    # 3. Local static fallback (intotdeauna disponibil)
    return {
        'url': local_static, 'verified': True,
        'fallback_used': True, 'tried_url': wiki_url,
        'status_code': code, 'is_local': True,
    }

def get_imagine(tip='', query='', base_url=''):
    result = get_imagine_with_status(query + ' ' + tip, base_url)
    return result['url']

# ============================================================
#  PIPELINE POST - validare, reflectie, constructie FB/TG
# ============================================================
def validate_post_data(zi_data):
    """Adauga avertismente pentru datele liturgice lipsa sau neverificate."""
    if not zi_data['saints']:
        zi_data['warnings'].append('⚠ Sfintii zilei lipsesc')
    if not zi_data['apostle']['reference']:
        zi_data['warnings'].append('⚠ Referinta Apostolului lipseste')
    if not zi_data['gospel']['reference']:
        zi_data['warnings'].append('⚠ Referinta Evangheliei lipseste')
    if not zi_data['selected_verse']['verified']:
        zi_data['warnings'].append('⚠ Versetul nu a putut fi verificat pe bibliaortodoxa.ro')
    return zi_data

def _make_zi_context(zi_data):
    saints_str = ', '.join(zi_data['saints']) if zi_data['saints'] else 'Sfintii zilei'
    ap_ref = zi_data['apostle'].get('reference', '')
    ev_ref = zi_data['gospel'].get('reference', '')
    v_ref  = zi_data['selected_verse'].get('reference', '')
    v_text = zi_data['selected_verse'].get('text', '')
    ctx = (
        f"Sfintii zilei: {saints_str}.\n"
        f"Apostolul: {ap_ref}.\n"
        f"Evanghelia: {ev_ref}.\n"
    )
    if v_text:
        ctx += f'Verset ales: {v_ref} — \"{v_text}\"\n'
    return ctx

SYS_PASTORAL = (
    "Esti un preot ortodox roman care scrie reflectii pastorale scurte, calde, sobru. "
    "Tonul tau este ca al Parintelui Constantin Necula — aproape de om, concret, fara academism. "
    "NU inventa citate patristice. NU folosi expresii ca: energie pozitiva, vibratii, "
    "universul ne trimite, spiritualitate, karma, destin, zi speciala, mindfulness, energii. "
    "Raspunde STRICT cu textul cerut, fara titluri, fara numerotare, fara hashtag-uri."
)

def generate_pastoral_reflection(zi_data):
    """Returneaza o singura reflectie pastorala (3-6 fraze). Retried daca contine expresii interzise."""
    ctx = _make_zi_context(zi_data)
    prompt = (
        ctx
        + "\nScrie 3-6 fraze pastorale calde, concrete, umane. "
        "Fara titluri. Fara hashtag-uri. Fara citate patristice inventate."
    )
    for _ in range(3):
        try:
            text = call_claude(SYS_PASTORAL, prompt, 600).strip()
            bad = _contine_expresii_interzise(text)
            if not bad:
                return text
            prompt = (
                ctx
                + f"\nATENTIE: textul anterior contine expresii interzise ({', '.join(bad)}). "
                "Rescrie fara aceste expresii. Pastreaza tonul ortodox, cald, sobru. 3-6 fraze."
            )
        except Exception:
            break
    return ''

def generate_pastoral_variants(zi_data):
    """Genereaza 3 variante de Cuvant de folos cu stiluri diferite.
    Returneaza {'scurt': ..., 'duhovnicesc': ..., 'catehetic': ...}
    """
    ctx = _make_zi_context(zi_data)
    styles = {
        'scurt': (
            ctx
            + "\nScrie o reflectie SCURTA si CALDA — 2-3 fraze simple, directe, aproape de om. "
            "Fara titluri."
        ),
        'duhovnicesc': (
            ctx
            + "\nScrie o reflectie DUHOVNICEASCA — 3-5 fraze cu profunzime ortodoxa, "
            "referire la Evanghelie si invitatie la rugaciune. Fara titluri."
        ),
        'catehetic': (
            ctx
            + "\nScrie o reflectie CATEHETICA — 3-5 fraze cu explicatie clara a lectiei zilei, "
            "potrivita pentru familia crestina si tineri. Fara titluri."
        ),
    }
    results = {}
    for key, prompt in styles.items():
        for _ in range(2):
            try:
                text = call_claude(SYS_PASTORAL, prompt, 600).strip()
                bad = _contine_expresii_interzise(text)
                if not bad:
                    results[key] = text
                    break
                prompt += f"\nATENTIE: evita expresiile ({', '.join(bad)})."
            except Exception:
                break
        if key not in results:
            results[key] = ''
    return results

def build_facebook_post(zi_data):
    """Construieste postarea FB structurata cu emoji-uri, conform formatului pastoral."""
    saints    = zi_data.get('saints', [])
    ap_ref    = zi_data['apostle'].get('reference', '')
    ev_ref    = zi_data['gospel'].get('reference', '')
    v_ref     = zi_data['selected_verse'].get('reference', '')
    v_text    = zi_data['selected_verse'].get('text', '')
    reflection = zi_data.get('pastoral_reflection', '')

    parts = []
    if saints:
        parts.append(f"🕊️ Sfinții zilei\nAstăzi îi pomenim pe: {', '.join(saints)}.")
    if ap_ref:
        parts.append(f"📖 Apostolul zilei\n{ap_ref}")
    if ev_ref:
        parts.append(f"✝️ Evanghelia zilei\n{ev_ref}")
    if v_text and v_ref:
        parts.append(f'„{v_text}”\n({v_ref})')
    if reflection:
        parts.append(f"Cuvânt de folos:\n{reflection}")
    parts.append("🙏 Doamne, ajută-ne să întâmpinăm ziua cu pace, credință și inimă bună.")
    parts.append("#ParohiaCetate2 #CalendarOrtodox #SfintiiZilei #EvangheliaZilei")
    return '\n\n'.join(parts)

def build_telegram_preview(zi_data, titlu_wp=''):
    """Preview Telegram cu surse verificate, 3 variante cuvant de folos si avertismente."""
    saints_str = ', '.join(zi_data['saints']) if zi_data['saints'] else '—'
    ap_ref  = zi_data['apostle'].get('reference', '—')
    ev_ref  = zi_data['gospel'].get('reference', '—')
    v_ref   = zi_data['selected_verse'].get('reference', '')
    v_ok    = zi_data['selected_verse'].get('verified', False)
    v_url   = zi_data['selected_verse'].get('source_url', '')
    warnings = zi_data.get('warnings', [])
    variants = zi_data.get('pastoral_variants', {})

    lines = ['<b>ARTICOL GENERAT</b>']
    if titlu_wp:
        lines.append(f'<b>{titlu_wp}</b>')
    lines.append('')
    lines.append(f'<b>Sfinții zilei:</b> <a href="https://doxologia.ro/calendar-ortodox">{saints_str}</a>')
    if ap_ref != '—':
        lines.append(f'<b>Apostolul:</b> {ap_ref}')
    if ev_ref != '—':
        lines.append(f'<b>Evanghelia:</b> {ev_ref}')
    if v_ref:
        icon = '✓' if v_ok else '⚠'
        if not v_ok:
            lines.append(f'<b>Verset ({icon}):</b> {v_ref}')
            lines.append('<i>⚠ Facebook nu va fi publicat fara verset verificat.</i>')
        elif v_url:
            lines.append(f'<b>Verset ({icon}):</b> <a href="{v_url}">{v_ref}</a>')
        else:
            lines.append(f'<b>Verset ({icon}):</b> {v_ref}')

    # 3 variante cuvant de folos
    if variants:
        lines.append('')
        lines.append('<b>💬 Cuvânt de folos — 3 variante:</b>')
        labels = {'scurt': '1️⃣ Scurt și cald', 'duhovnicesc': '2️⃣ Duhovnicesc', 'catehetic': '3️⃣ Catehetic'}
        for key, label in labels.items():
            txt = variants.get(key, '')
            if txt:
                lines.append(f'\n<b>{label}:</b>\n{txt}')

    lines.append('')
    lines.append(
        '📚 Surse: <a href="https://doxologia.ro/calendar-ortodox">Doxologia</a> | '
        '<a href="https://www.bibliaortodoxa.ro">Biblia Ortodoxă</a>'
    )
    if warnings:
        lines.append('')
        lines.append('<b>Atenție:</b>')
        for w in warnings:
            lines.append(f'  {w}')
    lines.append('')
    lines.append('<b>Comenzi:</b>')
    lines.append('/aproba — WP + Facebook')
    lines.append('/aproba_fb — doar Facebook')
    lines.append('/aproba_wp — doar WordPress')
    lines.append('/adaug [text] — adaugă gând personal')
    lines.append('/regenereaza_cuvant — regenerează cuvântul de folos')
    lines.append('/editeaza_fb — editează textul Facebook')
    lines.append('/editeaza_wp — editează titlul și conținutul WP')
    lines.append('/regenereaza — articol nou complet')
    lines.append('/respinge — nu publica azi')
    return '\n'.join(lines)

def _get_inline_keyboard_cuvant():
    return {
        'inline_keyboard': [[
            {'text': '🔁 Regenerează cuvântul de folos', 'callback_data': 'regen_cuvant'}
        ]]
    }

# ============================================================
#  VIDEO RESURSE (Saptamana Mare)
# ============================================================
def get_video_resurse_saptamana_mare(titlu_zi):
    """Returneaza bloc HTML cu resurse video pentru Saptamana Mare"""
    videos = {
        'Lunea Mare': 'https://www.youtube.com/results?search_query=IPS+Laurentiu+Streza+Lunea+Mare',
        'Martea Mare': 'https://www.youtube.com/results?search_query=IPS+Laurentiu+Streza+Martea+Mare',
        'Miercurea Mare': 'https://www.youtube.com/results?search_query=IPS+Laurentiu+Streza+Miercurea+Mare',
        'Joia Mare': 'https://www.youtube.com/results?search_query=IPS+Laurentiu+Streza+Joia+Mare',
        'Vinerea Mare': 'https://www.youtube.com/results?search_query=IPS+Laurentiu+Streza+Vinerea+Mare',
        'Sambata Mare': 'https://www.youtube.com/results?search_query=IPS+Laurentiu+Streza+Sambata+Mare',
    }
    yt_link = videos.get(titlu_zi, 'https://www.youtube.com/@MitropoliaArdealului')

    return f"""
<div style="background:#1a1a2e;border-radius:10px;padding:20px 24px;margin:28px 0;color:#fff;">
<p style="margin:0 0 12px 0;font-size:15px;font-weight:bold;color:#c9a227;
font-family:Georgia,serif;letter-spacing:0.3px;">
Resurse video pentru {titlu_zi}</p>
<p style="margin:0 0 10px 0;font-size:14px;line-height:1.8;">
<a href="{yt_link}" target="_blank"
style="color:#4fc3f7;text-decoration:none;font-weight:600;">
IPS Laurentiu Streza - cuvant pentru {titlu_zi}</a>
</p>
<p style="margin:0 0 10px 0;font-size:14px;line-height:1.8;">
<a href="https://www.youtube.com/results?search_query=Sorin+Mihalache+Saptamana+Mare"
target="_blank" style="color:#4fc3f7;text-decoration:none;">
Pr. Sorin Mihalache - meditatie pentru Saptamana Patimilor</a>
</p>
<p style="margin:0;font-size:14px;line-height:1.8;">
<a href="https://www.youtube.com/results?search_query=Chilia+Athonita+Saptamana+Mare"
target="_blank" style="color:#4fc3f7;text-decoration:none;">
Chilia Athonita - duhovnicie pentru Saptamana Mare</a>
</p>
</div>
"""

# ============================================================
#  WORDPRESS
# ============================================================
def wp_auth():
    enc = base64.b64encode(f"{WP_USER}:{WP_PASS}".encode()).decode()
    return {'Authorization': f'Basic {enc}', 'Content-Type': 'application/json'}

def publica_articol(titlu, continut, categorii=None, featured_media=None):
    if categorii is None:
        categorii = [CAT_TRAIESTE]
    continut_final = continut + WIDGET_DOXOLOGIA + SEMNATURA_HTML + get_bloc_resurse()
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

def publica_facebook(text, link='', img_bytes=None, img_url=None):
    """Posteaza direct pe pagina de Facebook prin Graph API."""
    if not FB_PAGE_TOKEN or not FB_PAGE_ID:
        return None, "FB_PAGE_TOKEN sau FB_PAGE_ID lipsa in variabilele de mediu"
    try:
        # Cu poza binara (trimisa de preot pe Telegram)
        if img_bytes:
            r = requests.post(
                f"https://graph.facebook.com/v20.0/{FB_PAGE_ID}/photos",
                data={'caption': text, 'access_token': FB_PAGE_TOKEN},
                files={'source': ('photo.jpg', img_bytes, 'image/jpeg')},
                timeout=60
            )
            res = r.json()
            if 'id' in res or 'post_id' in res:
                return res.get('post_id') or res.get('id'), ''
            return None, res.get('error', {}).get('message', str(res))
        # Cu poza din URL (verificam inainte ca FB sa o respinga)
        if img_url:
            img_ok, _ = _verify_image_url(img_url)
            if img_ok:
                r = requests.post(
                    f"https://graph.facebook.com/v20.0/{FB_PAGE_ID}/photos",
                    data={'caption': text, 'url': img_url, 'access_token': FB_PAGE_TOKEN},
                    timeout=30
                )
                res = r.json()
                if 'id' in res or 'post_id' in res:
                    return res.get('post_id') or res.get('id'), ''
            # Daca imaginea nu e accesibila sau FB o respinge, fallback la text
        # Text simplu (cu sau fara link WP)
        payload = {'message': text, 'access_token': FB_PAGE_TOKEN}
        if link:
            payload['link'] = link
        r = requests.post(
            f"https://graph.facebook.com/v20.0/{FB_PAGE_ID}/feed",
            data=payload, timeout=30
        )
        res = r.json()
        if 'id' in res:
            return res['id'], ''
        return None, res.get('error', {}).get('message', str(res))
    except Exception as e:
        return None, str(e)

def upload_media(data_bytes, filename, mime):
    enc = base64.b64encode(f"{WP_USER}:{WP_PASS}".encode()).decode()
    h = {
        'Authorization': f'Basic {enc}',
        'Content-Type': mime,
        'Content-Disposition': f'attachment; filename={filename}'
    }
    r = requests.post(f"{WP_URL}/wp-json/wp/v2/media",
                      data=data_bytes, headers=h, timeout=60)
    res = r.json()
    return res.get('id'), res.get('source_url', '')

# ============================================================
#  TELEGRAM
# ============================================================
def tg_send(text, chat_id=None, reply_markup=None):
    if not TG_TOKEN:
        return
    cid = chat_id or TG_CHAT_ID
    if not cid:
        return
    try:
        payload = {'chat_id': cid, 'text': text, 'parse_mode': 'HTML'}
        if reply_markup:
            payload['reply_markup'] = reply_markup
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json=payload, timeout=10
        )
    except:
        pass

def tg_answer_callback(callback_query_id, text=''):
    if not TG_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/answerCallbackQuery",
            json={'callback_query_id': callback_query_id, 'text': text},
            timeout=5
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
    _save_pending(articol)

    # Salveaza in istoric
    zi_data = articol.get('zi_data', {})
    _append_to_istoric({
        'data':       articol.get('data_generare', datetime.datetime.now().strftime('%Y-%m-%d')),
        'ora':        datetime.datetime.now().strftime('%H:%M'),
        'sfinti':     zi_data.get('saints', []),
        'apostol':    zi_data.get('apostle', {}).get('reference', ''),
        'evanghelie': zi_data.get('gospel', {}).get('reference', ''),
        'verset_ref': zi_data.get('selected_verse', {}).get('reference', ''),
        'verset_text': zi_data.get('selected_verse', {}).get('text', ''),
        'text_ales':  articol.get('fb_text', '')[:300],
        'status':     'generat',
        'surse':      zi_data.get('sources', {}),
    })

    if zi_data:
        preview = build_telegram_preview(zi_data, articol.get('titlu_wp', ''))
        keyboard = _get_inline_keyboard_cuvant()
    else:
        sfinti_link = ''
        if articol.get('sfinti_list'):
            sfinti_str = ', '.join(articol['sfinti_list'])
            sfinti_link = f'\n<b>Sfintii zilei:</b> <a href="https://doxologia.ro/calendar-ortodox">{sfinti_str}</a>'
        preview = (
            f"<b>ARTICOL GENERAT</b>\n"
            f"<b>{articol.get('titlu_wp','')}</b>"
            f"{sfinti_link}\n\n"
            f"<b>Preview Facebook:</b>\n"
            f"{str(articol.get('fb_text',''))[:500]}...\n\n"
            f"<b>Comenzi:</b>\n"
            f"/aproba — WP + Facebook\n"
            f"/aproba_fb — doar Facebook\n"
            f"/aproba_wp — doar WordPress\n"
            f"/adaug [text] — adaugă gând personal\n"
            f"/editeaza_fb — editează textul Facebook\n"
            f"/editeaza_wp — editează titlul și conținutul WP\n"
            f"/regenereaza — articol nou complet\n"
            f"/respinge — nu publica azi"
        )
        keyboard = None
    tg_send(preview, reply_markup=keyboard)

# ============================================================
#  GROQ API
# ============================================================
def call_claude(system, user, max_tokens=4000, img_b64=None, media_type='image/jpeg'):
    content = []
    if img_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{img_b64}"}
        })
    content.append({"type": "text", "text": user})

    model = "llama-3.2-90b-vision-preview" if img_b64 else "llama-3.3-70b-versatile"

    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": content}
        ]
    )
    return response.choices[0].message.content

def transcrie_audio_groq(audio_bytes, mime='audio/ogg'):
    """Transcrie audio cu Groq Whisper-large-v3, limbă română."""
    import tempfile, os as _os
    ext_map = {
        'audio/ogg': '.ogg', 'audio/oga': '.ogg',
        'audio/mp3': '.mp3', 'audio/mpeg': '.mp3',
        'audio/wav': '.wav', 'audio/m4a': '.m4a', 'audio/mp4': '.m4a',
    }
    ext = ext_map.get(mime, '.ogg')
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(audio_bytes)
            tmp = f.name
        with open(tmp, 'rb') as f:
            result = client.audio.transcriptions.create(
                model='whisper-large-v3',
                file=f,
                language='ro',
            )
        return result.text.strip()
    except Exception as e:
        print(f"Whisper error: {e}")
        return ''
    finally:
        if tmp:
            try: _os.unlink(tmp)
            except: pass

def parse_json_robust(text):
    def clean(s):
        # Inlocuieste newline-urile literale din interiorul string-urilor JSON
        result = []
        in_str = False
        i = 0
        while i < len(s):
            ch = s[i]
            # detecteaza ghilimele (deschidere/inchidere string), ignorand escaped \"
            if ch == '"':
                nb = 0
                j = i - 1
                while j >= 0 and s[j] == '\\':
                    nb += 1
                    j -= 1
                if nb % 2 == 0:
                    in_str = not in_str
            if in_str and ch == '\n':
                result.append(' ')
            elif in_str and ch == '\r':
                pass
            else:
                result.append(ch)
            i += 1
        return ''.join(result)

    def try_parse(s):
        try:
            return json.loads(s)
        except:
            try:
                return json.loads(clean(s))
            except:
                return None

    # 1. Incearca direct
    r = try_parse(text)
    if r is not None:
        return r

    # 2. Extrage din bloc ```json ... ```
    m = re.search(r'```(?:json)?\s*([\s\S]*?)(?:```|$)', text)
    if m:
        r = try_parse(m.group(1).strip())
        if r is not None:
            return r

    # 3. Extrage primul { ... } din text
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        r = try_parse(m.group(0))
        if r is not None:
            return r

    raise ValueError("JSON invalid: " + text[:200])

# ============================================================
#  SYSTEM PROMPT EDITORIAL
# ============================================================
SYSTEM = """Esti redactorul spiritual al Parohiei Cetate 2 Sibiu, Mitropolia Ardealului.

STILUL TAU - sinteza organica intre:
- Pr. Constantin Necula: caldura pastorala, umor fin, apropiere de om, referinte culturale vii
- Patriarhul Daniel: profunzime teologica, eleganta limbii romane, viziune misionara larga
- Alexandre Schmemann: teologia liturgica vie, sensul euharistic al creatiei, bucuria Invierii ca fundament

REGULI DE SCRIERE:
1. Fiecare articol are o MORALA clara, organica, integrata natural - nu impusa la sfarsit
2. Limbaj elevat dar cald si accesibil - ca o predica buna, nu un tratat academic
3. Citate patristice vii si concrete: Sf. Ioan Gura de Aur, Sf. Vasile cel Mare, Sf. Isaac Sirul, Sf. Siluan Athonitul, Sf. Paisie Aghioritul
4. Apostolul si Evanghelia zilei sunt punctul de plecare real, nu o formalitate
5. Diacritice corecte romanesti: a-virgula, i-virgula, s-virgula, t-virgula
6. Continut WP: 500-650 cuvinte - meditatie adevarata, aerisita, cu paragrafe scurte si spatii
7. Facebook: 220-280 cuvinte, ton cald-uman, cu verset si indemn la reflectie sau rugaciune
8. Structura AERISITA: paragrafe scurte (3-5 randuri), spatii intre sectiuni, nu ziduri de text
9. HTML elegant: foloseste <p> pentru fiecare paragraf, <blockquote> stilizat pentru citate
10. BIBLIA: Foloseste EXCLUSIV traducerea ortodoxa romana (Biblia sau Sfanta Scriptura, Editura Institutului Biblic, Bucuresti). Sursa de referinta: www.bibliortodoxa.ro. Cand citezi un verset, respecta exact textul din aceasta traducere.

Raspunzi EXCLUSIV cu JSON valid. Zero text in afara JSON. Zero markdown in afara JSON.
CRITIC: In valorile JSON, HTML-ul trebuie scris PE O SINGURA LINIE, fara newline-uri literale. Foloseste spatii intre taguri HTML, nu enter/newline."""

# ============================================================
#  GENERARE PRINCIPALA
# ============================================================
def genereaza_articol_zilnic(extra_text=''):
    global pending_articol
    dt      = get_azi()
    zi      = get_zi_romana(dt)
    tip     = get_tip_zi(dt)
    zi_spec = get_zi_speciala(dt)
    an_om   = get_an_omagial()

    # Preia calendarul ortodox complet de pe doxologia.ro
    zi_data = fetch_doxologia_calendar(dt)

    sfinti     = zi_data['saints']
    ap_ref     = zi_data['apostle']['reference']
    ev_ref     = zi_data['gospel']['reference']
    apostol    = ap_ref or zi_data['apostle']['text']
    evanghelie = ev_ref or zi_data['gospel']['text']

    # Fallback daca nu s-au gasit lecturi
    if not apostol or not evanghelie:
        pilda, solomon = scrape_pilde_solomon()
        apostol    = apostol or pilda
        evanghelie = evanghelie or solomon

    sfinti_str = ', '.join(sfinti) if sfinti else 'Sfintii zilei'
    autor_f, citat_f = get_citat_familie()
    s_extra   = f'\nGandul preotului (integreaza natural, nu fortat): {extra_text}' if extra_text else ''
    s_spec    = f'\nZi speciala de marcat discret: {zi_spec}' if zi_spec else ''
    s_an      = f'\nAnul omagial: {an_om} - integreaza un gand scurt despre familie.'
    s_familie = f'\nCitat despre familie pentru fb_text (integreaza natural la final): {autor_f}: "{citat_f}"'

    try:
        if tip == 'saptamana_mare':
            titlu_zi, tema_zi = get_nume_saptamana_mare(dt)
            data = _gen_saptamana_mare(zi, titlu_zi, tema_zi, apostol, evanghelie, s_extra)
            data['categorii'] = [CAT_PREDICA]
            data['video_bloc'] = get_video_resurse_saptamana_mare(titlu_zi)

        elif tip == 'sarbatoare':
            nume = get_nume_sarbatoare(dt)
            data = _gen_sarbatoare(zi, nume, apostol, evanghelie, s_extra, s_spec, s_an + s_familie)
            data['categorii'] = [CAT_PREDICA, CAT_POSTARI_NOI]
            data['imagine_query'] = nume.lower()

        elif tip == 'inceput_post':
            nume = get_nume_post(dt)
            data = _gen_inceput_post(zi, nume, apostol, evanghelie, s_extra, s_an + s_familie)
            data['categorii'] = [CAT_TRAIESTE]
            data['imagine_query'] = 'post'

        elif tip == 'duminica':
            nr = dt.isocalendar()[1]
            data = _gen_duminica(zi, sfinti_str, apostol, evanghelie,
                                  (nr % 3 == 0), s_extra, s_spec, s_an + s_familie)
            data['categorii'] = [CAT_PREDICA, CAT_TRAIESTE]

        elif tip in ['post', 'post_saptamana']:
            data = _gen_zi_post(zi, sfinti_str, apostol, evanghelie, s_extra + s_familie, s_spec, tip)
            data['categorii'] = [CAT_TRAIESTE]
            data['imagine_query'] = 'post'

        else:
            data = _gen_zi_obisnuita(zi, sfinti_str, apostol, evanghelie, s_extra, s_spec, s_an + s_familie)
            data['categorii'] = [CAT_TRAIESTE, CAT_POSTARI_NOI]

        # Metadata backward-compat
        data['sfinti_list'] = sfinti
        data['apostol']     = apostol
        data['evanghelie']  = evanghelie

        # Bloc sfinti + familie in continut WP
        data['continut_wp'] = _bloc_sfinti(sfinti) + data.get('continut_wp', '')
        data['continut_wp'] = data['continut_wp'] + get_bloc_familie()

        # Citat familie
        autor_f2, citat_f2 = get_citat_familie()
        data['citat_familie'] = f'"{citat_f2}" — {autor_f2}'

        # Imagine cu verificare si fallback local
        query = data.get('imagine_query', tip)
        _base = request.host_url.rstrip('/') if request else ''
        img_res = get_imagine_with_status(query + ' ' + tip, _base)
        data['imagine_url'] = img_res['url']
        if img_res['is_local']:
            data.setdefault('warnings', []).append('Imaginea externa nu s-a incarcat - se foloseste imaginea locala default')
        data['publica_wp']  = True

        # === Pipeline ZiData ===
        # 1. Verset verificat de pe bibliaortodoxa.ro (evanghelie > apostol)
        verse_ref = ev_ref or ap_ref
        if verse_ref:
            zi_data['selected_verse'] = fetch_biblia_ortodoxa_verse(verse_ref)

        # 2. Reflectie pastorala: varianta principala + 3 variante pentru Telegram
        zi_data['pastoral_variants'] = generate_pastoral_variants(zi_data)
        # Varianta principala = cea scurta (sau prima disponibila)
        zi_data['pastoral_reflection'] = (
            zi_data['pastoral_variants'].get('scurt')
            or zi_data['pastoral_variants'].get('duhovnicesc')
            or generate_pastoral_reflection(zi_data)
        )

        # 3. Validare
        zi_data = validate_post_data(zi_data)

        # 4. Construieste FB post structurat
        fb_text_nou = build_facebook_post(zi_data)
        if fb_text_nou:
            # Adauga citat familie la final
            data['fb_text'] = fb_text_nou + f'\n\n✦ {autor_f2}:\n„{citat_f2}"'
        # Altfel pastreaza fb_text generat de AI

        # 5. Salveaza zi_data si metadata in articol
        data['zi_data'] = zi_data
        data['data_generare'] = dt.strftime('%Y-%m-%d')

        trimite_spre_aprobare(data)
        return data

    except Exception as e:
        import traceback
        eroare = traceback.format_exc()
        print(f"EROARE GENERARE: {eroare}")
        tg_send(f"Eroare generare: {str(e)}\n{eroare[:200]}")
        return None

# ============================================================
#  GENERATOARE SPECIFICE
# ============================================================
WIDGET_DOXOLOGIA = """<div style="margin:24px 0;">
<table width="100%" class="doxo-table"><tr><td><div>
<script type="text/javascript">widgetContext_417c8830427f={"widgetid":"views_view_webwidget_765e55a9c50d100292071a1f227cd363"};</script>
<script src="https://doxologia.ro/doxowidgetcalendar"></script>
<div class="doxowidgetcalendar" id="views_view_webwidget_765e55a9c50d100292071a1f227cd363"></div>
</div></td></tr></table>
</div>"""

def _bloc_sfinti(sfinti_list):
    if not sfinti_list:
        return ''
    sfinti_str = ', '.join(sfinti_list)
    zi_str = get_zi_romana()
    return (
        f'<div style="background:linear-gradient(135deg,#fffdf0,#fffbea);border:1px solid #e8d5a0;'
        f'border-left:5px solid #c9a227;padding:20px 24px;margin:0 0 24px 0;border-radius:0 8px 8px 0;'
        f'box-shadow:0 2px 8px rgba(201,162,39,0.1);">'
        f'<p style="margin:0 0 4px 0;font-size:11px;text-transform:uppercase;letter-spacing:2px;'
        f'color:#c9a227;font-weight:700;font-family:Georgia,serif;">{zi_str}</p>'
        f'<p style="margin:0 0 6px 0;font-size:13px;text-transform:uppercase;letter-spacing:1px;'
        f'color:#8B6914;font-weight:600;">'
        f'<a href="https://doxologia.ro/calendar-ortodox" target="_blank" '
        f'style="color:#8B6914;text-decoration:none;">✦ Sfinții zilei ↗</a></p>'
        f'<p style="margin:0;color:#4a3300;line-height:1.9;font-style:italic;font-size:15px;'
        f'font-family:Georgia,serif;">{sfinti_str}</p>'
        f'</div>'
    )

def _bloc_lecturi(apostol, evanghelie):
    if not apostol and not evanghelie:
        return ''
    url_cal = 'https://doxologia.ro/calendar-ortodox'
    bloc = (
        f'<div style="background:linear-gradient(135deg,#fdf5f5,#fdf8f8);border:1px solid #dcc0c0;'
        f'border-left:5px solid #8B0000;padding:20px 24px;margin:0 0 24px 0;border-radius:0 8px 8px 0;'
        f'box-shadow:0 2px 8px rgba(139,0,0,0.08);">'
    )
    if apostol:
        bloc += (
            f'<p style="margin:0 0 4px 0;font-size:11px;text-transform:uppercase;letter-spacing:2px;'
            f'color:#8B0000;font-weight:700;">'
            f'<a href="{url_cal}" target="_blank" style="color:#8B0000;text-decoration:none;">✦ Apostolul zilei ↗</a></p>'
            f'<p style="margin:0 0 18px 0;font-style:italic;color:#2c0000;line-height:1.9;font-size:15px;'
            f'font-family:Georgia,serif;padding-left:12px;border-left:2px solid #c9a0a0;">{apostol}</p>'
        )
    if evanghelie:
        bloc += (
            f'<p style="margin:0 0 4px 0;font-size:11px;text-transform:uppercase;letter-spacing:2px;'
            f'color:#8B0000;font-weight:700;">'
            f'<a href="{url_cal}" target="_blank" style="color:#8B0000;text-decoration:none;">✦ Evanghelia zilei ↗</a></p>'
            f'<p style="margin:0;font-style:italic;color:#2c0000;line-height:1.9;font-size:15px;'
            f'font-family:Georgia,serif;padding-left:12px;border-left:2px solid #c9a0a0;">{evanghelie}</p>'
        )
    bloc += '</div>'
    return bloc

def _gen_zi_obisnuita(zi, sfinti, apostol, evanghelie, s_extra, s_spec, s_an):
    u = f"""Astazi este {zi}. Sfintii zilei: {sfinti}.
Apostolul zilei: {apostol}.
Evanghelia zilei: {evanghelie}.{s_spec}{s_an}{s_extra}

Genereaza articolul zilnic pentru Parohia Cetate 2 Sibiu.
Structura HTML AERISITA cu paragrafe scurte si spatii generoase.

JSON:
{{
  "titlu_wp": "titlu evocator, poetic, nu banal - 6-10 cuvinte",
  "continut_wp": "HTML complet aerisit: <h2 style='color:#8B0000;font-family:Georgia,serif;'>Sfintii zilei</h2> <p>descriere vie a fiecarui sfant, legatura cu viata de azi</p> <h2 style='color:#8B0000;font-family:Georgia,serif;'>Meditatie duhovniceasca</h2> <p>paragraf 1 - deschide cu o intrebare sau imagine poetica</p> <p>paragraf 2 - dezvoltare teologica accesibila cu referinta patristica concreta</p> <p>paragraf 3 - aplicatie pastorala calda</p> <h3 style='color:#8B0000;'>Morala zilei</h3> <p>un paragraf scurt, memorabil, practic</p>",
  "fb_text": "220-260 cuvinte: incepe cu un verset scurt exact din Apostol sau Evanghelie (din Biblia Ortodoxa Romana) pus intre ghilimele cu referinta (ex: Ioan 3,16) + mentionezi explicit sfintii zilei ({sfinti}) + meditatie calda 3-4 randuri stil Pr. Necula + intrebare sau indemn concret + la final adauga citatul despre familie din context (pe rand nou, italic, cu liniuta si autor) + #ParohiaCetate2Sibiu #EvanghelliaZilei #SfintiiZilei #FamiliaCrestina #Ortodox #Sibiu"
}}"""
    d = parse_json_robust(call_claude(SYSTEM, u, 4500))
    # Inserez blocul lecturilor la inceput
    d['continut_wp'] = _bloc_lecturi(apostol, evanghelie) + d.get('continut_wp','')
    return d


def _gen_duminica(zi, sfinti, apostol, evanghelie, ips, s_extra, s_spec, s_an):
    ips_html = '+ <h2 style="color:#8B0000;">Cuvant arhieresc</h2> <p>citat inspirat si autentic din predicile IPS Laurentiu Streza al Ardealului, cu referinta la mitropolia-ardealului.ro</p>' if ips else ''
    u = f"""Astazi este {zi}, Duminica. Sfintii zilei: {sfinti}.
Apostolul Duminicii: {apostol}.
Evanghelia Duminicii: {evanghelie}.{s_spec}{s_an}{s_extra}

Genereaza articolul duminical pentru Parohia Cetate 2 Sibiu.
JSON:
{{
  "titlu_wp": "titlu duminical profund si evocator - 6-10 cuvinte",
  "continut_wp": "HTML aerisit: <h2 style='color:#8B0000;font-family:Georgia,serif;'>Sfintii Duminicii</h2> <p>descriere</p> <h2 style='color:#8B0000;font-family:Georgia,serif;'>Predica Duminicii</h2> <p>deschide cu o intrebare existentiala</p> <p>dezvoltare teologica 2-3 paragrafe cu referinte patristice</p> <p>aplicatie pastorala calda</p> {ips_html} <h3 style='color:#8B0000;'>Morala Duminicii</h3> <p>concluzie practica si indemn pentru saptamana</p>",
  "fb_text": "250-280 cuvinte: verset exact din Evanghelia duminicii (din Biblia Ortodoxa Romana) pus intre ghilimele cu referinta + sfintii duminicii ({sfinti}) + meditatie duminicala calda 3-4 randuri + urare calduroasa + la final citatul despre familie din context (pe rand nou, italic, cu liniuta si autor) + #DuminicaOrtodoxa #FamiliaCrestina #ParohiaCetate2Sibiu #Evanghelie #Sibiu"
}}"""
    d = parse_json_robust(call_claude(SYSTEM, u, 5500))
    d['continut_wp'] = _bloc_lecturi(apostol, evanghelie) + d.get('continut_wp','')
    return d


def _gen_sarbatoare(zi, nume, apostol, evanghelie, s_extra, s_spec, s_an):
    u = f"""Astazi este {zi} - {nume}.
Apostolul sarbatorii: {apostol}.
Evanghelia sarbatorii: {evanghelie}.{s_spec}{s_an}{s_extra}

Genereaza articolul de sarbatoare pentru Parohia Cetate 2 Sibiu.
Stilul: urare calda ca Patriarhul Daniel + profunzime ca Schmemann + bucurie ca Pr. Necula.
JSON:
{{
  "titlu_wp": "titlu festiv si evocator",
  "continut_wp": "HTML festiv aerisit: <h2 style='color:#8B0000;font-family:Georgia,serif;'>{nume}</h2> <p>semnificatia sarbatorii in 1-2 paragrafe</p> <blockquote style='border-left:4px solid #8B0000;padding:12px 16px;margin:16px 0;background:#fdf8f3;font-style:italic;'>Troparul sarbatorii</blockquote> <blockquote style='border-left:4px solid #c9a227;padding:12px 16px;margin:16px 0;background:#fffdf5;font-style:italic;'>Condacul</blockquote> <h2 style='color:#8B0000;font-family:Georgia,serif;'>Meditatie</h2> <p>2-3 paragrafe despre taina sarbatorii cu referinte patristice</p> <h3 style='color:#8B0000;'>Morala sarbatorii</h3> <p>urare calda pentru credinciosi</p>",
  "fb_text": "220-260 cuvinte: urare calda de sarbatoare + verset exact din Evanghelia sarbatorii (din Biblia Ortodoxa Romana) intre ghilimele cu referinta + Tropar scurt + meditatie 2-3 randuri + indemn la slujba + emoji potrivite + #ParohiaCetate2Sibiu #{nume.replace(' ','')} #Ortodox #Sibiu"
}}"""
    d = parse_json_robust(call_claude(SYSTEM, u, 5000))
    d['continut_wp'] = _bloc_lecturi(apostol, evanghelie) + d.get('continut_wp','')
    return d


def _gen_inceput_post(zi, nume, apostol, evanghelie, s_extra, s_an):
    u = f"""Astazi este {zi} - incepe {nume}.
Apostolul zilei: {apostol}.
Evanghelia zilei: {evanghelie}.{s_an}{s_extra}

Genereaza articolul de inceput de post pentru Parohia Cetate 2 Sibiu.
JSON:
{{
  "titlu_wp": "titlu poetic despre inceperea postului",
  "continut_wp": "HTML aerisit: <h2 style='color:#8B0000;font-family:Georgia,serif;'>Incepe {nume}</h2> <p>semnificatia duhovniceasca in 1-2 paragrafe</p> <h2 style='color:#8B0000;'>Postul - scoala a sufletului</h2> <p>paragraf 1 - citat din Sf. Ioan Gura de Aur despre post</p> <p>paragraf 2 - citat din Sf. Vasile sau Sf. Isaac Sirul</p> <p>paragraf 3 - sfaturi practice duhovnicesti</p> <h3 style='color:#8B0000;'>Morala</h3> <p>binecuvantare pentru post</p>",
  "fb_text": "200-240 cuvinte: caldura pastorala + citat patristic despre post + indemn concret + Post cu folos! + hashtag-uri #Post{nume.replace(' ','')} #ParohiaCetate2Sibiu #Ortodox"
}}"""
    d = parse_json_robust(call_claude(SYSTEM, u, 4500))
    d['continut_wp'] = _bloc_lecturi(apostol, evanghelie) + d.get('continut_wp','')
    return d


def _gen_zi_post(zi, sfinti, apostol, evanghelie, s_extra, s_spec, tip):
    ton = "Miercuri sau Vineri de post - zi de infranare si rugaciune sporita" if tip == 'post' else "zi de post in Postul Mare"
    u = f"""Astazi este {zi} - {ton}. Sfintii zilei: {sfinti}.
Apostolul zilei: {apostol}.
Evanghelia zilei: {evanghelie}.{s_spec}{s_extra}

Genereaza meditatie pentru zi de post, Parohia Cetate 2 Sibiu.
JSON:
{{
  "titlu_wp": "titlu poetic pentru zi de post",
  "continut_wp": "HTML aerisit: <h2 style='color:#8B0000;font-family:Georgia,serif;'>Sfintii zilei</h2> <p>descriere scurta</p> <h2 style='color:#8B0000;font-family:Georgia,serif;'>Postul ca rugaciune a trupului</h2> <p>paragraf 1 - sensul postului dincolo de abtinere</p> <p>paragraf 2 - intalnirea cu Dumnezeu prin post, citat patristic</p> <p>paragraf 3 - aplicatie practica pentru ziua de azi</p> <h3 style='color:#8B0000;'>Morala zilei</h3> <p>un indemn scurt si memorabil</p>",
  "fb_text": "180-220 cuvinte: verset exact din Apostol sau Evanghelie (din Biblia Ortodoxa Romana) intre ghilimele + sfintii zilei ({sfinti}) + citat patristic scurt despre post + indemn concret pentru zi de post + la final citatul despre familie din context (pe rand nou, italic) + #ZiDePost #FamiliaCrestina #ParohiaCetate2Sibiu #Ortodox"
}}"""
    d = parse_json_robust(call_claude(SYSTEM, u, 4000))
    d['continut_wp'] = _bloc_lecturi(apostol, evanghelie) + d.get('continut_wp','')
    return d


def _gen_saptamana_mare(zi, titlu_zi, tema_zi, apostol, evanghelie, s_extra):
    u = f"""Astazi este {zi} - {titlu_zi}. Tema: {tema_zi}.
Apostolul zilei: {apostol}.
Evanghelia zilei: {evanghelie}.{s_extra}

Genereaza articolul pentru Saptamana Patimilor, Parohia Cetate 2 Sibiu.
Ton: solemn, profund, cu nadejdea Invierii stralucind prin Patimi - ca la Schmemann.
JSON:
{{
  "titlu_wp": "{titlu_zi} - titlu solemn si evocator",
  "continut_wp": "HTML solemn aerisit: <h2 style='color:#8B0000;font-family:Georgia,serif;'>{titlu_zi}</h2> <p>contextul biblic al zilei in 1-2 paragrafe</p> <h2 style='color:#8B0000;font-family:Georgia,serif;'>Semnificatia liturgica</h2> <p>explicarea slujbei zilei cu referinte la Triod</p> <h2 style='color:#8B0000;font-family:Georgia,serif;'>Meditatie</h2> <p>2-3 paragrafe in spiritul Triodului, cu referinte patristice, cu nadejdea Invierii</p> <h3 style='color:#8B0000;'>Morala</h3> <p>rugaciune scurta de incheiere sau indemn solemn</p>",
  "fb_text": "200-240 cuvinte: solemn cu nadejde + Apostol + Evanghelie + taina zilei + emoji ✝ + #SaptamanaMare #{titlu_zi.replace(' ','')} #ParohiaCetate2Sibiu"
}}"""
    d = parse_json_robust(call_claude(SYSTEM, u, 5000))
    d['continut_wp'] = _bloc_lecturi(apostol, evanghelie) + d.get('continut_wp','')
    return d


def _gen_din_poza(img_b64, caption=''):
    zi = get_zi_romana()
    _zd = fetch_doxologia_calendar(get_azi())
    apostol    = _zd['apostle']['reference'] or _zd['apostle']['text']
    evanghelie = _zd['gospel']['reference']  or _zd['gospel']['text']
    if not apostol:
        apostol, evanghelie = scrape_pilde_solomon()
    s_cap = f"Textul preotului (integreaza natural): {caption}" if caption else ''
    u = f"""Astazi este {zi}. {s_cap}
Apostolul zilei: {apostol or ''}.
Evanghelia zilei: {evanghelie or ''}.

Preotul a trimis aceasta imagine. Genereaza articol inspirat din imagine si lecturile zilei.
JSON:
{{
  "titlu_wp": "titlu bazat pe evenimentul fotografiat",
  "continut_wp": "HTML 380-450 cuvinte aerisit: descrie evenimentul/momentul in 1-2 paragrafe + leaga de lecturile zilei + meditatie pastorala 2 paragrafe + <h3 style='color:#8B0000;'>Morala</h3>",
  "fb_text": "200-240 cuvinte: calda, invitanta, context spiritual + hashtag-uri #ParohiaCetate2Sibiu #ViataParohiei #Sibiu"
}}"""
    d = parse_json_robust(call_claude(SYSTEM, u, 3500, img_b64=img_b64))
    d['continut_wp'] = _bloc_lecturi(apostol, evanghelie) + d.get('continut_wp','')
    return d


def _gen_din_text(text):
    zi = get_zi_romana()
    _zd = fetch_doxologia_calendar(get_azi())
    apostol    = _zd['apostle']['reference'] or _zd['apostle']['text']
    evanghelie = _zd['gospel']['reference']  or _zd['gospel']['text']
    if not apostol:
        apostol, evanghelie = scrape_pilde_solomon()
    u = f"""Astazi este {zi}.
Apostolul zilei: {apostol or ''}.
Evanghelia zilei: {evanghelie or ''}.
Preotul a trimis: "{text}"

Transforma in articol complet, integrand lecturile zilei.
JSON:
{{
  "titlu_wp": "titlu articol inspirat din mesajul preotului",
  "continut_wp": "HTML 360-420 cuvinte aerisit: mesajul preotului + Apostol + Evanghelie + context spiritual + <h3 style='color:#8B0000;'>Morala</h3>",
  "fb_text": "190-230 cuvinte + emoji + #ParohiaCetate2Sibiu #Sibiu"
}}"""
    d = parse_json_robust(call_claude(SYSTEM, u, 3500))
    d['continut_wp'] = _bloc_lecturi(apostol, evanghelie) + d.get('continut_wp','')
    return d


def _gen_din_audio(transcriptie, caption=''):
    zi = get_zi_romana()
    _zd = fetch_doxologia_calendar(get_azi())
    apostol    = _zd['apostle']['reference'] or _zd['apostle']['text']
    evanghelie = _zd['gospel']['reference']  or _zd['gospel']['text']
    if not apostol:
        apostol, evanghelie = scrape_pilde_solomon()
    s_cap = f"Text suplimentar: {caption}" if caption else ''
    u = f"""Astazi este {zi}.
Apostolul zilei: {apostol or ''}.
Evanghelia zilei: {evanghelie or ''}.
Preotul a trimis mesaj audio (tema/transcriptie): "{transcriptie}"
{s_cap}

Transforma in articol complet.
JSON:
{{
  "titlu_wp": "titlu inspirat din mesajul audio",
  "continut_wp": "HTML 360-420 cuvinte aerisit: integreaza natural mesajul cu lecturile zilei + <h3 style='color:#8B0000;'>Morala</h3>",
  "fb_text": "190-230 cuvinte + #ParohiaCetate2Sibiu #Sibiu"
}}"""
    d = parse_json_robust(call_claude(SYSTEM, u, 3500))
    d['continut_wp'] = _bloc_lecturi(apostol, evanghelie) + d.get('continut_wp','')
    return d

# ============================================================
#  WEBHOOK TELEGRAM
# ============================================================
@app.route('/webhook', methods=['POST'])
def webhook():
    global pending_articol, edit_mode
    update = request.json
    if not update:
        return jsonify({'ok': True})

    # Callback inline keyboard
    cb = update.get('callback_query', {})
    if cb:
        cb_chat = str(cb.get('message', {}).get('chat', {}).get('id', ''))
        cb_data = cb.get('data', '')
        cb_id   = cb.get('id', '')
        if cb_chat == TG_CHAT_ID and cb_data == 'regen_cuvant':
            tg_answer_callback(cb_id, 'Regenerez...')
            def _regen_cuvant_bg():
                art = pending_articol
                zi = art.get('zi_data')
                if not zi:
                    tg_send("Nu exista articol in asteptare pentru regenerare.")
                    return
                variants = generate_pastoral_variants(zi)
                zi['pastoral_variants'] = variants
                zi['pastoral_reflection'] = (
                    variants.get('scurt') or variants.get('duhovnicesc') or ''
                )
                art['zi_data'] = zi
                pending_articol.update({'zi_data': zi})
                _save_pending(pending_articol)
                lines = ['<b>🔁 Cuvânt de folos — variante noi:</b>']
                labels = {'scurt': '1️⃣ Scurt și cald', 'duhovnicesc': '2️⃣ Duhovnicesc', 'catehetic': '3️⃣ Catehetic'}
                for key, label in labels.items():
                    txt = variants.get(key, '')
                    if txt:
                        lines.append(f'\n<b>{label}:</b>\n{txt}')
                tg_send('\n'.join(lines), reply_markup=_get_inline_keyboard_cuvant())
            threading.Thread(target=_regen_cuvant_bg, daemon=True).start()
        return jsonify({'ok': True})

    msg     = update.get('message', {})
    chat_id = str(msg.get('chat', {}).get('id', ''))

    if chat_id != TG_CHAT_ID:
        return jsonify({'ok': True})

    text    = msg.get('text', '')
    photo   = msg.get('photo')
    audio   = msg.get('audio') or msg.get('voice')
    caption = msg.get('caption', '')

    if text == '/aproba':
        if not pending_articol:
            tg_send("Nu exista articol in asteptare.")
            return jsonify({'ok': True})
        art = pending_articol
        art_date = art.get('data_generare', datetime.datetime.now().strftime('%Y-%m-%d'))
        try:
            media_id = None
            img_warn = ''

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
                    else:
                        img_warn = f'⚠ Imaginea ({art["imagine_url"][:60]}...) nu s-a incarcat. Postez fara imagine.'
                except:
                    img_warn = '⚠ Imaginea nu a putut fi descarcata. Postez fara imagine.'

            # Audio
            bloc_audio = ''
            if art.get('audio_bytes'):
                try:
                    _, aurl = upload_media(art['audio_bytes'], 'mesaj.ogg', 'audio/ogg')
                    if aurl:
                        bloc_audio = (
                            f'<div style="margin:20px 0;padding:16px;background:#f5f5f5;border-radius:8px;">'
                            f'<p style="margin:0 0 8px 0;font-size:13px;color:#666;">Mesaj audio:</p>'
                            f'<audio controls style="width:100%">'
                            f'<source src="{aurl}" type="audio/ogg"></audio></div>'
                        )
                except:
                    pass

            video_bloc = art.get('video_bloc', '')
            continut = (bloc_audio or '') + art.get('continut_wp', '') + (video_bloc or '')
            cat = art.get('categorii', [CAT_TRAIESTE])

            post_id, link = publica_articol(art['titlu_wp'], continut, cat, media_id)

            if link:
                _update_istoric_status(art_date, 'publicat_wp')
                fb_text = art.get('fb_text', '')
                # Verifica verset: Facebook blocat daca versetul nu e verificat
                verse_ok = art.get('zi_data', {}).get('selected_verse', {}).get('verified', True)
                if not verse_ok:
                    tg_send(
                        f"✓ Publicat pe WordPress!\n{link}\n\n"
                        f"⛔ Facebook BLOCAT — versetul biblic nu a fost verificat pe bibliaortodoxa.ro.\n"
                        f"Verificați manual sau folosiți /aproba_fb după corectare."
                        + (f'\n{img_warn}' if img_warn else '')
                    )
                else:
                    fb_id, fb_err = publica_facebook(fb_text, link)
                    if fb_id:
                        _update_istoric_status(art_date, 'publicat')
                        tg_send(
                            f"✓ Publicat pe WordPress!\n{link}\n\n"
                            f"✓ Publicat pe Facebook!"
                            + (f'\n{img_warn}' if img_warn else '')
                        )
                    elif FB_PAGE_TOKEN and FB_PAGE_ID:
                        tg_send(
                            f"✓ Publicat pe WordPress!\n{link}\n\n"
                            f"⚠ Facebook eroare: {fb_err}"
                            + (f'\n{img_warn}' if img_warn else '')
                        )
                    else:
                        tg_send(
                            f"✓ Publicat pe WordPress!\n{link}\n\n"
                            f"(Facebook: seteaza FB_PAGE_TOKEN si FB_PAGE_ID pe Render)"
                        )
            else:
                tg_send("Eroare la publicarea pe WordPress.")
            pending_articol = {}
            _clear_pending()

        except Exception as e:
            tg_send(f"Eroare la publicare: {str(e)}")

    elif text == '/aproba_fb':
        if not pending_articol:
            tg_send("Nu exista articol in asteptare.")
        else:
            art = pending_articol
            art_date = art.get('data_generare', datetime.datetime.now().strftime('%Y-%m-%d'))
            # Verifica verset
            verse_ok = art.get('zi_data', {}).get('selected_verse', {}).get('verified', True)
            if not verse_ok:
                tg_send(
                    "⛔ Facebook BLOCAT — versetul biblic nu a fost verificat pe bibliaortodoxa.ro.\n"
                    "Verificați manual referința sau folosiți /respinge."
                )
                return jsonify({'ok': True})
            fb_text = art.get('fb_text', '')
            img_bytes = art.get('img_bytes')
            img_url = art.get('imagine_url') if not img_bytes else None
            fb_id, fb_err = publica_facebook(fb_text, img_bytes=img_bytes, img_url=img_url)
            if fb_id:
                _update_istoric_status(art_date, 'publicat_fb')
                msg_ok = "✓ Publicat pe Facebook!"
                if img_url and not img_bytes:
                    img_ok, _ = _verify_image_url(img_url)
                    if not img_ok:
                        msg_ok += "\n⚠ Imaginea nu s-a incarcat — postare publicata fara imagine."
                tg_send(msg_ok)
            else:
                tg_send(f"⚠ Facebook eroare: {fb_err}")
            pending_articol = {}
            _clear_pending()

    elif text == '/aproba_wp':
        if not pending_articol:
            tg_send("Nu exista articol in asteptare.")
        else:
            art = pending_articol
            art_date = art.get('data_generare', datetime.datetime.now().strftime('%Y-%m-%d'))
            try:
                media_id = None
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
                continut = art.get('continut_wp', '') + art.get('video_bloc', '')
                post_id, link = publica_articol(art['titlu_wp'], continut, art.get('categorii', [CAT_TRAIESTE]), media_id)
                if link:
                    _update_istoric_status(art_date, 'publicat_wp')
                    tg_send(f"✓ Publicat doar pe WordPress!\n{link}")
                else:
                    tg_send("Eroare - verificati WordPress.")
            except Exception as e:
                tg_send(f"Eroare: {str(e)}")
            pending_articol = {}
            _clear_pending()

    elif text.startswith('/adaug '):
        extra = text[7:].strip()
        tg_send("Regenerez cu gandul tau... (30-60 sec)")
        def _trigger_adaug():
            try:
                requests.get(f"https://bot-parohie.onrender.com/genereaza?extra={requests.utils.quote(extra)}", timeout=280)
            except:
                pass
        threading.Thread(target=_trigger_adaug, daemon=True).start()

    elif text == '/regenereaza_cuvant':
        if not pending_articol:
            tg_send("Nu exista articol in asteptare.")
        else:
            tg_send("Regenerez variantele cuvântului de folos... (20-40 sec)")
            def _regen_cuvant_cmd():
                art = pending_articol
                zi = art.get('zi_data')
                if not zi:
                    tg_send("Articolul nu are zi_data — foloseste /regenereaza pentru articol nou complet.")
                    return
                variants = generate_pastoral_variants(zi)
                zi['pastoral_variants'] = variants
                zi['pastoral_reflection'] = variants.get('scurt') or variants.get('duhovnicesc') or ''
                pending_articol['zi_data'] = zi
                _save_pending(pending_articol)
                lines = ['<b>🔁 Cuvânt de folos — variante noi:</b>']
                labels = {'scurt': '1️⃣ Scurt și cald', 'duhovnicesc': '2️⃣ Duhovnicesc', 'catehetic': '3️⃣ Catehetic'}
                for key, label in labels.items():
                    txt = variants.get(key, '')
                    if txt:
                        lines.append(f'\n<b>{label}:</b>\n{txt}')
                tg_send('\n'.join(lines), reply_markup=_get_inline_keyboard_cuvant())
            threading.Thread(target=_regen_cuvant_cmd, daemon=True).start()

    elif text == '/regenereaza':
        tg_send("Generez articol nou...")
        def _trigger_regen():
            try:
                requests.get("https://bot-parohie.onrender.com/genereaza", timeout=280)
            except:
                pass
        threading.Thread(target=_trigger_regen, daemon=True).start()

    elif text == '/editeaza_fb':
        if not pending_articol:
            tg_send("Nu exista articol in asteptare.")
        else:
            edit_mode = 'fb'
            tg_send(
                f"<b>Text Facebook curent:</b>\n\n"
                f"{pending_articol.get('fb_text','')}\n\n"
                f"Trimite acum textul nou pentru Facebook."
            )

    elif text == '/editeaza_wp':
        if not pending_articol:
            tg_send("Nu exista articol in asteptare.")
        else:
            edit_mode = 'wp'
            continut_text = re.sub(r'<[^>]+>', '', pending_articol.get('continut_wp', ''))
            continut_text = re.sub(r'\s+', ' ', continut_text).strip()
            tg_send(
                f"<b>Titlu curent:</b> {pending_articol.get('titlu_wp','')}\n\n"
                f"<b>Continut curent (fara HTML):</b>\n{continut_text[:800]}...\n\n"
                f"Trimite acum:\n<code>TITLU: titlul nou\nCONTINUT: textul nou</code>\n\n"
                f"Sau doar <code>TITLU: titlul nou</code> pentru a schimba doar titlul."
            )

    elif text == '/respinge':
        art_date = pending_articol.get('data_generare', datetime.datetime.now().strftime('%Y-%m-%d'))
        _update_istoric_status(art_date, 'respins')
        pending_articol = {}
        _clear_pending()
        tg_send("Articolul a fost respins.")

    elif text in ['/start', '/help']:
        tg_send(
            "<b>Bot Parohia Cetate 2 Sibiu</b>\n\n"
            "<b>Comenzi:</b>\n"
            "/genereaza - articolul zilei\n"
            "/aproba - publica pe WP + Facebook\n"
            "/aproba_fb - publica doar pe Facebook\n"
            "/aproba_wp - publica doar pe WordPress\n"
            "/adaug [text] - adauga gand personal\n"
            "/regenereaza - alt articol\n"
            "/respinge - nu publica azi\n\n"
            "<b>Trimiteti direct:</b>\n"
            "Fotografie - articol foto\n"
            "Mesaj vocal/audio - articol audio\n"
            "Text liber - articol din textul tau"
        )

    elif text == '/genereaza':
        tg_send("Generez articolul zilei... (30-60 secunde)")
        def _trigger_gen():
            try:
                requests.get("https://bot-parohie.onrender.com/genereaza", timeout=280)
            except:
                pass
        threading.Thread(target=_trigger_gen, daemon=True).start()

    elif text == '/an_omagial':
        tg_send(f"Anul omagial: {get_an_omagial()}")

    elif photo:
        # Daca exista articol in asteptare, actualizeaza doar poza
        if pending_articol:
            def schimba_poza():
                try:
                    fb = tg_get_file(photo[-1]['file_id'])
                    if fb:
                        pending_articol['img_bytes'] = fb
                        pending_articol.pop('imagine_url', None)
                        tg_send("✓ Poza actualizata!\n\n/aproba - WP + Facebook\n/aproba_fb - doar Facebook\n/aproba_wp - doar WordPress")
                    else:
                        tg_send("Nu am putut descarca poza.")
                except Exception as e:
                    tg_send(f"Eroare poza: {str(e)}")
            threading.Thread(target=schimba_poza).start()
        else:
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
        tg_send("Am primit mesajul audio. Transcriu cu Whisper... (30-60 sec)")
        def proc_audio():
            try:
                ab = tg_get_file(audio.get('file_id'))
                if not ab:
                    tg_send("Nu am putut descarca audio.")
                    return
                # Transcriere reala cu Groq Whisper
                mime = audio.get('mime_type', 'audio/ogg')
                transcriptie = transcrie_audio_groq(ab, mime)
                if transcriptie:
                    tg_send(f"Transcriptie: {transcriptie[:300]}")
                else:
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
        if edit_mode == 'fb' and pending_articol:
            pending_articol['fb_text'] = text
            edit_mode = None
            tg_send("✓ Text Facebook actualizat!\n\n/aproba - publica acum\n/respinge - nu publica azi")
        elif edit_mode == 'wp' and pending_articol:
            titlu_nou = re.search(r'TITLU:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
            continut_nou = re.search(r'CONTINUT:\s*([\s\S]+)', text, re.IGNORECASE)
            if titlu_nou:
                pending_articol['titlu_wp'] = titlu_nou.group(1).strip()
            if continut_nou:
                paragraphs = continut_nou.group(1).strip().split('\n')
                pending_articol['continut_wp'] = ''.join(f'<p>{p.strip()}</p>' for p in paragraphs if p.strip())
            edit_mode = None
            tg_send("✓ Articol WordPress actualizat!\n\n/aproba - publica acum\n/respinge - nu publica azi")
        else:
            tg_send("Am primit mesajul. Generez... (20-30 sec)")
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
#  ENDPOINT-URI HTTP
# ============================================================
@app.route('/')
def home():
    return f"Bot Parohia Cetate 2 Sibiu - activ {get_azi().strftime('%d.%m.%Y %H:%M')}"

@app.route('/genereaza')
def ep_genereaza():
    from flask import request as freq
    extra = freq.args.get('extra', '')
    try:
        genereaza_articol_zilnic(extra)
        return jsonify({'status': 'gata', 'ora': get_azi().strftime('%H:%M')})
    except Exception as e:
        return jsonify({'status': 'eroare', 'eroare': str(e)})

@app.route('/preview_fb')
def ep_preview_fb():
    art = _load_pending()
    if not art:
        return "Nu exista articol in asteptare.", 200
    fb    = art.get('fb_text', '')
    titlu = art.get('titlu_wp', '')
    img   = art.get('imagine_url', '')
    sfinti = ', '.join(art.get('sfinti_list', [])) or '—'
    zi_data = art.get('zi_data', {})
    apostol    = zi_data.get('apostle', {}).get('reference', '') or art.get('apostol', '—')
    evanghelie = zi_data.get('gospel',  {}).get('reference', '') or art.get('evanghelie', '—')
    v_ref  = zi_data.get('selected_verse', {}).get('reference', '')
    v_ok   = zi_data.get('selected_verse', {}).get('verified', False)
    v_url  = zi_data.get('selected_verse', {}).get('source_url', '')
    warnings = zi_data.get('warnings', [])

    img_html = (
        f'<img src="{img}" referrerpolicy="no-referrer" crossorigin="anonymous" '
        f'style="width:100%;border-radius:8px;margin-bottom:16px;'
        f'object-fit:cover;max-height:340px;" alt="Imagine articol" />'
        if img else ''
    )
    warn_html = ''
    if warnings:
        items = ''.join(f'<li style="margin:4px 0;">{w}</li>' for w in warnings)
        warn_html = (
            f'<div style="background:#fff3cd;border:1px solid #ffc107;padding:12px 16px;'
            f'margin:0 0 16px;border-radius:6px;">'
            f'<p style="margin:0 0 6px;font-weight:bold;color:#856404;font-size:13px;">⚠ Avertismente:</p>'
            f'<ul style="margin:0;padding-left:18px;font-size:13px;color:#664d03;">{items}</ul></div>'
        )
    v_html = ''
    if v_ref:
        icon = '✓' if v_ok else '⚠'
        color = '#2e7d32' if v_ok else '#e65100'
        v_link = f'<a href="{v_url}" style="color:{color};">{v_ref}</a>' if v_url else v_ref
        v_html = (
            f'<p style="margin:0 0 4px;font-size:11px;color:#999;text-transform:uppercase;letter-spacing:1px;">Verset verificat ({icon})</p>'
            f'<p style="margin:0 0 16px;font-size:13px;color:{color};">{v_link}</p>'
        )
    return f"""<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="font-family:Georgia,serif;max-width:620px;margin:40px auto;padding:20px;background:#fdf8f3;">
<div style="background:#fff;border-radius:12px;padding:24px;box-shadow:0 2px 12px rgba(0,0,0,.08);">
  {img_html}
  {warn_html}
  <p style="margin:0 0 4px;font-size:11px;color:#999;text-transform:uppercase;letter-spacing:1px;">Titlu WordPress</p>
  <p style="margin:0 0 16px;font-size:18px;font-weight:bold;color:#8B0000;">{titlu}</p>
  <p style="margin:0 0 4px;font-size:11px;color:#999;text-transform:uppercase;letter-spacing:1px;">Sfinții zilei</p>
  <p style="margin:0 0 16px;font-size:13px;font-style:italic;color:#555;">{sfinti}</p>
  <p style="margin:0 0 4px;font-size:11px;color:#999;text-transform:uppercase;letter-spacing:1px;">Apostolul</p>
  <p style="margin:0 0 16px;font-size:13px;color:#333;">{apostol[:200]}</p>
  <p style="margin:0 0 4px;font-size:11px;color:#999;text-transform:uppercase;letter-spacing:1px;">Evanghelia</p>
  <p style="margin:0 0 16px;font-size:13px;color:#333;">{evanghelie[:200]}</p>
  {v_html}
  <hr style="border:none;border-top:2px solid #8B0000;margin:0 0 20px;">
  <p style="margin:0 0 4px;font-size:11px;color:#999;text-transform:uppercase;letter-spacing:1px;">Text Facebook</p>
  <p style="margin:0;white-space:pre-wrap;font-size:15px;line-height:1.9;color:#1a1a1a;">{fb}</p>
  <p style="margin:20px 0 0;font-size:11px;color:#aaa;border-top:1px solid #eee;padding-top:10px;">
    Surse: <a href="https://doxologia.ro/calendar-ortodox" style="color:#8B0000;">Doxologia.ro</a> &nbsp;|&nbsp;
    <a href="https://www.bibliaortodoxa.ro" style="color:#8B0000;">Biblia Ortodoxă</a>
  </p>
</div>
</body></html>"""

@app.route('/citat')
@app.route('/sfinti')
@app.route('/mitropolit')
@app.route('/evanghelia')
def ep_alias():
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

@app.route('/test')
def ep_test():
    dt = get_azi()
    zi_str = get_zi_romana(dt)

    # 1. Doxologia
    t0 = __import__('time').time()
    zi_data = fetch_doxologia_calendar(dt)
    t_dox = round(__import__('time').time() - t0, 2)

    # 2. Verset bibliaortodoxa.ro
    ev_ref = zi_data['gospel']['reference']
    ap_ref = zi_data['apostle']['reference']
    verse_ref = ev_ref or ap_ref
    verse = {}
    t_verse = 0
    if verse_ref:
        t1 = __import__('time').time()
        verse = fetch_biblia_ortodoxa_verse(verse_ref)
        t_verse = round(__import__('time').time() - t1, 2)

    # 3. Imagine cu verificare
    base_url = request.host_url.rstrip('/')
    t2 = __import__('time').time()
    img_status = get_imagine_with_status('', base_url)
    t_img = round(__import__('time').time() - t2, 2)
    img_url = img_status['url']

    def row(label, value, ok=None):
        if ok is True:
            icon = '<span style="color:#2e7d32;font-weight:bold;">✓</span>'
        elif ok is False:
            icon = '<span style="color:#c62828;font-weight:bold;">✗</span>'
        else:
            icon = ''
        val_style = 'color:#1a1a1a;' if value else 'color:#999;font-style:italic;'
        return (
            f'<tr><td style="padding:8px 12px;font-size:12px;color:#666;'
            f'text-transform:uppercase;letter-spacing:1px;white-space:nowrap;'
            f'border-bottom:1px solid #f0e8e8;">{label}</td>'
            f'<td style="padding:8px 12px;font-size:14px;{val_style}'
            f'border-bottom:1px solid #f0e8e8;">{icon} {value or "—"}</td></tr>'
        )

    saints_html = '<br>'.join(zi_data['saints']) if zi_data['saints'] else '—'
    warnings_html = ''
    if zi_data['warnings']:
        items = ''.join(f'<li>{w}</li>' for w in zi_data['warnings'])
        warnings_html = (
            f'<div style="background:#fff3cd;border:1px solid #ffc107;'
            f'padding:10px 14px;margin:16px 0;border-radius:6px;font-size:13px;">'
            f'<b>Avertismente:</b><ul style="margin:6px 0 0;padding-left:18px;">'
            f'{items}</ul></div>'
        )

    verse_text = verse.get('text', '')
    verse_ok   = verse.get('verified', False)
    verse_url  = verse.get('source_url', '')
    verse_link = (f'<a href="{verse_url}" target="_blank" style="color:#8B0000;">'
                  f'{verse_ref}</a>') if verse_url else verse_ref

    # Debug Biblia Ortodoxa
    dbg = verse.get('debug', {})
    dbg_rows = ''
    if dbg:
        def dbg_row(label, val):
            val_s = str(val) if val else '—'
            return (
                f'<tr><td style="padding:5px 10px;font-size:11px;color:#888;'
                f'white-space:nowrap;border-bottom:1px solid #f5f0f0;">{label}</td>'
                f'<td style="padding:5px 10px;font-size:12px;color:#444;'
                f'border-bottom:1px solid #f5f0f0;word-break:break-all;">{val_s}</td></tr>'
            )
        segs_str = '; '.join(
            f"cap {s['chapter']} v{s['v_start'] or '?'}-{s['v_end'] or '?'}"
            for s in dbg.get('segments', [])
        )
        urls_str = '<br>'.join(
            f'<a href="{u}" target="_blank" style="color:#8B0000;">{u}</a>'
            for u in dbg.get('urls_accessed', [])
        )
        dbg_rows = (
            dbg_row('ref_received', dbg.get('ref_received'))
            + dbg_row('ref_normalized', dbg.get('ref_normalized'))
            + dbg_row('book_detected', dbg.get('book_detected'))
            + dbg_row('segmente', segs_str or '—')
            + dbg_row('url(uri) accesate', urls_str or '—')
            + dbg_row('versete_gasite', dbg.get('verses_found'))
            + dbg_row('motiv_esec', dbg.get('reason_failure') or '—')
        )
        dbg_section = (
            f'<details style="margin-top:8px;">'
            f'<summary style="font-size:12px;color:#888;cursor:pointer;">Debug detalii</summary>'
            f'<table style="width:100%;border-collapse:collapse;margin-top:6px;">'
            f'{dbg_rows}</table></details>'
        )
    else:
        dbg_section = ''

    verse_warning = verse.get('warning', '')

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Test Bot Parohie</title>
</head>
<body style="font-family:Georgia,serif;max-width:700px;margin:32px auto;padding:0 16px;background:#fdf8f3;">

<h2 style="color:#8B0000;margin:0 0 4px;font-size:20px;">Test Pipeline Liturgic</h2>
<p style="margin:0 0 20px;color:#888;font-size:13px;">{zi_str}</p>

<h3 style="color:#8B0000;font-size:14px;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px;">
  1. Doxologia.ro
  <span style="font-weight:normal;color:#888;font-size:12px;">({t_dox}s)</span>
</h3>
<table style="width:100%;border-collapse:collapse;background:#fff;border-radius:8px;
  box-shadow:0 1px 6px rgba(0,0,0,.07);margin-bottom:20px;overflow:hidden;">
  {row('Sfintii zilei', saints_html, bool(zi_data['saints']))}
  {row('Apostolul', ap_ref, bool(ap_ref))}
  {row('Evanghelia', ev_ref, bool(ev_ref))}
</table>

<h3 style="color:#8B0000;font-size:14px;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px;">
  2. Biblia Ortodoxa ({verse_link})
  <span style="font-weight:normal;color:#888;font-size:12px;">({t_verse}s)</span>
</h3>
<div style="background:#fff;border-radius:8px;box-shadow:0 1px 6px rgba(0,0,0,.07);
  margin-bottom:20px;overflow:hidden;">
<table style="width:100%;border-collapse:collapse;">
  {row('Referinta', verse_ref, bool(verse_ref))}
  {row('Text verset', verse_text[:200] + ('…' if len(verse_text) > 200 else ''), verse_ok)}
  {row('Verificat', 'DA' if verse_ok else 'NU', verse_ok)}
  {''.join([row('Avertisment', verse_warning, False)]) if verse_warning else ''}
</table>
<div style="padding:4px 12px 10px;">{dbg_section}</div>
</div>

<h3 style="color:#8B0000;font-size:14px;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px;">
  3. Imagine Facebook
  <span style="font-weight:normal;color:#888;font-size:12px;">({t_img}s)</span>
</h3>
<div style="background:#fff;border-radius:8px;box-shadow:0 1px 6px rgba(0,0,0,.07);margin-bottom:20px;overflow:hidden;">
<table style="width:100%;border-collapse:collapse;">
  {row('URL incercat', img_status['tried_url'], None)}
  {row('Status HTTP', str(img_status['status_code']), img_status['verified'])}
  {row('Fallback folosit', 'DA' if img_status['fallback_used'] else 'NU', None)}
  {row('Sursa locala', 'DA' if img_status['is_local'] else 'NU', None)}
  {row('URL final', img_url, img_status['verified'])}
</table>
<div style="padding:12px;">
  <img src="{img_url}" referrerpolicy="no-referrer" crossorigin="anonymous"
       style="max-width:100%;border-radius:6px;max-height:200px;object-fit:cover;"
       onerror="this.style.display='none';document.getElementById('img-err').style.display='block';" />
  <div id="img-err" style="display:none;color:#c62828;font-size:13px;padding:8px 0;">
    ✗ Imaginea nu s-a incarcat in browser: {img_url}
  </div>
</div>
</div>

{warnings_html}

<p style="font-size:12px;color:#aaa;margin-top:24px;border-top:1px solid #e8ddd0;padding-top:12px;">
  <a href="/preview_fb" style="color:#8B0000;">→ Preview Facebook</a> &nbsp;|&nbsp;
  <a href="/genereaza" style="color:#8B0000;">→ Genereaza articol</a> &nbsp;|&nbsp;
  <a href="/test" style="color:#8B0000;">↺ Refresh test</a>
</p>
</body></html>"""


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
