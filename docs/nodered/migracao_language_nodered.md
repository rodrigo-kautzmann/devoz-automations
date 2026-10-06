# Migração Language: Deal.Linguagem → Account.Language (Node-RED)

Decisão: **`Deal.Linguagem` será removido — SEM fallback.** Language passa a viver só no Account.

## Contexto (já feito)
- Criado `Language` (picklist pt_BR/es/en) no **Account**; dados migrados de `Deal.Linguagem`.
- Conexão Zoho do Node-RED com escopo **COQL** (validado: `Account_Name.Language` retorna via COQL).

## ⚠️ Pré-requisito antes de remover o Deal.Linguagem
Como não haverá fallback, todo Account de deal ativo precisa ter `Language`. Checar cobertura:
- COQL: `select id, ozid, Account_Name.Language from Deals where ozid is not null` → conferir que `Account_Name.Language` não vem nulo. Preencher os que faltarem antes de seguir.

## Os 3 pontos
| Nó | Flow | Papel |
|---|---|---|
| `buildZohoUsers` | OZmachine Sync (CRM) | LÊ — origem do `crm.language` do pipeline (⭐) |
| `function 9` | Produção (CRM) | LÊ — lançamento manual |
| `setDealInfos` | Superlógica→Zoho (CRM) | ESCREVE — autocompra (conversão de lead) |

Restrição: `buildZohoUsers`/`function 9` usam `Owner.email`, que o COQL não retorna → não converter o fetch principal pra COQL; trazer o Language do Account por caminho paralelo.

---

## 1) setDealInfos (ESCRITA) → gravar Language SÓ no Account  ✅ FEITO (2026-07-26)

Tab **"Superlógica -> Zoho"** (`d21beb1b35ad3cd9`). Há **2** nós `setDealInfos`:
- `c61626029c1c9dd3` → alimenta **`Zoho | convertLead`** (cliente NOVO / autocompra).
- `205f011efae97567` → alimenta **`Zoho | patchDealsField`** (sync recorrente de deal existente).

Em **ambos** removi a linha `"Linguagem": msg.infos.linguagem,` do `dealInfos` (para de escrever no campo que vai morrer).

**Só no caminho do convert** (cliente novo) gravamos o idioma na Account criada:
- Id da Account vem da resposta do convert em `msg.payload.data[0].details.Accounts.id`
  (o fluxo já usa `.details.Deals.id` para o `dealId`).
- Ligado na **saída 1 (sucesso)** do convert: `convert:1 → prepAcctLang → [Zoho | setAccountLanguage]`.
  - `prepAcctLang`: `msg.accountId = ...details.Accounts.id; msg.lang = msg.infos.linguagem || "en"`.
  - Subflow **`Zoho | setAccountLanguage`** (`sf_setacctlang`): `getAuthorization → buildPut → http request PUT`
    `PUT /crm/v2/Accounts/{id} {data:[{Language}]}`, default **en**, com guard (pula se sem accountId).

**Caminho do patch recorrente (205):** apenas removida a linha `Linguagem`. NÃO re-sincroniza idioma
na Account a cada rodada (idioma praticamente não muda; re-sync exigiria lookup de conta por execução).
Se algum dia precisar, reusar `setAccountLanguage` resolvendo o accountId por ozid.

Validado em produção: PUT idempotente numa conta pt_BR → `Modified_Time` atualizado, `Language` pt_BR, resposta `data[1]`.

---

## 2) buildZohoUsers (LEITURA) → lookup pontual por ozid  ✅ FEITO (2026-07-26)

**Decisão de arquitetura:** o fluxo OZmachine Sync roda **1 vez por cliente** (fechamento/demo),
processando **1 deal por execução**. Portanto NADA de scan paginado / `langMap` de todos os ozids
(seria overkill). Basta **1 COQL** buscando o idioma da conta daquele ozid.

Empacotado como subflow reutilizável **`Zoho | getAccountLanguage`** (id `sf_getacctlang`):
```
[in] → getAuthorization → coqlByOzid → http request (COQL) → extractLang → [out]
```
- `coqlByOzid`: `select ozid, Account_Name.Language from Deals where ozid = '<ozid>' limit 1`
  (lê ozid de `msg.deal[0].ozid` ou `msg.ozid`).
- `extractLang`: `msg.acctLang = <lang> || "en"` (default **en** se a conta não tiver Language)
  e restaura `msg.payload = msg.deal`.

**Nos DOIS caminhos** (demo `da866f6b84d72ba7` e fechado `d94c35e925d32d49`), antes do buildZohoUsers:
```
getAllDeals(saída 1) → change "stashDeal" (msg.deal = msg.payload) → [Zoho | getAccountLanguage] → buildZohoUsers
```
E no `buildZohoUsers` a linha virou:
```js
language: msg.acctLang,
```
Validado em produção: ozid de teste → `acctLang: "pt_BR"` (statusCode 200). Deploy OK.
Node do runtime é v16 (sem `fetch` global) → o lookup usa nó `http request`, não fetch inline.

---

## 3) function 9 (LEITURA, lançamento manual) → enriquecer com o Account
Inserir 5 nós ENTRE o nó que entrega o deal e a `function 9`:

1. **change "stash deal"**: set `msg.launchDeal` = (msg) `payload`.
2. **subflow `Zoho | getAuthorization`**.
3. **function "prep account req"**:
```js
msg.payload = { accountId: msg.launchDeal.Account_Name.id, authorization: msg.payload.authorization };
return msg;
```
4. **subflow `Zoho | getAccountInfos`** (payload vira a Account, com `Language`).
5. **function "merge language"** (sem fallback):
```js
const deal = msg.launchDeal;
deal.Account_Language = msg.payload && msg.payload.Language;
msg.payload = deal;
return msg;
```
6. Na `function 9`, trocar a linha:
```js
"language": msg.payload.Account_Language,
```

---

## Ordem
1. Checar cobertura de `Account.Language` (pré-requisito acima) e preencher lacunas.
2. buildZohoUsers (origem do pipeline).
3. function 9 (manual).
4. setDealInfos (escrita só no Account).
5. Validar cada um (launch manual, sync, autocompra) com o idioma vindo do Account.
6. **Aposentar `Deal.Linguagem`** (agora sem uso).

Sem fallback: a cobertura de `Account.Language` (passo 1) é o que garante que nada vá com idioma vazio.
