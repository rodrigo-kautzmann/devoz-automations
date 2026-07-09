#!/usr/bin/env python3
"""Gera o mapa interativo "Onde estamos" (HTML self-contained) pro Google Sites.

Uso self-service (sem login/Playwright): você baixa o export "Colaboradores" do
Feedz manualmente e roda este script apontando pro arquivo. Ele cospe um
onde_estamos.html (Leaflet, zoom/pan, filtro por Time/Grupo, busca) que é só colar
no Google Sites em Inserir › Incorporar › Código.

    python3 scripts/mapa_interativo.py ~/Downloads/colaboradores.xlsx
    # ou, sem argumento, ele pega o colaboradores*.xlsx mais recente da pasta atual

Privacidade: o xlsx tem CPF/banco; este script lê SÓ nome, e-mail, cidade/UF,
Departamento (Time) e Grupos. O HTML gerado só contém nome + cidade + time/grupo.
Fora do Brasil (IFD-33): preencher o campo Endereço no Feedz terminando com
"..., Cidade, País"; coordenadas de fora do BR em data/cidades_extra.csv.

Depende só de: openpyxl. Dados de apoio: data/cidades_br.csv, data/cidades_extra.csv,
map_overrides.json (opcional).
"""
import os, sys, csv, json, glob, io, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
COL = {"nome": "Nome completo", "nome2": "Nome", "email": "Email",
       "cid": "Residência - Município", "uf": "Residência - UF",
       "end": "Residência - Endereço", "dep": "Departamento", "grupos": "Grupos",
       "deslig": "Desligamento - Tipo", "ultdia": "Último dia trabalhado"}
ALIAS_CIDADE = {("distrito federal", "DF"): ("Brasília", "DF")}
PAISES_BR = ("brasil", "brazil", "br", "")


