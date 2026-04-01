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

# ════════════════════════════════════════════════════════════
#  CONFIGURARE
# ════════════════════════════════════════════════════════════
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_KEY', '')
WP_URL        = os.environ.get('WP_URL', 'https://parohiacetate2.ro')
WP_USER       = os.environ.get('WP_USER', 'cetate2AI')
WP_PASS       = os.environ.get('WP_PASS', '')
TG_TOKEN      = os.environ.get('TG_TOKEN', '')
TG_CHAT_ID    = os.environ.get('TG_CHAT_ID', '')

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# Articolul generat în așteptare (un singur articol pending la un moment dat)
pending_articol = {}

def parse_json_robust(text):
    """Parsează JSON din răspunsul Claude, chiar dacă are text în jur."""
    # Încearcă direct
    try:
        return json.loads(text)
    except:
        pass
    # Caută bloc JSON între ```json ... ```
    match = re.search(r'```json\s*([\s\S]*?)\s*```', text)
    if match:
        try:
            return json.loads(match.group(1))
        except:
            pass
    # Caută primul { ... } din text
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            pass
    raise ValueError(f"Nu am putut parsa JSON din răspuns: {text[:200]}")

# ════════════════════════════════════════════════════════════
#  HELPERS DATĂ ȘI CALENDAR
# ════════════════════════════════════════════════════════════
def get_azi():
    return datetime.datetime.now()

def get_zi_romana(dt=None):
    if dt is None: dt = get_azi()
    zile = ['Luni','Marți','Miercuri','Joi','Vineri','Sâmbătă','Duminică']
    luni = ['','ianuarie','februarie','martie','aprilie','mai','iunie',
            'iulie','august','septembrie','octombrie','noiembrie','decembrie']
    return f"{zile[dt.weekday()]}, {dt.day} {luni[dt.month]} {dt.year}"

def get_tip_zi(dt=None):
    """Returnează tipul zilei: duminica, sarbatoare, post_mare, saptamana_mare, obisnuit"""
    if dt is None: dt = get_azi()
    ziua = (dt.month, dt.day)
    zi_sapt = dt.weekday()  # 0=Luni, 6=Duminică

    # Săptămâna Mare 2026: 6-11 aprilie
    saptamana_mare_2026 = [
        (4,6),(4,7),(4,8),(4,9),(4,10),(4,11)
    ]
    if ziua in saptamana_mare_2026:
        return 'saptamana_mare'

    # Sărbători mari fixe
    sarbatori_mari = {
        (1,1): "Tăierea Împrejur / Sf. Vasile cel Mare",
        (1,6): "Botezul Domnului",
        (1,7): "Soborul Sf. Ioan Botezătorul",
        (2,2): "Întâmpinarea Domnului",
        (3,25): "Buna Vestire",
        (8,6): "Schimbarea la Față",
        (8,15): "Adormirea Maicii Domnului",
        (9,8): "Nașterea Maicii Domnului",
        (9,14): "Înălțarea Sfintei Cruci",
        (11,8): "Soborul Sfinților Arhangheli",
        (11,30): "Sf. Apostol Andrei",
        (12,6): "Sf. Ierarh Nicolae",
        (12,25): "Nașterea Domnului",
        (12,26): "A doua zi de Crăciun",
    }
    if ziua in sarbatori_mari:
        return 'sarbatoare'

    # Posturi mari (date aproximative 2026)
    # Postul Mare: 23 feb - 11 apr 2026
    post_mare_start = datetime.date(2026, 2, 23)
    post_mare_end   = datetime.date(2026, 4, 11)
    # Postul Apostolilor: 15 iun - 28 iun 2026
    post_ap_start = datetime.date(2026, 6, 15)
    post_ap_end   = datetime.date(2026, 6, 28)
    # Postul Adormirii: 1-14 aug 2026
    post_ad_start = datetime.date(2026, 8, 1)
    post_ad_end   = datetime.date(2026, 8, 14)
    # Postul Crăciunului: 15 nov - 24 dec 2026
    post_cr_start = datetime.date(2026, 11, 15)
    post_cr_end   = datetime.date(2026, 12, 24)

    azi_date = dt.date() if hasattr(dt, 'date') else dt
    in_post = (
        post_mare_start <= azi_date <= post_mare_end or
        post_ap_start   <= azi_date <= post_ap_end   or
        post_ad_start   <= azi_date <= post_ad_end   or
        post_cr_start   <= azi_date <= post_cr_end
    )

    # Prima zi de post
    if azi_date in [post_mare_start, post_ap_start, post_ad_start, post_cr_start]:
        return 'inceput_post'

    if zi_sapt == 6:  # Duminică
        return 'duminica'

    if in_post:
        return 'post'

    return 'obisnuit'

