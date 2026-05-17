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
GROQ_KEY      = os.environ.get('GROQ_KEY', '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')
WP_URL        = os.environ.get('WP_URL', 'https://parohiacetate2.ro')
WP_USER       = os.environ.get('WP_USER', 'cetate2AI')
WP_PASS       = os.environ.get('WP_PASS', '')
TG_TOKEN      = os.environ.get('TG_TOKEN', '')
TG_CHAT_ID    = os.environ.get('TG_CHAT_ID', '')

client = OpenAI(api_key=GROQ_KEY, base_url="https://api.groq.com/openai/v1")
pending_articol = {}

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

def get_tip_zi(dt=None):
    if dt is None:
        dt = get_azi()
    ziua   = (dt.month, dt.day)
    zi_sapt = dt.weekday()  # 0=Luni, 6=Duminica

    # Saptamana Mare 2026 (se poate extinde pentru ani viitori)
    saptamana_mare = [(4,6),(4,7),(4,8),(4,9),(4,10),(4,11)]
    if ziua in saptamana_mare:
        return 'saptamana_mare'

    # Sarbatori mari fixe
    sarbatori = {
        (1,1),(1,6),(1,7),(2,2),(3,25),(8,6),(8,15),
        (9,8),(9,14),(11,8),(11,30),(12,6),(12,25),(12,26)
    }
    if ziua in sarbatori:
        return 'sarbatoare'

    azi_date = dt.date() if hasattr(dt,'date') else dt

    # Posturi 2026 - de actualizat anual
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
    if in_post and zi_sapt in [2, 4]:  # Miercuri si Vineri din post
        return 'post'
    if in_post:
        return 'post_saptamana'  # Restul zilelor din post
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
    return zile.get((dt.month,dt.day), ("Saptamana Mare",""))

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
    p = {
        (2,23):"Postul Mare",(6,15):"Postul Sfintilor Apostoli",
        (8,1):"Postul Adormirii Maicii Domnului",(11,15):"Postul Craciunului",
    }
    return p.get((dt.month,dt.day), "Postul")

# ============================================================
#  SCRAPING
# ============================================================
def scrape_sfinti():
    try:
        h = {'User-Agent':'Mozilla/5.0'}
        r = requests.get('https://doxologia.ro/calendar-ortodox', headers=h, timeout=10)
        m = re.findall(r'<h[23][^>]*>([^<]{10,100})</h[23]>', r.text)
        sfinti = [x.strip() for x in m if any(
            k in x.lower() for k in
            ['sf.','sfanta','sfantul','cuviosul','mucenic','ierarh','apostol','prooroc','cuv.']
        )]
        return sfinti[:6]
    except:
        return []

def scrape_apostol_evanghelie():
    """Preia Apostolul si Evanghelia de pe doxologia.ro/lecturile-zilei"""
    try:
        h = {'User-Agent':'Mozilla/5.0'}
        r = requests.get('https://doxologia.ro/lecturile-zilei', headers=h, timeout=12)
        text = r.text
        ap, ev = '', ''

        # Apostol
        for pat in [
            r'(?:Apostol|Epistola)[^<]{0,50}</[^>]+>\s*<[^>]+>([^<]{40,500})',
            r'<[^>]*apostol[^>]*>([^<]{40,500})',
        ]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                ap = re.sub(r'<[^>]+>','',m.group(1)).strip()[:500]
                break

        # Evanghelie
        for pat in [
            r'(?:Evanghelia|Evanghelie)[^<]{0,50}</[^>]+>\s*<[^>]+>([^<]{40,500})',
            r'<[^>]*evangheli[^>]*>([^<]{40,500})',
        ]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                ev = re.sub(r'<[^>]+>','',m.group(1)).strip()[:500]
                break

        return ap, ev
    except:
        return '', ''

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

def get_imagine_doxologia(query=''):
    """Incearca sa ia imagine reala de pe doxologia.ro"""
    try:
        h = {'User-Agent':'Mozilla/5.0'}
        # Incearca pagina calendarului
        r = requests.get('https://doxologia.ro/calendar-ortodox', headers=h, timeout=10)
        # Cauta imagini cu dimensiuni rezonabile
        imgs = re.findall(
            r'<img[^>]+src=["\']([^"\']*(?:doxologia\.ro|basilica\.ro)[^"\']*\.jpg)["\']',
            r.text
        )
        # Filtrare imagini mici (avatare etc.)
        for img in imgs:
            if 'icon' not in img.lower() and 'logo' not in img.lower() and 'thumb' not in img.lower():
                # Verifica ca exista
                try:
                    ir = requests.head(img, timeout=5)
                    if ir.status_code == 200:
                        return img
                except:
                    pass
    except:
        pass
    return get_imagine_fallback(query)

