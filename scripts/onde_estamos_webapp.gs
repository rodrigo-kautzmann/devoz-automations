/**
 * Web App "Onde estamos" — serve o onde_estamos.html direto do Drive.
 *
 * Por quê: o Google Sites não tem API. Este Web App é a URL que o Sites embute
 * (Inserir › Incorporar › Por URL). Como o doGet lê o arquivo do Drive A CADA
 * acesso, atualizar o mapa = sobrescrever o arquivo (scripts/drive_publish.py).
 * Nunca mais se edita o Sites nem se redeploya este script.
 *
 * ── Setup (1x, ~5 min) ────────────────────────────────────────────────────
 * 1. Suba um onde_estamos.html qualquer para o seu Drive e copie o ID do
 *    arquivo (na URL: /d/<ID>/view). Cole em FILE_ID abaixo.
 * 2. Compartilhe esse arquivo com o e-mail da service account (Editor).
 * 3. Em script.google.com › Novo projeto, cole este código.
 * 4. Implantar › Nova implantação › Web App:
 *      - Executar como: VOCÊ (rodrigo.kautzmann@ozmap.com)
 *      - Quem pode acessar: "Qualquer pessoa em ozmap.com"
 * 5. Copie a URL /exec e, no Google Sites, troque o bloco "Incorporar > Código"
 *    por "Incorporar > Por URL" com essa URL. Publique o Sites (última vez!).
 *
 * Obs.: implantação fixa (/exec) serve sempre a versão implantada DO CÓDIGO,
 * mas o CONTEÚDO vem do Drive na hora — por isso não precisa redeploy.
 */

var FILE_ID = '13vv5tq_wDdXwBYyvnuIGR9-vLoNpUHJ7';

function doGet() {
  var html = DriveApp.getFileById(FILE_ID).getBlob().getDataAsString('UTF-8');
  return HtmlService.createHtmlOutput(html)
    .setTitle('Onde estamos — DevOZ')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL); // permite embed no Sites
}