def get_nume_saptamana_mare(dt=None):
    if dt is None: dt = get_azi()
    zile_patimi = {
        (4,6):  ("Lunea Mare", "Iosif cel Prea Frumos și smochinul neroditor"),
        (4,7):  ("Marțea Mare", "Parabolele Mântuitorului și semnele sfârșitului"),
        (4,8):  ("Miercurea Mare", "Ungerea cu mir la Betania și vânzarea lui Iuda"),
        (4,9):  ("Joia Mare", "Cina cea de Taină și rugăciunea din Ghetsimani"),
        (4,10): ("Vinerea Mare", "Patimile, Răstignirea și Moartea Domnului"),
        (4,11): ("Sâmbăta Mare", "Prohodul Domnului — între moarte și Înviere"),
    }
    return zile_patimi.get((dt.month, dt.day), ("Săptămâna Mare", ""))

# ════════════════════════════════════════════════════════════
#  TELEGRAM
# ════════════════════════════════════════════════════════════
def tg_send(text, reply_markup=None):
    """Trimite mesaj pe Telegram."""
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        'chat_id': TG_CHAT_ID,
        'text': text,
        'parse_mode': 'HTML'
    }
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

def tg_send_photo(photo_url, caption=""):
    """Trimite poză pe Telegram."""
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    payload = {
        'chat_id': TG_CHAT_ID,
        'photo': photo_url,
        'caption': caption,
        'parse_mode': 'HTML'
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

def tg_get_file(file_id):
    """Descarcă fișier de pe Telegram."""
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/getFile?file_id={file_id}"
        r = requests.get(url, timeout=10)
        file_path = r.json()['result']['file_path']
        file_url = f"https://api.telegram.org/file/bot{TG_TOKEN}/{file_path}"
        img_data = requests.get(file_url, timeout=15).content
        return img_data
    except:
        return None

def trimite_spre_aprobare(articol):
    """Trimite articolul generat pe Telegram spre aprobare."""
    global pending_articol
    pending_articol = articol

    preview = (
        f"✝️ <b>ARTICOL GENERAT — {articol.get('tip','').upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{articol.get('titlu_wp','')}</b>\n\n"
        f"📱 <b>Facebook:</b>\n{articol.get('fb_text','')[:400]}...\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Publică pe: <b>{'WordPress + Facebook' if articol.get('publica_wp') else 'Doar Facebook'}</b>\n\n"
        f"Răspunde cu:\n"
        f"✅ /aproba — publică acum\n"
        f"✏️ /adaug [text] — adaugă un gând personal\n"
        f"🔄 /regenereaza — generează alt articol\n"
        f"❌ /respinge — nu publica azi"
    )
    tg_send(preview)

# ════════════════════════════════════════════════════════════
#  CLAUDE API
# ════════════════════════════════════════════════════════════
def call_claude(system, user, max_tokens=2500, imagine_b64=None, imagine_media_type='image/jpeg'):
    """Apelează Claude cu text și opțional o imagine."""
    content = []
    if imagine_b64:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": imagine_media_type,
                "data": imagine_b64
            }
        })
    content.append({"type": "text", "text": user})

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}]
    )
    return message.content[0].text