def get_imagine_fallback(query=''):
    """Imagini de rezerva verificate"""
    imagini = {
        'craciun':   'https://basilica.ro/wp-content/uploads/2023/12/nasterea-domnului.jpg',
        'paste':     'https://basilica.ro/wp-content/uploads/2024/04/invierea-domnului.jpg',
        'florii':    'https://basilica.ro/wp-content/uploads/2024/04/duminica-floriilor.jpg',
        'boboteaza': 'https://basilica.ro/wp-content/uploads/2024/01/botezul-domnului.jpg',
        'post':      'https://basilica.ro/wp-content/uploads/2023/03/postul-mare.jpg',
        'maica':     'https://basilica.ro/wp-content/uploads/2023/08/adormirea-maicii-domnului.jpg',
        'cruce':     'https://basilica.ro/wp-content/uploads/2023/09/inaltarea-sfintei-cruci.jpg',
        'nicolae':   'https://basilica.ro/wp-content/uploads/2023/12/sfantul-nicolae.jpg',
        'andrei':    'https://basilica.ro/wp-content/uploads/2023/11/sf-apostol-andrei.jpg',
        'vasile':    'https://basilica.ro/wp-content/uploads/2024/01/sf-vasile-cel-mare.jpg',
        'botez':     'https://basilica.ro/wp-content/uploads/2024/01/botezul-domnului.jpg',
        'default':   'https://basilica.ro/wp-content/uploads/2023/10/biserica-ortodoxa.jpg',
    }
    q = query.lower()
    for k,v in imagini.items():
        if k in q:
            return v
    return imagini['default']

def get_imagine(tip='', query=''):
    img = get_imagine_doxologia(query + ' ' + tip)
    if not img:
        img = get_imagine_fallback(tip + ' ' + query)
    return img

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
    continut_final = continut + SEMNATURA_HTML + get_bloc_resurse()
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
    r = requests.post(f"{WP_URL}/wp-json/wp/v2/media",
                      data=data_bytes, headers=h, timeout=60)
    res = r.json()
    return res.get('id'), res.get('source_url', '')

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

