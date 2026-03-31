from flask import Flask, request, jsonify
import anthropic
import requests
import base64
import datetime
import os
import re
import random

app = Flask(__name__)

ANTHROPIC_KEY = os.environ.get('ANTHROPIC_KEY', '')
WP_URL = os.environ.get('WP_URL', 'https://parohiacetate2.ro')
WP_USER = os.environ.get('WP_USER', 'cetate2AI')
WP_PASS = os.environ.get('WP_PASS', '')

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

def get_zi_romana():
    zile = ['Duminică','Luni','Marți','Miercuri','Joi','Vineri','Sâmbătă']
    luni = ['','ianuarie','februarie','martie','aprilie','mai','iunie','iulie','august','septembrie','octombrie','noiembrie','decembrie']
    now = datetime.datetime.now()
    return f"{zile[now.weekday()]}, {now.day} {luni[now.month]} {now.year}"

def call_claude(system, user, max_tokens=2000):
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role":"user","content":user}]
    )
    return message.content[0].text

def publica_articol(titlu, continut, tags=[]):
    wp_auth = base64.b64encode(f"{WP_USER}:{WP_PASS}".encode()).decode()
    headers = {'Authorization':f'Basic {wp_auth}','Content-Type':'application/json'}
    data = {'title':titlu,'content':continut,'status':'publish','tags':tags}
    r = requests.post(f"{WP_URL}/wp-json/wp/v2/posts",json=data,headers=headers,timeout=30)
    result = r.json()
    return result.get('id'), result.get('link','')

@app.route('/')
def home():
    return f"Bot Parohia Cetate 2 - activ! {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}"

@app.route('/evanghelia')
def evanghelia():
    zi = get_zi_romana()
    system = ("Ești un preot ortodox român. Te inspiri din doxologia.ro și bazilica.ro. "
              "Articole calde, spirituale, cu diacritice corecte. Răspunzi DOAR cu JSON valid.")
    user = (f"Astăzi este {zi}. Scrie Evanghelia zilei pentru Parohia Cetate 2 Sibiu.\n"
            'Returnează JSON: {"titlu_wp":"titlu","continut_wp":"HTML 500-700 cuvinte cu h2 p blockquote strong","rezumat_fb":"Facebook 150-250 cuvinte cu emoji"}')
    import json
    response = call_claude(system, user, 2000)
    try:
        data = json.loads(response)
    except:
        return jsonify({'error':'JSON invalid'}), 500
    post_id, link = publica_articol(data['titlu_wp'], data['continut_wp'], ['evanghelie','calendar-ortodox'])
    return jsonify({'success':True,'post_id':post_id,'link':link,'facebook':data.get('rezumat_fb','')})

@app.route('/sfinti')
def sfinti():
    zi = get_zi_romana()
    system = ("Ești un hagiograf ortodox român inspirat din doxologia.ro. "
              "Diacritice corecte. Răspunzi DOAR cu JSON valid.")
    user = (f"Astăzi este {zi}. Scrie despre Sfinții zilei pentru Parohia Cetate 2 Sibiu.\n"
            'Returnează JSON: {"titlu_wp":"titlu","continut_wp":"HTML 400-600 cuvinte","rezumat_fb":"Facebook 100-150 cuvinte cu emoji"}')
    import json
    response = call_claude(system, user, 1500)
    try:
        data = json.loads(response)
    except:
        return jsonify({'error':'JSON invalid'}), 500
    post_id, link = publica_articol(data['titlu_wp'], data['continut_wp'], ['sfinti','calendar-ortodox'])
    return jsonify({'success':True,'post_id':post_id,'link':link})

@app.route('/citat')
def citat():
    zi = get_zi_romana()
    carti = ['Psalmi','Proverbe','Isaia','Matei','Luca','Ioan','Romani','Efeseni','Filipeni','1 Ioan','Iacov']
    carte = random.choice(carti)
    system = ("Ești un teolog ortodox român. Folosești Biblia Ortodoxă română. "
              "Comentarii scurte, profunde. Răspunzi DOAR cu JSON valid.")
    user = (f"Astăzi este {zi}. Alege un verset din {carte}.\n"
            'Returnează JSON: {"titlu_wp":"titlu","continut_wp":"HTML cu blockquote și comentariu","rezumat_fb":"Facebook cu versetul și emoji"}')
    import json
    response = call_claude(system, user, 1500)
    try:
        data = json.loads(response)
    except:
        return jsonify({'error':'JSON invalid'}), 500
    post_id, link = publica_articol(data['titlu_wp'], data['continut_wp'], ['biblie','citat-biblic'])
    return jsonify({'success':True,'post_id':post_id,'link':link})

@app.route('/mitropolit')
def mitropolit():
    import json
    try:
        r = requests.get('https://mitropolia-ardealului.ro/', timeout=10,
                        headers={'User-Agent':'Mozilla/5.0'})
        html = r.text
        matches = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]{20,})</a>', html)
        keywords = ['mitropolit','laurențiu','predică','vizită','liturghie']
        stire = None
        for link, titlu in matches:
            titlu = titlu.strip()
            if any(kw.lower() in titlu.lower() for kw in keywords):
                if not link.startswith('http'):
                    link = 'https://mitropolia-ardealului.ro' + link
                stire = {'titlu':titlu,'link':link}
                break
        if not stire:
            return jsonify({'error':'Nu am găsit știri'}), 404
    except:
        return jsonify({'error':'Eroare scraping'}), 500

    system = ("Ești redactorul Parohiei Cetate 2 Sibiu. Scrii despre Mitropolitul Laurențiu Streza "
              "cu respect și evlavie, inspirat din bazilica.ro. Răspunzi DOAR cu JSON valid.")
    user = (f"Știre: {stire['titlu']}\nLink: {stire['link']}\n"
            'Returnează JSON: {"titlu_wp":"titlu","continut_wp":"HTML 300-500 cuvinte","rezumat_fb":"Facebook 100-150 cuvinte"}')
    response = call_claude(system, user, 1500)
    try:
        data = json.loads(response)
    except:
        return jsonify({'error':'JSON invalid'}), 500
    post_id, link = publica_articol(data['titlu_wp'], data['continut_wp'], ['mitropolia-ardealului','mitropolit'])
    return jsonify({'success':True,'post_id':post_id,'link':link})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