# ════════════════════════════════════════════════════════════
#  WORDPRESS
# ════════════════════════════════════════════════════════════
def wp_auth_header():
    encoded = base64.b64encode(f"{WP_USER}:{WP_PASS}".encode()).decode()
    return {'Authorization': f'Basic {encoded}', 'Content-Type': 'application/json'}

def publica_articol(titlu, continut, tags=[], featured_media=None):
    """Publică articol pe WordPress."""
    data = {
        'title': titlu,
        'content': continut,
        'status': 'publish',
        'tags': tags
    }
    if featured_media:
        data['featured_media'] = featured_media
    r = requests.post(
        f"{WP_URL}/wp-json/wp/v2/posts",
        json=data,
        headers=wp_auth_header(),
        timeout=30
    )
    result = r.json()
    return result.get('id'), result.get('link', '')

def upload_imagine_wp(img_bytes, filename='imagine.jpg'):
    """Urcă imagine pe WordPress și returnează media ID."""
    encoded = base64.b64encode(f"{WP_USER}:{WP_PASS}".encode()).decode()
    headers = {
        'Authorization': f'Basic {encoded}',
        'Content-Type': 'image/jpeg',
        'Content-Disposition': f'attachment; filename={filename}'
    }
    r = requests.post(
        f"{WP_URL}/wp-json/wp/v2/media",
        data=img_bytes,
        headers=headers,
        timeout=30
    )
    result = r.json()
    return result.get('id'), result.get('source_url', '')

def publica_fb(text, imagine_url=None):
    """Publică pe Facebook via WordPress (Zapier preia automat)."""
    # Zapier preia automat din WordPress — nu e nevoie de apel FB direct
    pass

