# Como atualizar o mapa "Onde estamos"

Mapa interativo com a cidade onde cada pessoa do time mora, publicado como um site
interno no **Google Sites** (restrito ao domínio `ozmap.com`). Endereço muda pouco,
então atualizar **uma vez por mês** (ou quando entra/sai gente) já basta.

> Por enquanto a atualização é **manual** (3 passos, ~5 min). A automação diária fica
> para depois — o login do Feedz tem reCAPTCHA, que impede baixar o export sozinho.

---

## Atualizar (rotina, ~5 min)

### 1. Baixar o export do Feedz
No Feedz: **Pessoas › Relatórios › Pré-definidos › Colaboradores › Exportar**.
Salva o arquivo `.xlsx` (ex.: em `~/Downloads`). É o export que traz "Residência - Município/UF".

### 2. Gerar o HTML
No terminal, dentro da pasta do projeto (na 1ª vez, instale a dependência: `pip3 install openpyxl`):

```bash
cd "/Users/kautzmann/Claude/Projects/iafirstitizacao devoz/devoz-automations"
python3 scripts/mapa_interativo.py ~/Downloads/colaboradores.xlsx
```

Isso gera **`onde_estamos.html`** na pasta atual e imprime um resumo
(quantos ativos, cidades, e quem está "sem cidade"). Se não passar o caminho, ele
pega o `.xlsx` mais recente da pasta.

### 3. Colar no Google Sites
1. Abra o `onde_estamos.html` num editor de texto e **copie tudo** (Cmd+A, Cmd+C).
2. No Google Sites, edite a página do mapa → clique no bloco **Incorporar** existente
   → **Código** → apague o antigo → **cole** o novo → **Inserir**.
3. **Publicar** (canto superior direito).

Pronto. Confere no site publicado.

---

## Primeira vez: criar o site (só uma vez)

1. Em [sites.google.com](https://sites.google.com/new), crie um site novo (ex.: "Onde estamos — DevOZ").
2. **Inserir › Incorporar › Código** → cole o conteúdo do `onde_estamos.html` → **Inserir**.
   (Dica: dá pra usar **Páginas › Incorporação de página inteira** pro mapa ocupar a tela toda.)
3. **Publicar** → em "Quem pode ver", restrinja a **DevOZ / `ozmap.com`** (não deixar público).
4. Copie o link publicado e coloque na página da intranet ("Onde estamos" no Confluence)
   como um botão/link **"Abrir mapa"**.

---

## Detalhes que importam

- **Privacidade:** o `.xlsx` do Feedz tem CPF, banco etc. O script lê **só** nome, e-mail,
  cidade/UF, Time (Departamento) e Grupo. O HTML gerado só contém **nome + cidade + time/grupo**.
  **Não** versione o `.xlsx` nem o `onde_estamos.html` no git (já estão no `.gitignore`).
- **Quem mora fora do Brasil:** o Feedz só tem Município/UF para o Brasil. Para o time LatAm,
  People preenche o campo **Endereço** no Feedz terminando com **`..., Cidade, País`**
  (ex.: `Av. Corrientes 1234, Buenos Aires, Argentina`) — ver Jira **IFD-33**. O script pega
  as duas últimas partes (cidade, país). Coordenadas de cidades fora do BR ficam em
  `scripts/data/cidades_extra.csv` (edite se aparecer uma cidade nova sem ponto no mapa).
- **"Cidade pendente":** quem está ativo mas sem município no Feedz aparece listado no rodapé
  do mapa (não some). Some sozinho quando o endereço for preenchido no Feedz.
- **Cidade sem coordenada:** se o script avisar "sem coordenada p/ X", adicione a linha em
  `scripts/data/cidades_extra.csv` (`nome,pais,lat,lon`) e rode de novo.

## Peças

| O quê | Onde |
|---|---|
| Gerador do mapa | `scripts/mapa_interativo.py` |
| Coordenadas BR (IBGE) | `scripts/data/cidades_br.csv` |
| Coordenadas fora do BR | `scripts/data/cidades_extra.csv` |
| Exceções por pessoa | `scripts/map_overrides.json` |
| Site publicado | Google Sites (link na intranet) |