Raspunzi EXCLUSIV cu JSON valid. Zero text in afara JSON. Zero markdown in afara JSON."""

# ============================================================
#  GENERARE PRINCIPALA
# ============================================================
def genereaza_articol_zilnic(extra_text=''):
    global pending_articol
    dt      = get_azi()
    zi      = get_zi_romana(dt)
    tip     = get_tip_zi(dt)
    sfinti  = scrape_sfinti()
    apostol, evanghelie = scrape_apostol_evanghelie()
    zi_spec = get_zi_speciala(dt)
    an_om   = get_an_omagial()

    # Fallback daca nu s-a gasit Apostol/Evanghelie
    if not apostol or not evanghelie:
        pilda, solomon = scrape_pilde_solomon()
        apostol   = apostol or pilda
        evanghelie = evanghelie or solomon

    sfinti_str = ', '.join(sfinti) if sfinti else 'Sfintii zilei'
    s_extra = f'\nGandul preotului (integreaza natural, nu fortat): {extra_text}' if extra_text else ''
    s_spec  = f'\nZi speciala de marcat discret: {zi_spec}' if zi_spec else ''
    s_an    = f'\nAnul omagial (mentionare discreta): {an_om}' if an_om else ''

    try:
        if tip == 'saptamana_mare':
            titlu_zi, tema_zi = get_nume_saptamana_mare(dt)
            data = _gen_saptamana_mare(zi, titlu_zi, tema_zi, apostol, evanghelie, s_extra)
            data['categorii'] = [CAT_PREDICA]
            data['video_bloc'] = get_video_resurse_saptamana_mare(titlu_zi)

        elif tip == 'sarbatoare':
            nume = get_nume_sarbatoare(dt)
            data = _gen_sarbatoare(zi, nume, apostol, evanghelie, s_extra, s_spec, s_an)
            data['categorii'] = [CAT_PREDICA, CAT_POSTARI_NOI]
            data['imagine_query'] = nume.lower()

        elif tip == 'inceput_post':
            nume = get_nume_post(dt)
            data = _gen_inceput_post(zi, nume, apostol, evanghelie, s_extra, s_an)
            data['categorii'] = [CAT_TRAIESTE]
            data['imagine_query'] = 'post'

        elif tip == 'duminica':
            nr = dt.isocalendar()[1]
            data = _gen_duminica(zi, sfinti_str, apostol, evanghelie,
                                  (nr % 3 == 0), s_extra, s_spec, s_an)
            data['categorii'] = [CAT_PREDICA, CAT_TRAIESTE]

        elif tip in ['post', 'post_saptamana']:
            data = _gen_zi_post(zi, sfinti_str, apostol, evanghelie, s_extra, s_spec, tip)
            data['categorii'] = [CAT_TRAIESTE]
            data['imagine_query'] = 'post'

        else:
            data = _gen_zi_obisnuita(zi, sfinti_str, apostol, evanghelie, s_extra, s_spec, s_an)
            data['categorii'] = [CAT_TRAIESTE, CAT_POSTARI_NOI]

        # Imagine
        query = data.get('imagine_query', tip)
        data['imagine_url'] = get_imagine(tip, query)
        data['publica_wp']  = True
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
def _bloc_lecturi(apostol, evanghelie):
    """Bloc HTML elegant pentru Apostol si Evanghelie"""
    if not apostol and not evanghelie:
        return ''
    bloc = '<div style="background:#fdf8f3;border-left:3px solid #8B0000;padding:16px 20px;margin:20px 0;border-radius:0 6px 6px 0;">'
    if apostol:
        bloc += f'<p style="margin:0 0 6px 0;font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#8B0000;font-weight:bold;">Apostolul zilei</p>'
        bloc += f'<p style="margin:0 0 16px 0;font-style:italic;color:#333;line-height:1.8;">{apostol}</p>'
    if evanghelie:
        bloc += f'<p style="margin:0 0 6px 0;font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#8B0000;font-weight:bold;">Evanghelia zilei</p>'
        bloc += f'<p style="margin:0;font-style:italic;color:#333;line-height:1.8;">{evanghelie}</p>'
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
  "fb_text": "220-260 cuvinte: incepe cu Apostolul sau Evanghelia ca scurt citat + Sfintii zilei pe scurt + meditatie calda stil Pr. Necula + intrebare sau indemn + #ParohiaCetate2Sibiu #EvanghelliaZilei #SfintiiZilei #Ortodox #Sibiu"
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
  "fb_text": "250-280 cuvinte: Apostol scurt + Evanghelie scurta + meditatie duminicala calda + urare + #DuminicaOrtodoxa #ParohiaCetate2Sibiu #Evanghelie #Predica #Sibiu"
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
  "fb_text": "220-260 cuvinte: urare in duhul Bisericii + Tropar scurt + meditatie calda + indemn la slujba si rugaciune + emoji potrivite + hashtag-uri"
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
  "fb_text": "180-220 cuvinte: Apostol sau Evanghelie + Sfintii zilei + citat patristic + indemn pentru zi de post + hashtag-uri #ZiDePost #ParohiaCetate2Sibiu #Ortodox"
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
    apostol, evanghelie = scrape_apostol_evanghelie()
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
    apostol, evanghelie = scrape_apostol_evanghelie()
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
    apostol, evanghelie = scrape_apostol_evanghelie()
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
    global pending_articol
    update = request.json
    if not update:
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
                            f'<div style="margin:20px 0;padding:16px;background:#f5f5f5;border-radius:8px;">'
                            f'<p style="margin:0 0 8px 0;font-size:13px;color:#666;">Mesaj audio:</p>'
                            f'<audio controls style="width:100%">'
                            f'<source src="{aurl}" type="audio/ogg"></audio></div>'
                        )
                except:
                    pass

            # Video bloc (Saptamana Mare)
            video_bloc = art.get('video_bloc', '')

            continut = (bloc_audio or '') + art.get('continut_wp', '') + (video_bloc or '')
            cat = art.get('categorii', [CAT_TRAIESTE])

            post_id, link = publica_articol(art['titlu_wp'], continut, cat, media_id)

            if link:
                tg_send(
                    f"Publicat pe WordPress!\n{link}\n\n"
                    f"Facebook preia automat prin Zapier."
                )
            else:
                tg_send("Eroare - verificati WordPress.")
            pending_articol = {}

        except Exception as e:
            tg_send(f"Eroare la publicare: {str(e)}")

    elif text.startswith('/adaug '):
        extra = text[7:].strip()
        tg_send("Regenerez cu gandul tau... (30-60 sec)")
        def _trigger_adaug():
            try:
                requests.get(f"https://bot-parohie.onrender.com/genereaza?extra={requests.utils.quote(extra)}", timeout=280)
            except:
                pass
        threading.Thread(target=_trigger_adaug, daemon=True).start()

    elif text == '/regenereaza':
        tg_send("Generez articol nou...")
        def _trigger_regen():
            try:
                requests.get("https://bot-parohie.onrender.com/genereaza", timeout=280)
            except:
                pass
        threading.Thread(target=_trigger_regen, daemon=True).start()

    elif text == '/respinge':
        pending_articol = {}
        tg_send("Articolul a fost respins.")

    elif text in ['/start', '/help']:
        tg_send(
            "<b>Bot Parohia Cetate 2 Sibiu</b>\n\n"
            "<b>Comenzi:</b>\n"
            "/genereaza - articolul zilei\n"
            "/aproba - publica articolul curent\n"
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