# ════════════════════════════════════════════════════════════
#  SCRAPING SURSE ORTODOXE
# ════════════════════════════════════════════════════════════
def scrape_doxologia_sfinti():
    """Preia Sfinții zilei de pe doxologia.ro"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get('https://doxologia.ro/calendar-ortodox', headers=headers, timeout=10)
        html = r.text
        # Caută sfinții în pagină
        matches = re.findall(r'<h[23][^>]*>([^<]{10,100})</h[23]>', html)
        sfinti = [m.strip() for m in matches if any(k in m.lower() for k in ['sf.','sfânta','sfântul','cuviosul','mucenic','ierarh'])]
        return sfinti[:5] if sfinti else []
    except:
        return []

def scrape_evanghelie_doxologia():
    """Preia Evanghelia zilei de pe doxologia.ro"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get('https://doxologia.ro/lecturile-zilei', headers=headers, timeout=10)
        html = r.text
        # Caută textul evangheliei
        match = re.search(r'evangheli[ae][^<]*</[^>]+>\s*<[^>]+>([^<]{50,})', html, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None
    except:
        return None

def scrape_lumina_cuvant():
    """Preia un cuvânt de învățătură de pe ziarullumina.ro"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get('https://ziarullumina.ro/spiritualitate-si-cultura/', headers=headers, timeout=10)
        html = r.text
        matches = re.findall(r'<h[23][^>]*>\s*<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]{20,120})</a>', html)
        if matches:
            link, titlu = random.choice(matches[:5])
            return titlu.strip(), link
        return None, None
    except:
        return None, None

def cauta_imagine_patriarhie(query):
    """Returnează URL imagine reprezentativă de pe patriarhia.ro sau doxologia.ro"""
    imagini_sarbatori = {
        'craciun': 'https://basilica.ro/wp-content/uploads/2023/12/nasterea-domnului.jpg',
        'paste': 'https://basilica.ro/wp-content/uploads/2024/04/invierea-domnului.jpg',
        'florii': 'https://basilica.ro/wp-content/uploads/2024/04/duminica-floriilor.jpg',
        'boboteaza': 'https://basilica.ro/wp-content/uploads/2024/01/botezul-domnului.jpg',
        'post': 'https://doxologia.ro/sites/default/files/articol/2020/03/post.jpg',
        'default': 'https://basilica.ro/wp-content/uploads/2023/10/biserica-ortodoxa.jpg',
    }
    query_lower = query.lower()
    for cheie, url in imagini_sarbatori.items():
        if cheie in query_lower:
            return url
    return imagini_sarbatori['default']

# ════════════════════════════════════════════════════════════
#  GENERARE ARTICOLE
# ════════════════════════════════════════════════════════════
SYSTEM_BASE = """Ești redactorul spiritual al Parohiei Cetate 2 Sibiu, Mitropolia Ardealului.
Scrii în stilul Preafericitului Patriarh Daniel — teologic profund dar accesibil enoriașilor.
Respecti strict învățăturile Bisericii Ortodoxe Române și ale Sfintei Scripturi.
Folosești Biblia Ortodoxă română (traducerea Bartolomeu Anania sau Sinodală).
Diacritice corecte: ă, â, î, ș, ț. Ton cald, pastoral, cu referințe patristice.
Răspunzi EXCLUSIV cu JSON valid, fără text în afara JSON-ului."""

def genereaza_articol_obisnuit(zi, sfinti, extra_text=""):
    """Luni-Sâmbătă: Evanghelie + Sfinți + Citat biblic"""
    sfinti_str = ", ".join(sfinti) if sfinti else "Sfinții zilei"
    extra = f"\nMesaj personal de la preot: {extra_text}" if extra_text else ""

    user = f"""Astăzi este {zi}. Sfinții zilei: {sfinti_str}.{extra}

Generează articolul zilnic pentru Parohia Cetate 2 Sibiu.
Returnează JSON:
{{
  "titlu_wp": "titlu articol WordPress",
  "continut_wp": "HTML complet cu: <h2>Evanghelia zilei</h2> + text evanghelie cu blockquote + <h2>Sfinții zilei</h2> + scurtă descriere fiecărui sfânt + link doxologia.ro + <h2>Cuvântul zilei</h2> + verset biblic în blockquote + meditație scurtă 100 cuvinte",
  "fb_text": "postare Facebook 150-200 cuvinte cu emoji, verset + îndemn + hashtag-uri #ParohiaCetate2 #Sibiu #Ortodox",
  "sfinti_links": [{{"nume": "...", "link": "https://doxologia.ro/..."}}],
  "tags": ["evanghelie", "calendar-ortodox", "citat-biblic"]
}}"""
    response = call_claude(SYSTEM_BASE, user, 3000)
    return parse_json_robust(response)

def genereaza_articol_duminica(zi, sfinti, include_ips=False, extra_text=""):
    """Duminică: Evanghelie + Predică stil Lumina + Sfinți + eventual IPS Laurențiu"""
    sfinti_str = ", ".join(sfinti) if sfinti else "Sfinții zilei"
    ips_section = ""
    if include_ips:
        ips_section = """+ <h2>Cuvânt arhieresc</h2> cu citat din predica IPS Laurențiu Streza inspirat din mitropolia-ardealului.ro"""
    extra = f"\nMesaj personal de la preot: {extra_text}" if extra_text else ""

    user = f"""Astăzi este {zi}, Duminică. Sfinții zilei: {sfinti_str}.{extra}

Generează articolul duminical pentru Parohia Cetate 2 Sibiu.
Returnează JSON:
{{
  "titlu_wp": "titlu articol duminical",
  "continut_wp": "HTML complet cu: <h2>Evanghelia Duminicii</h2> + pericopa evanghelică cu blockquote + <h2>Predică</h2> + predică 400-500 cuvinte stil ziarul Lumina, teologic-pastoral {ips_section} + <h2>Sfinții zilei</h2> + descriere + linkuri doxologia.ro",
  "fb_text": "postare Facebook duminicală 200-250 cuvinte cu emoji, mesaj inspirațional + hashtag-uri",
  "rezumat_predica": "rezumat predică 2-3 fraze pentru previzualizare",
  "tags": ["duminica", "evanghelie", "predica", "calendar-ortodox"]
}}"""
    response = call_claude(SYSTEM_BASE, user, 4000)
    return parse_json_robust(response)

def genereaza_articol_sarbatoare(zi, nume_sarbatoare, extra_text=""):
    """Sărbătoare mare: articol festiv + mesaj Facebook stil Patriarhie"""
    extra = f"\nMesaj personal de la preot: {extra_text}" if extra_text else ""
    imagine_url = cauta_imagine_patriarhie(nume_sarbatoare)

    user = f"""Astăzi este {zi} — {nume_sarbatoare}.{extra}

Generează articolul de sărbătoare pentru Parohia Cetate 2 Sibiu.
Returnează JSON:
{{
  "titlu_wp": "titlu articol sărbătoare",
  "continut_wp": "HTML festiv: <h2>...</h2> + semnificația sărbătorii + tropar/condac + meditație 300-400 cuvinte + urare pentru credincioși",
  "fb_text": "mesaj sărbătoare Facebook 150-200 cuvinte în stil Patriarh Daniel/Pr. Necula — cald, evlavios, cu emoji și urare",
  "imagine_url": "{imagine_url}",
  "tags": ["sarbatoare", "calendar-ortodox"]
}}"""
    response = call_claude(SYSTEM_BASE, user, 3000)
    data = parse_json_robust(response)
    data['imagine_url'] = imagine_url
    return data

def genereaza_anunt_post(zi, nume_post):
    """Prima zi de post: anunț cu citat patristic"""
    user = f"""Astăzi este {zi} — începe {nume_post}.

Generează anunțul de post pentru Parohia Cetate 2 Sibiu.
Returnează JSON:
{{
  "titlu_wp": "titlu anunț post",
  "continut_wp": "HTML: <h2>Începe {nume_post}</h2> + semnificație duhovnicească + sfaturi practice pentru post + citat Sfânt Părinte despre post + binecuvântare",
  "fb_text": "mesaj Facebook despre post 150 cuvinte cu citat dintr-un Sfânt Părinte (Sf. Ioan Gură de Aur, Sf. Vasile, etc.) + emoji + urare Post cu folos! #Post #Ortodox #ParohiaCetate2",
  "tags": ["post", "viata-duhovniceasca"]
}}"""
    response = call_claude(SYSTEM_BASE, user, 2500)
    return parse_json_robust(response)

def genereaza_articol_saptamana_mare(zi, titlu_zi, tema_zi):
    """Săptămâna Mare: articol zilnic Luni Mare - Sâmbătă Mare"""
    user = f"""Astăzi este {zi} — {titlu_zi}.
Tema zilei: {tema_zi}

Generează articolul pentru Săptămâna Patimilor, Parohia Cetate 2 Sibiu.
Returnează JSON:
{{
  "titlu_wp": "{titlu_zi} — titlu evocator",
  "continut_wp": "HTML solemn și profund: <h2>{titlu_zi}</h2> + contextul biblic al zilei din surse ortodoxe + <h2>Semnificație liturgică</h2> + explicarea slujbei zilei + <h2>Meditație</h2> + îndrumare duhovnicească pentru credincios + rugăciune scurtă",
  "fb_text": "mesaj Facebook solemn 150-200 cuvinte pentru {titlu_zi}, stil evlavios cu emoji ✝️🕯️",
  "tags": ["saptamana-mare", "patimi", "calendar-ortodox"]
}}"""
    response = call_claude(SYSTEM_BASE, user, 3500)
    return parse_json_robust(response)

def genereaza_din_poza(imagine_b64, text_preot=""):
    """Generează articol din poza trimisă de preot"""
    extra = f"Textul preotului: {text_preot}" if text_preot else "Descrie ce vezi în imagine și scrie un articol potrivit."
    zi = get_zi_romana()

    user = f"""Astăzi este {zi}. {extra}

Uită-te la imaginea trimisă de preotul Parohiei Cetate 2 Sibiu.
Returnează JSON:
{{
  "titlu_wp": "titlu articol bazat pe imagine",
  "continut_wp": "HTML 300-500 cuvinte: descriere eveniment/moment surprins + context spiritual + mesaj pastoral pentru enoriași",
  "fb_text": "postare Facebook 150-200 cuvinte cu emoji, caldă și invitantă, hashtag-uri #ParohiaCetate2 #Sibiu",
  "tags": ["viata-parohiei", "foto"]
}}"""
    response = call_claude(SYSTEM_BASE, user, 2500, imagine_b64=imagine_b64)
    return parse_json_robust(response)

def genereaza_din_text_preot(text):
    """Generează articol din textul trimis de preot"""
    zi = get_zi_romana()
    user = f"""Astăzi este {zi}. Preotul Parohiei Cetate 2 Sibiu a trimis acest mesaj: "{text}"

Transformă acest mesaj într-un articol complet pentru parohie.
Returnează JSON:
{{
  "titlu_wp": "titlu articol",
  "continut_wp": "HTML 300-400 cuvinte bazat pe mesajul preotului, completat cu context spiritual potrivit",
  "fb_text": "postare Facebook 150 cuvinte cu emoji și hashtag-uri #ParohiaCetate2 #Sibiu #Ortodox",
  "tags": ["viata-parohiei", "anunturi"]
}}"""
    response = call_claude(SYSTEM_BASE, user, 2000)
    return parse_json_robust(response)

# ════════════════════════════════════════════════════════════
#  FLUX PRINCIPAL — GENERARE ZILNICĂ
# ════════════════════════════════════════════════════════════
def genereaza_articol_zilnic(extra_text=""):
    """Funcția principală — determină tipul zilei și generează articolul potrivit."""
    global pending_articol
    dt = get_azi()
    zi = get_zi_romana(dt)
    tip = get_tip_zi(dt)
    sfinti = scrape_doxologia_sfinti()

    try:
        if tip == 'saptamana_mare':
            titlu_zi, tema_zi = get_nume_saptamana_mare(dt)
            data = genereaza_articol_saptamana_mare(zi, titlu_zi, tema_zi)
            data['tip'] = 'saptamana_mare'
            data['publica_wp'] = True

        elif tip == 'sarbatoare':
            sarbatori_mari = {
                (1,1): "Tăierea Împrejur / Sf. Vasile cel Mare",
                (1,6): "Botezul Domnului",
                (2,2): "Întâmpinarea Domnului",
                (3,25): "Buna Vestire",
                (8,6): "Schimbarea la Față",
                (8,15): "Adormirea Maicii Domnului",
                (9,8): "Nașterea Maicii Domnului",
                (9,14): "Înălțarea Sfintei Cruci",
                (11,8): "Soborul Sfinților Arhangheli",
                (11,30): "Sf. Apostol Andrei",
                (12,6): "Sf. Ierarh Nicolae",
                (12,25): "Nașterea Domnului",
            }
            nume_sarbatoare = sarbatori_mari.get((dt.month, dt.day), "Sărbătoare")
            data = genereaza_articol_sarbatoare(zi, nume_sarbatoare, extra_text)
            data['tip'] = 'sarbatoare'
            data['publica_wp'] = True

        elif tip == 'inceput_post':
            posturi = {
                (2,23): "Postul Mare",
                (6,15): "Postul Sfinților Apostoli",
                (8,1):  "Postul Adormirii Maicii Domnului",
                (11,15): "Postul Crăciunului",
            }
            nume_post = posturi.get((dt.month, dt.day), "Postul")
            data = genereaza_anunt_post(zi, nume_post)
            data['tip'] = 'inceput_post'
            data['publica_wp'] = True

        elif tip == 'duminica':
            # La fiecare a 3-a duminică — include cuvânt IPS Laurențiu
            nr_sapt = dt.isocalendar()[1]
            include_ips = (nr_sapt % 3 == 0)
            data = genereaza_articol_duminica(zi, sfinti, include_ips, extra_text)
            data['tip'] = 'duminica'
            data['publica_wp'] = True

        elif tip == 'post':
            # Zile de post (Miercuri, Vineri din posturi): meditație scurtă
            cuvant_titlu, cuvant_link = scrape_lumina_cuvant()
            user = f"""Astăzi este {zi} — zi de post.
Sursă de inspirație: {cuvant_titlu or 'Cuvântul Evangheliei'}.

Generează meditație duhovnicească scurtă pentru zi de post.
Returnează JSON:
{{"titlu_wp": "titlu meditație post",
  "continut_wp": "HTML 250-350 cuvinte: semnificația postului în ziua respectivă + citat patristic + îndemn duhovnicesc",
  "fb_text": "postare Facebook scurtă 100-150 cuvinte despre post cu emoji și hashtag-uri",
  "tags": ["post", "meditatie", "viata-duhovniceasca"]}}"""
            response = call_claude(SYSTEM_BASE, user, 2000)
            data = parse_json_robust(response)
            data['tip'] = 'post'
            data['publica_wp'] = True  # Zilele de post obișnuite — doar Facebook

        else:
            # Zi obișnuită (Luni-Sâmbătă)
            data = genereaza_articol_obisnuit(zi, sfinti, extra_text)
            data['tip'] = 'obisnuit'
            data['publica_wp'] = True  # Zilele obișnuite — doar Facebook

        if extra_text:
            data['extra_text'] = extra_text

        trimite_spre_aprobare(data)
        return data

    except Exception as e:
        tg_send(f"❌ Eroare la generare articol: {str(e)}")
        return None

# ════════════════════════════════════════════════════════════
#  WEBHOOK TELEGRAM
# ════════════════════════════════════════════════════════════
@app.route('/webhook', methods=['POST'])
def webhook():
    global pending_articol
    update = request.json
    if not update:
        return jsonify({'ok': True})

    message = update.get('message', {})
    chat_id = str(message.get('chat', {}).get('id', ''))

    # Securitate: acceptă doar mesaje de la preot
    if chat_id != TG_CHAT_ID:
        return jsonify({'ok': True})

    text = message.get('text', '')
    photo = message.get('photo')
    caption = message.get('caption', '')

    # ── Comenzi de aprobare ──────────────────────────────────
    if text == '/aproba':
        if not pending_articol:
            tg_send("⚠️ Nu există niciun articol în așteptare.")
            return jsonify({'ok': True})

        articol = pending_articol
        try:
            media_id = None
            if articol.get('imagine_url'):
                try:
                    img_r = requests.get(articol['imagine_url'], timeout=10)
                    media_id, _ = upload_imagine_wp(img_r.content)
                except:
                    pass

            if articol.get('publica_wp', False):
                post_id, link = publica_articol(
                    articol['titlu_wp'],
                    articol['continut_wp'],
                    articol.get('tags', []),
                    media_id
                )
                tg_send(
                    f"✅ <b>Publicat pe WordPress!</b>\n"
                    f"🔗 {link}\n\n"
                    f"📘 Facebook va prelua automat prin Zapier."
                )
            else:
                # Doar Facebook — postăm un articol scurt pe WP pentru Zapier
                post_id, link = publica_articol(
                    articol['titlu_wp'],
                    f"<p>{articol.get('fb_text','')}</p>",
                    articol.get('tags', []),
                    media_id
                )
                tg_send(
                    f"✅ <b>Publicat pe Facebook!</b>\n"
                    f"(articol scurt pe WP pentru Zapier)\n"
                    f"🔗 {link}"
                )
            pending_articol = {}
        except Exception as e:
            tg_send(f"❌ Eroare la publicare: {str(e)}")

    elif text.startswith('/adaug '):
        extra = text[7:].strip()
        if not pending_articol:
            tg_send("⚠️ Nu există articol pending. Generez unul nou cu textul tău...")
            threading.Thread(target=genereaza_articol_zilnic, args=(extra,)).start()
        else:
            tg_send("✍️ Regenerez articolul cu gândul tău personal...")
            tip = pending_articol.get('tip', 'obisnuit')
            threading.Thread(target=genereaza_articol_zilnic, args=(extra,)).start()

    elif text == '/regenereaza':
        tg_send("🔄 Generez un articol nou...")
        threading.Thread(target=genereaza_articol_zilnic).start()

    elif text == '/respinge':
        pending_articol = {}
        tg_send("❌ Articolul a fost respins. Nu se publică azi.")

    elif text == '/start' or text == '/help':
        tg_send(
            "✝️ <b>Bot Parohia Cetate 2 Sibiu</b>\n\n"
            "<b>Comenzi:</b>\n"
            "/aproba — publică articolul curent\n"
            "/adaug [text] — adaugă gând personal\n"
            "/regenereaza — generează alt articol\n"
            "/respinge — nu publica azi\n"
            "/genereaza — generează articol manual\n\n"
            "📸 Trimite o <b>poză</b> (cu sau fără text) pentru articol foto\n"
            "💬 Trimite un <b>text</b> pentru articol manual"
        )

    elif text == '/genereaza':
        tg_send("✍️ Generez articolul zilei...")
        threading.Thread(target=genereaza_articol_zilnic).start()

    # ── Poză trimisă de preot ────────────────────────────────
    elif photo:
        tg_send("📸 Am primit poza. Generez articolul... (30-60 secunde)")
        def process_photo():
            try:
                file_id = photo[-1]['file_id']  # cea mai mare rezoluție
                img_bytes = tg_get_file(file_id)
                if not img_bytes:
                    tg_send("❌ Nu am putut descărca poza.")
                    return
                img_b64 = base64.b64encode(img_bytes).decode()
                data = genereaza_din_poza(img_b64, caption)
                data['tip'] = 'foto'
                data['publica_wp'] = True
                data['img_bytes'] = img_bytes
                trimite_spre_aprobare(data)
            except Exception as e:
                tg_send(f"❌ Eroare procesare poză: {str(e)}")
        threading.Thread(target=process_photo).start()

    # ── Text liber de la preot ───────────────────────────────
    elif text and not text.startswith('/'):
        tg_send("✍️ Am primit mesajul tău. Generez articolul... (20-30 secunde)")
        def process_text():
            try:
                data = genereaza_din_text_preot(text)
                data['tip'] = 'manual'
                data['publica_wp'] = True
                trimite_spre_aprobare(data)
            except Exception as e:
                tg_send(f"❌ Eroare: {str(e)}")
        threading.Thread(target=process_text).start()

    return jsonify({'ok': True})

# ════════════════════════════════════════════════════════════
#  ENDPOINT-URI HTTP (pentru cron jobs Hostico)
# ════════════════════════════════════════════════════════════
@app.route('/')
def home():
    return f"✝️ Bot Parohia Cetate 2 — activ! {get_azi().strftime('%d.%m.%Y %H:%M')}"

@app.route('/genereaza')
def endpoint_genereaza():
    """Apelat de cron job la 7:00 — generează și trimite spre aprobare."""
    threading.Thread(target=genereaza_articol_zilnic).start()
    return jsonify({'status': 'generare_pornita', 'ora': get_azi().strftime('%H:%M')})

@app.route('/citat')
def endpoint_citat():
    """Păstrat pentru compatibilitate."""
    return endpoint_genereaza()

@app.route('/evanghelia')
def endpoint_evanghelia():
    """Păstrat pentru compatibilitate."""
    return endpoint_genereaza()

@app.route('/setup_webhook')
def setup_webhook():
    """Setează webhook-ul Telegram — apelează o singură dată."""
    webhook_url = f"https://bot-parohie.onrender.com/webhook"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/setWebhook?url={webhook_url}"
    r = requests.get(url, timeout=10)
    return jsonify(r.json())

# ════════════════════════════════════════════════════════════
#  START
# ════════════════════════════════════════════════════════════
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)