def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _load_json(name):
    p = os.path.join(HERE, name)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_coords_br():
    out = {}
    with open(os.path.join(HERE, "data", "cidades_br.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[(norm(r["nome"]), r["uf"].upper())] = (float(r["lat"]), float(r["lon"]))
    return out


def load_coords_extra():
    out = {}
    p = os.path.join(HERE, "data", "cidades_extra.csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out[(norm(r["nome"]), norm(r["pais"]))] = (float(r["lat"]), float(r["lon"]))
    return out


def clean_grupo(v):
    v = (str(v or "")).strip().strip(",").strip()
    if v.lower() in ("", "none"):
        return ""
    return ", ".join(w.strip().title() for w in v.split(",") if w.strip())


def cidade_pais_do_endereco(endereco):
    parts = [p.strip() for p in (endereco or "").split(",") if p.strip()]
    if len(parts) >= 2 and not any(ch.isdigit() for ch in parts[-1]):
        return parts[-2], parts[-1]
    return None


def read_xlsx(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True); ws = wb.active
    rows = ws.iter_rows(values_only=True)
    h = [str(x) if x is not None else "" for x in next(rows)]

    def idx(key):
        n = COL[key]
        if n not in h:
            raise SystemExit(f"Coluna '{n}' não está no export — layout do Feedz mudou? Colunas: {h[:15]}...")
        return h.index(n)

    I = {k: idx(k) for k in COL}
    pessoas = []
    for r in rows:
        if (r[I["deslig"]] and str(r[I["deslig"]]).strip()) or (r[I["ultdia"]] and str(r[I["ultdia"]]).strip()):
            continue  # desligado
        nome = str(r[I["nome"]] or r[I["nome2"]] or "").strip()
        email = str(r[I["email"]] or "").strip().lower()
        if not (nome or email):
            continue
        pessoas.append({"nome": nome or email, "email": email,
                        "cidade": str(r[I["cid"]] or "").strip(), "uf": str(r[I["uf"]] or "").strip().upper(),
                        "endereco": str(r[I["end"]] or "").strip(),
                        "time": str(r[I["dep"]] or "").strip(), "grupo": clean_grupo(r[I["grupos"]])})
    return pessoas


def build(pessoas):
    coords_br = load_coords_br(); coords_extra = load_coords_extra()
    try:
        overrides = _load_json("map_overrides.json")
    except FileNotFoundError:
        overrides = {}
    grouped, pend, warn = {}, [], []
    for p in pessoas:
        ov = overrides.get(p["email"], {}) if isinstance(overrides, dict) else {}
        cid = (ov.get("cidade") or p["cidade"]).strip(); uf = (ov.get("uf") or p["uf"]).strip().upper()
        pais = (ov.get("pais") or "").strip()
        if not cid and p["endereco"]:
            cp = cidade_pais_do_endereco(p["endereco"])
            if cp:
                cid, pais = cp; uf = ""
        if not cid:
            pend.append(p["nome"]); continue
        if norm(pais) in PAISES_BR:
            if (norm(cid), uf) in ALIAS_CIDADE:
                cid, uf = ALIAS_CIDADE[(norm(cid), uf)]
            label = f"{cid}/{uf}" if uf else cid
            lat, lon = coords_br.get((norm(cid), uf), (None, None))
        else:
            label = f"{cid}/{pais}"
            lat, lon = coords_extra.get((norm(cid), norm(pais)), (None, None))
        if "lat" in ov and "lon" in ov:
            lat, lon = float(ov["lat"]), float(ov["lon"])
        if lat is None:
            warn.append(f"sem coordenada p/ {label} ({p['email']}) — adicione em data/cidades_extra.csv")
            pend.append(p["nome"] + f" (cidade {label} sem coordenada)")
            continue
        g = grouped.setdefault(label, {"lat": lat, "lon": lon, "cidade": cid,
                                       "suf": uf or (pais if norm(pais) not in PAISES_BR else ""), "pessoas": []})
        g["pessoas"].append({"nome": p["nome"], "time": p["time"], "grupo": p["grupo"]})
    for g in grouped.values():
        g["pessoas"].sort(key=lambda x: x["nome"])
    return grouped, pend, warn


TEMPLATE = r'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Onde estamos — DevOZ</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  :root{ --green:#00D256; --green-d:#00B84C; --ink:#16231A; --muted:#5A6B5E; }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:var(--ink)}
  #wrap{display:flex;height:100vh;min-height:520px}
  #map{flex:1;height:100%}
  #side{width:380px;max-width:46%;overflow:auto;border-left:1px solid #e6ece7;padding:18px 16px 40px}
  h1{font-size:22px;margin:0 0 2px}
  .sub{color:var(--muted);font-size:13px;margin:0 0 14px}
  .stat{display:flex;gap:12px;margin:10px 0 12px}
  .stat div{background:#F1FAF4;border:1px solid #DCEFE3;border-radius:10px;padding:8px 12px;flex:1}
  .stat b{display:block;font-size:20px;color:var(--green-d)}
  .stat span{font-size:11px;color:var(--muted)}
  .flabel{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin:8px 0 4px}
  .chips{display:flex;flex-wrap:wrap;gap:5px}
  .chip{border:1px solid #DCEFE3;background:#fff;color:var(--ink);border-radius:20px;padding:3px 10px;font-size:12px;cursor:pointer;user-select:none}
  .chip:hover{background:#F1FAF4}
  .chip.on{background:var(--green);border-color:var(--green-d);color:#063a1b;font-weight:600}
  #q{width:100%;padding:8px 10px;border:1px solid #DCEFE3;border-radius:8px;font-size:13px;margin:10px 0 6px}
  .clearf{font-size:11.5px;color:var(--green-d);cursor:pointer;margin-bottom:10px;display:inline-block}
  .person{padding:8px 10px;border-radius:8px;cursor:pointer}
  .person:hover{background:#F1FAF4}
  .person .top{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
  .person .nm{font-weight:600;font-size:13px}
  .person .cy{color:var(--muted);font-size:12px;white-space:nowrap}
  .person .meta{font-size:11px;color:var(--muted);margin-top:2px}
  .tag{display:inline-block;background:#EAFBF2;border:1px solid #CDEFDC;color:var(--green-d);border-radius:20px;padding:0 7px;font-size:10.5px;margin-right:4px}
  .empty{color:var(--muted);font-size:12.5px;padding:10px}
  .pend{margin-top:16px;padding-top:12px;border-top:1px solid #eee}
  .pend h3{font-size:13px;margin:0 0 6px;color:var(--muted)}
  .pend p{font-size:12px;color:var(--muted);line-height:1.5;margin:0}
  .leaflet-popup-content{font-size:13px;line-height:1.5;width:auto !important;max-width:340px}
  .leaflet-popup-content b{color:var(--green-d)}
  .leaflet-tooltip.city-tip{white-space:normal !important;width:max-content;max-width:360px;font-size:12.5px;line-height:1.55;padding:9px 12px}
  .leaflet-tooltip.city-tip b{color:var(--green-d)}
  .foot{color:#9AA69C;font-size:11px;margin-top:16px}
</style>
</head>
<body>
<div id="wrap">
  <div id="map"></div>
  <div id="side">
    <h1>Onde estamos</h1>
    <p class="sub">Distribuição do time por cidade — fonte: Feedz &middot; __DATA_GER__</p>
    <div class="stat">
      <div><b id="s-pes"></b><span>pessoas no filtro</span></div>
      <div><b id="s-cid"></b><span>cidades</span></div>
    </div>
    <div class="flabel">Times</div><div class="chips" id="cTime"></div>
    <div class="flabel">Grupos</div><div class="chips" id="cGrupo"></div>
    <input id="q" placeholder="Buscar por nome..."/>
    <span class="clearf" id="clear">limpar filtros</span>
    <div id="list"></div>
    <div class="pend" id="pendbox"></div>
    <p class="foot">Somente cidade — nunca endereço. Selecione vários times/grupos; o mapa reflete a seleção. Passe o mouse numa bolha pra ver quem mora lá; clique numa pessoa pra centralizar.</p>
  </div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const DADOS = __DATA__;
const map = L.map('map',{scrollWheelZoom:true}).setView([-15.6,-52.0],4);
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap &copy; CARTO'}).addTo(map);
const GREEN='#00D256', GREEND='#00B84C';
const esc=s=>(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;');
const radius=n=> 8 + Math.sqrt(n)*5;
const layer=L.layerGroup().addTo(map);
const PESSOAS=[];
DADOS.pontos.forEach(p=> p.pessoas.forEach(x=> PESSOAS.push({...x, cidade:p.cidade, suf:p.suf, label:p.cidade+(p.suf?'/'+p.suf:''), lat:p.lat, lon:p.lon})));
PESSOAS.sort((a,b)=> a.nome.localeCompare(b.nome,'pt',{sensitivity:'base'}));
const uniq=(arr)=>[...new Set(arr.filter(Boolean))].sort((a,b)=>a.localeCompare(b,'pt'));
const times=uniq(PESSOAS.map(p=>p.time)), grupos=uniq(PESSOAS.map(p=>p.grupo));
const selT=new Set(), selG=new Set();
function buildChips(el, vals, set){ el.innerHTML=''; vals.forEach(v=>{ const c=document.createElement('span'); c.className='chip'; c.textContent=v; c.onclick=()=>{ set.has(v)?(set.delete(v),c.classList.remove('on')):(set.add(v),c.classList.add('on')); redraw(); }; el.appendChild(c); }); }
buildChips(document.getElementById('cTime'), times, selT);
buildChips(document.getElementById('cGrupo'), grupos, selG);
function currentPeople(){ const q=(document.getElementById('q').value||'').toLowerCase(); return PESSOAS.filter(p=> (!selT.size||selT.has(p.time)) && (!selG.size||selG.has(p.grupo)) && (!q||p.nome.toLowerCase().includes(q))); }
function redraw(){
  const ppl=currentPeople(), byCity={};
  ppl.forEach(p=>{ (byCity[p.label]=byCity[p.label]||{lat:p.lat,lon:p.lon,cidade:p.cidade,suf:p.suf,pessoas:[]}).pessoas.push(p); });
  layer.clearLayers();
  Object.values(byCity).forEach(c=>{
    const n=c.pessoas.length;
    const linhas=c.pessoas.map(x=>{const tg=[x.time,x.grupo].filter(Boolean).join(' · ');return '• '+esc(x.nome)+(tg?' <span style="color:#7c8a80">('+esc(tg)+')</span>':'');}).join('<br>');
    const titulo='<b>'+esc(c.cidade)+(c.suf?'/'+c.suf:'')+'</b> — '+n+(n>1?' pessoas':' pessoa');
    const m=L.circleMarker([c.lat,c.lon],{radius:radius(n),color:GREEND,weight:1.5,fillColor:GREEN,fillOpacity:.75}).addTo(layer);
    m.bindTooltip(titulo+'<br>'+linhas,{className:'city-tip',direction:'top',sticky:true});
    m.bindPopup(titulo+'<br>'+linhas); c._m=m;
  });
  document.getElementById('s-pes').textContent=ppl.length;
  document.getElementById('s-cid').textContent=Object.keys(byCity).length;
  const list=document.getElementById('list'); list.innerHTML='';
  if(!ppl.length){ list.innerHTML='<div class="empty">Ninguém neste filtro.</div>'; return; }
  ppl.forEach(p=>{
    const tags=[p.time,p.grupo].filter(Boolean).map(t=>'<span class="tag">'+esc(t)+'</span>').join('');
    const row=document.createElement('div'); row.className='person';
    row.innerHTML='<div class="top"><span class="nm">'+esc(p.nome)+'</span><span class="cy">'+esc(p.label)+'</span></div>'+(tags?'<div class="meta">'+tags+'</div>':'');
    row.onclick=()=>{ map.flyTo([p.lat,p.lon],8,{duration:.8}); const c=byCity[p.label]; if(c&&c._m) c._m.openPopup(); };
    list.appendChild(row);
  });
}
document.getElementById('q').addEventListener('input',redraw);
document.getElementById('clear').onclick=()=>{ selT.clear();selG.clear();document.getElementById('q').value='';document.querySelectorAll('.chip.on').forEach(c=>c.classList.remove('on'));redraw(); };
redraw();
if(DADOS.pendentes.length){ document.getElementById('pendbox').innerHTML='<h3>Cidade pendente no Feedz ('+DADOS.pendentes.length+')</h3><p>'+DADOS.pendentes.slice().sort((a,b)=>a.localeCompare(b,'pt')).join(' · ')+'</p>'; }
</script>
</body>
</html>'''


def resolve_xlsx():
    if len(sys.argv) > 1:
        return sys.argv[1]
    if os.environ.get("MAP_XLSX"):
        return os.environ["MAP_XLSX"]
    cands = sorted(glob.glob("colaboradores*.xlsx") + glob.glob("*.xlsx"), key=os.path.getmtime, reverse=True)
    if cands:
        return cands[0]
    raise SystemExit("Passe o caminho do export: python3 scripts/mapa_interativo.py <arquivo.xlsx>")


def main():
    import datetime
    path = resolve_xlsx()
    print(f"Lendo export: {path}")
    pessoas = read_xlsx(path)
    grouped, pend, warn = build(pessoas)
    pts = []
    for label, g in grouped.items():
        pts.append({"cidade": g["cidade"], "suf": g["suf"], "lat": g["lat"], "lon": g["lon"],
                    "n": len(g["pessoas"]), "pessoas": g["pessoas"]})
    pts.sort(key=lambda p: -p["n"])
    payload = {"pontos": pts, "pendentes": pend, "total": len(pessoas), "n_cidades": len(grouped)}
    html = (TEMPLATE
            .replace("__DATA_GER__", datetime.date.today().strftime("%d/%m/%Y"))
            .replace("__DATA__", json.dumps(payload, ensure_ascii=False)))
    out = os.path.abspath("onde_estamos.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"OK: {out} ({len(html)//1024} KB) — {len(pessoas)} ativos, {len(grouped)} cidades, {len(pend)} sem cidade.")
    for w in warn:
        print("AVISO:", w)
    print("\nAbra pra conferir e cole no Google Sites (Inserir › Incorporar › Código). "
          "Veja COMO-ATUALIZAR-ONDE-ESTAMOS.md.")


if __name__ == "__main__":
    main()
