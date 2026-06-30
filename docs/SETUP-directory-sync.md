# Setup — workspace-directory-sync

Provisionamento único (IT/Admin). Depois disso, roda sozinho todo dia.

## 1. Service account do Google (para ler o Admin Directory)
1. Google Cloud Console → crie um projeto (ou use um existente) → **Service Accounts** → criar.
2. Gere uma **chave JSON** para essa service account.
3. Ative a **Admin SDK API** no projeto.
4. **Domain-wide delegation:** Admin Console (admin.google.com) → Segurança → Controles de API
   → Delegação em todo o domínio → adicionar o **Client ID** da service account com o escopo:
   `https://www.googleapis.com/auth/admin.directory.user.readonly`
5. Escolha um **e-mail de admin** que a service account vai personificar (ex.: um admin do Workspace).

## 2. Token do Confluence
- Atlassian → Perfil → Segurança → **Criar token de API**.
- Anote o e-mail da conta e o token.

## 3. Secrets no GitHub (repo devoz-automations → Settings → Secrets and variables → Actions)
| Secret | Valor |
|---|---|
| `GOOGLE_SA_JSON` | conteúdo completo do JSON da service account |
| `GOOGLE_ADMIN_EMAIL` | e-mail de admin a personificar |
| `CONFLUENCE_BASE_URL` | `https://ozmap.atlassian.net/wiki` |
| `CONFLUENCE_EMAIL` | e-mail da conta Atlassian |
| `CONFLUENCE_API_TOKEN` | token criado no passo 2 |
| `CONFLUENCE_PAGE_ID` | `2246836238` (página Diretório) |

## 4. Testar
- Actions → directory-sync → **Run workflow** com **dry_run = true** (só simula).
- Confira o log; se estiver ok, rode sem dry-run (ou espere o agendamento).

## Segurança
Nenhum desses valores vai pro código — só nos secrets do GitHub. A service account é
**somente leitura** do diretório (`directory.user.readonly`).
