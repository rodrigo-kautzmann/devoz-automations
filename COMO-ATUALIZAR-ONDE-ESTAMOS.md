# Como funciona o mapa "Onde estamos"

Mapa interativo com a cidade onde cada pessoa do time mora, publicado como um site
interno no **Google Sites** (restrito ao domínio `ozmap.com`).

> A atualização é **automática e diária** (workflow `onde-estamos` no GitHub Actions).
> Ninguém edita o Google Sites — nunca mais.

## O fluxo

```
Feedz (export xlsx) ──▶ mapa_interativo.py ──▶ onde_estamos.html
        │                                            │
   sessão salva                              drive_publish.py
   (cache Actions)                                   │
                                          arquivo fixo no Drive
                                                     │
                                     Web App Apps Script (doGet lê o Drive)
                                                     │
                                  Google Sites (Incorporar › Por URL) — nunca muda
```

O truque: o Sites não tem API, então ele embute **por URL** um Web App do Apps Script
que serve o HTML lido do Drive **a cada acesso**. Atualizar o mapa = sobrescrever o
arquivo no Drive. O Sites e o Web App nunca são tocados.

## Rotina (nenhuma)

O workflow roda todo dia às 06:20 BRT. Só intervenha se:

- **O job falhar com "Sessão do Feedz expirou":** o login do Feedz tem reCAPTCHA, então
  a credencial é uma sessão de navegador salva. Ela se renova a cada execução, mas se
  expirar de vez (ex.: workflow parado por semanas), rode local:

  ```bash
  cd "/Users/kautzmann/Claude/Projects/iafirstitizacao devoz/devoz-automations"
  python3 scripts/feedz_export.py login    # abre navegador; faça o login normal
  cat ~/.config/devoz/feedz_state.json | pbcopy
  ```

  e cole no secret **`FEEDZ_STATE_JSON`** do repo (Settings › Secrets › Actions).

- **"sem coordenada p/ X" no log:** adicione a cidade em `scripts/data/cidades_extra.csv`
  (`nome,pais,lat,lon`) e faça push — o próximo run corrige.

- **Quer atualizar agora** (entrou gente hoje): Actions › `onde-estamos` › Run workflow.

## Setup inicial (1x — checklist)

1. **Arquivo no Drive:** gere um `onde_estamos.html` (ou use o último) e suba para o seu
   Drive. Copie o **ID do arquivo** (na URL: `/d/<ID>/view`).
2. **Service account:** no Google Cloud Console, crie uma SA (ex.: `onde-estamos@…`),
   gere uma chave JSON e **compartilhe o arquivo do Drive com o e-mail da SA (Editor)**.
   Não precisa de domain-wide delegation.
3. **Web App:** em [script.google.com](https://script.google.com), novo projeto, cole
   `scripts/onde_estamos_webapp.gs`, preencha o `FILE_ID`. Implantar › Web App:
   executar como **você**, acesso **"Qualquer pessoa em ozmap.com"**. Copie a URL `/exec`.
4. **Google Sites:** na página do mapa, remova o bloco "Incorporar › Código" e insira
   **Incorporar › Por URL** com a URL `/exec`. Publique (última vez).
5. **Secrets no repo** (Settings › Secrets › Actions):
   | Secret | Conteúdo |
   |---|---|
   | `FEEDZ_STATE_JSON` | conteúdo de `~/.config/devoz/feedz_state.json` (após `feedz_export.py login`) |
   | `GDRIVE_SA_JSON` | conteúdo do JSON da service account |
   | `ONDE_ESTAMOS_DRIVE_FILE_ID` | ID do arquivo do passo 1 |
6. **Teste:** Actions › `onde-estamos` › Run workflow com `dry_run` (gera o HTML como
   artifact, sem publicar). Depois rode sem dry-run e confira o site.

## Detalhes que importam

- **Privacidade:** o `.xlsx` do Feedz tem CPF, banco etc. O pipeline lê **só** nome, e-mail,
  cidade/UF, Time (Departamento) e Grupo. O HTML gerado só contém **nome + cidade + time/grupo**.
  **Não** versione o `.xlsx` nem o `onde_estamos.html` no git (já estão no `.gitignore`).
  O xlsx nunca vira artifact no Actions. O arquivo do Drive e o Web App ficam restritos
  ao domínio — não deixe públicos.
- **Sessão do Feedz no CI:** vive no cache do Actions (`feedz_state.json`) e é re-salva a
  cada run com os cookies rotacionados — rodando diário, ela se mantém viva sozinha. O
  secret `FEEDZ_STATE_JSON` é só a semente/fallback (não precisa ficar atualizando).
- **Quem mora fora do Brasil:** o Feedz só tem Município/UF para o Brasil. Para o time LatAm,
  People preenche o campo **Endereço** no Feedz terminando com **`..., Cidade, País`**
  (ex.: `Av. Corrientes 1234, Buenos Aires, Argentina`) — ver Jira **IFD-33**. O script pega
  as duas últimas partes (cidade, país). Coordenadas de cidades fora do BR ficam em
  `scripts/data/cidades_extra.csv`.
- **"Cidade pendente":** quem está ativo mas sem município no Feedz aparece listado no rodapé
  do mapa (não some). Some sozinho quando o endereço for preenchido no Feedz.
- **Atualização manual (fallback):** o caminho antigo continua funcionando —
  `python3 scripts/mapa_interativo.py <export.xlsx>` e colar o HTML no bloco
  Incorporar › Código do Sites. Só faz sentido se o pipeline estiver quebrado.

## Peças

| O quê | Onde |
|---|---|
| Workflow diário | `.github/workflows/onde-estamos.yml` |
| Download do Feedz (sessão salva) | `scripts/feedz_export.py` |
| Gerador do mapa | `scripts/mapa_interativo.py` |
| Publicação no Drive | `scripts/drive_publish.py` |
| Web App (serve o HTML do Drive) | `scripts/onde_estamos_webapp.gs` |
| Coordenadas BR (IBGE) | `scripts/data/cidades_br.csv` |
| Coordenadas fora do BR | `scripts/data/cidades_extra.csv` |
| Exceções por pessoa | `scripts/map_overrides.json` |
| Site publicado | Google Sites (link na intranet) |
