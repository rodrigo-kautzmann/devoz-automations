# Node-RED — mapa dos flows

Gerado por `scripts/nodered_indice.py` a partir dos exports sanitizados desta pasta
(`scripts/nodered_sanitiza.py` remove credenciais e dados de teste; ids e ligações
ficam intactos). Para atualizar: exporte os flows do Node-RED, rode o sanitiza em
cada um, confira, e rode este script.

## admin

### Backup NodeRed  (114 nós)
- **Expõe:** `GET /api/v1/healthcheck`
- **Subflows:** NodeRed | healthcheck V2 ×9, Devops | restartProxy ×4, Node-Red | S3 Backup Routine ×1, manager | healthcheck ×1, validFields ×1, vault | checkAuthorization ×1

### Machine Control  (446 nós)
- **Expõe:** `GET /api/v1/churn`, `GET /api/v1/demo/churn`, `GET /api/v1/demo/churn_start`, `PATCH /api/v1/zoho/deal/stage`, `POST /api/v1/newclient`, `POST /api/v1/newdemo`, `POST /api/v1/ozmap/backups/delete`, `POST /api/v1/ozmap/backups/restore`, `POST /api/v1/ozmap/users/user`
- **Chama:** (url dinâmica, via msg.url), nodered.ozmap.com.br, ozmachine.ozmap.com.br
- **Subflows:** vault | checkAuthorization ×9, delayMsgByRetry ×7, validFields ×5, OZmachine v2 | getUser(s) ×5, OZmachine | getUser ×4, Zoho| attDemoStatus ×4, Zoho | changeStage ×3, OZmachine | patchField ×3, OZmap | login ×3, vault | vaultGet ×3, registerLogsEndpoints ×2, OZmap | checksDomain ×2, Totango | updateAttributes ×2, Manager | getUser ×1, Manager | updateUser ×1, Manager | createInactiveUser ×1, Zoho | setOzid ×1, Totango | touchpointChurn ×1, Zoho | getUserInfos ×1, OZmap | restoreDump ×1, setLimitRequests ×1, OZmap | createUserAdmin ×1, Zoho | updateField ×1, OZmap | getDumps ×1, OZmap | deleteDump ×1

### Att Activitys  (22 nós)
- **Subflows:** Manager | getUser(s) ×1, Zoho | updateField ×1

### Reports Admin  (74 nós)
- **Subflows:** Machine DB | getPlans ×3, OZmachine v2 | getUser(s) ×3

### Mautic Integrations  (97 nós)
- **Expõe:** `POST api/v1/mautic/webhook/form-submit/createlead`
- **Chama:** (url dinâmica, via msg.url), authentication.ozmap.com.br, mautic.ozmap.com, nr-admin.ozmap.com.br, ozmap.com.br
- **Subflows:** Mautic | getToken ×2, Mautic | getContactByEmail ×1, Zoho | createLeadFromMautic ×1, Zoho | getLeadInfos ×1, Zoho | addContactNotesV2 ×1, Zoho | addMauticTags ×1, Zoho | searchContactV2 ×1, Mautic | getCompanyByName ×1, vault | checkAuthorization ×1

### Produção  (34 nós)
- **Subflows:** Manager | getUser(s) ×1, Manager | updateUser ×1, Totango | updateAttributes ×1, vault | vaultGet ×1, OZmap | login ×1, OZmap | getDumps ×1

### UNIQ  (51 nós)
- **Expõe:** `POST /api/v1/UNIQ/teste-event-de-chamada`, `POST /api/v1/UNIQ/teste-registro-de-chamada`, `POST /api/v2/uniq/call-event`, `POST /open/uniq/newcall`, `POST call-event`
- **Chama:** (url dinâmica, via msg.url), api.uniq.app
- **Subflows:** checkAuthorization ×1

### Messagebird  (31 nós)
- **Expõe:** `POST /api/v1/chat/ticket`, `POST /api/v1/messagebird-notification`
- **Subflows:** vault | checkAuthorization ×1

### Dump Raupp  (24 nós)
- **Expõe:** `GET /api/open/v1/xerocallback`, `GET /api/v1/ozmap/users/user`, `GET /v1/ec2/machineup`, `POST /api/open/v1/xerocallback`, `POST /api/open/v1/xerowebhook`

### Alares adição em grupos  (180 nós)
- **Expõe:** `GET /api/v1/list-projects/update`, `GET /api/v1/list-users/update`, `GET /api/v1/users/update`
- **Chama:** (url dinâmica, via msg.url)
- **Subflows:** validFields ×7

### RD-Mautic (Importação)  (144 nós)
- **Chama:** (url dinâmica, via msg.url), mautic.ozmap.com
- **Subflows:** Mautic | getToken ×5, Mautic | getContactByEmail ×2, Mautic | createCompany ×1, Mautic | createContact ×1, validFields ×1, Mautic | addContactToStage ×1, Mautic | getCompanyByName ×1, Mautic | addContactToCompany ×1

### Flow 1  (25 nós)
- **Chama:** (url dinâmica, via msg.url)
- **Subflows:** OZmachine v2 | getUser(s) ×1

## crm

### Endpoints Deal  (148 nós)
- **Expõe:** `GET /api/v1/deal/account/infos/:accountId`, `GET /api/v1/deal/accounts/infos`, `GET /api/v1/deal/attactivity`, `GET /api/v1/deal/infos/:userId`, `GET /api/v1/deal/searchdeal`, `PATCH /api/v1/deal/attdemostatus`, `PATCH /api/v1/deal/changestage`, `PATCH /api/v1/deal/patchfield`, `POST /api/v1/deal/attdebug`, `POST /api/v1/demo/overdue/update`, `PUT /api/v1/deal/setozid`
- **Subflows:** vault | checkAuthorization ×10, getReqRes ×9, registerLogsEndpoints ×9, saveReqRes ×7, validFields ×7, Zoho | getUserInfos ×1, Zoho | changeStage ×1, Zoho | patchField ×1, Zoho | attDemoStatus ×1, Zoho | getAccountInfos ×1, Zoho | setOzid ×1, Zoho | getAllDeals ×1, Zoho | attDemoDebug ×1, Zoho | attActivity ×1, Zoho | getDealByEmail ×1, checkAuthorization ×1, OZmachine | updateOverDueAndLock/Unlock ×1, OZmachine v2 | getUser(s) ×1, vault | vaultGet ×1

### Endpoints Lead  (131 nós)
- **Expõe:** `GET /api/v1/contact/:email`, `GET /api/v1/lead/infos/:leadEmail`, `GET /api/v1/lead/searchcontact/:email`, `GET /api/v1/lead/searchlead`, `GET /api/v1/lead/transition/:leadId`, `POST /api/v1/contact/addcontactnote`, `POST /api/v1/contact/addtag`, `POST /api/v1/lead/createLead`, `POST /api/v1/lead/editleadsource`, `POST /api/v1/lead/transition`, `PUT /api/v1/lead/addtag`
- **Subflows:** vault | checkAuthorization ×11, validFields ×10, registerLogsEndpoints ×9, getReqRes ×8, saveReqRes ×4, Zoho | getLeadInfosByEmail ×1, Zoho | addLeadTags ×1, Zoho | createLead ×1, Zoho | addZohoContactNotes ×1, Zoho | searchContactByEmail ×1, Zoho | addTagZohoContact ×1, Zoho | getContactByEmail ×1, Zoho | editLeadSourceByEmail ×1, Zoho | getLeadByEmail ×1, Zoho | getLeadTransitionId ×1, Zoho | patchLeadStage ×1

### Endpoints SERPRO  (20 nós)
- **Expõe:** `GET /api/v1/consulta-cnpj/basico`, `GET /api/v1/consulta-cnpj/qsa`
- **Subflows:** validFields ×2, vault | checkAuthorization ×2, SERPRO | consultaBasicaCNPJ ×1, SERPRO | consultaQSACNPJ ×1

### Mautic Integration  (166 nós)
- **Expõe:** `POST /api/v1/mautic/zoho_callback`
- **Subflows:** Mautic | getToken ×4, Mautic | getContactByEmail ×3, Mautic | editContactById ×2, OZmachine v2 | getUser(s) ×2, Mautic | createCompany ×1, Mautic | createContact ×1, Mautic | addContactToCompany ×1, Mautic | getCompanyByName ×1, validFields ×1, Mautic | addContactToStage ×1, Zoho | changeStage ×1, Manager | updateUser ×1, OZmachine | getUser(s) ×1, NR DevOps | updateVariablesAndDeploy ×1, vault | vaultGet ×1, checkAuthorization ×1, NR DevOps | unlockPortal ×1

### OZmachine Sync  (124 nós)
- **Subflows:** OZmachine | patchField v2 ×5, OZmachine v2 | getUser(s) ×4, Zoho | getAllDeals ×2, Zoho | getAllDemoDeals ×1, Zoho | getAllDealsByCriteria ×1, Zoho | getAllDealsWithDistribuidor ×1, Zoho | getAllDealsInMasterAgreement ×1, OZmachine | updateOverDueAndLock/Unlock ×1

### Backup NodeRed  (17 nós)
- **Expõe:** `GET /api/v1/healthcheck`
- **Subflows:** Node-Red | S3 Backup Routine ×1, validFields ×1, vault | checkAuthorization ×1

### Produção  (345 nós)
- **Expõe:** `GET /api/v1/teste`, `GET /api/v1/zoho/code`, `GET /test-report/error`, `POST /api/v1/zoho/webhook/corporative`
- **Chama:** (url dinâmica, via msg.url), accounts.zoho.com, crm.zoho.com, marketingautomation.zoho.com, nr-erp.ozmap.com.br, sandbox.clicksign.com, www.zohoapis.com
- **Subflows:** Zoho | getAuthorization ×14, Zoho | getUserInfos ×4, Zoho | getTransitionId ×2, validFields ×2, Zoho | getAccountInfos ×2, OZmachine v2 | getUser(s) ×2, Zoho | setOzid ×1, Zoho | changeStage ×1, Zoho | patchField ×1, Zoho Accounts | patchField ×1, Zoho | getAllDemoDeals ×1, Zoho | getAllDeals ×1, Zoho | getDealInfos ×1, Zoho | getLeadInfosByEmail ×1, Zoho | patchStage ×1

### Contratos  (21 nós)
- **Expõe:** `POST /api/v1/contract/create`
- **Subflows:** checkAuthorization ×1

### Superlógica -> Zoho  (94 nós)
- **Expõe:** `POST /api/v1/deal/create-from-superlogica`
- **Subflows:** Zoho | patchStage ×2, Zoho | patchDealsField ×2, Zoho | getDealByEmail ×1, Zoho | getLeadByEmail ×1, Zoho | createLead ×1, Zoho | addLeadTags ×1, Zoho | convertLead ×1, validFields ×1, checkAuthorization ×1

### Relatórios  (43 nós)
- **Subflows:** Zoho | getAllDealsByCriteria ×2, OZmachine v2 | getUser(s) ×2

## csm

### Backup NodeRed  (33 nós)
- **Expõe:** `GET /api/v1/healthcheck`, `GET /test-report/error`
- **Subflows:** validFields ×2, Node-Red | S3 Backup Routine ×1, vault | checkAuthorization ×1, OZmachine v2 | getUser(s) ×1

### Totango Sync  (485 nós)
- **Chama:** (url dinâmica, via msg.url), devoz.freshdesk.com
- **Subflows:** Totango | updateAttribute ×17, OZmachine v3 | getUser(s) ×17, Totango | getAccountsDetailsV3 ×11, Freshdesk | getTicketsByQuery ×5, Zoho | getUserInfos ×2, Totango | createAccount ×1, Totango | createContact ×1, Machine DB | getPlans ×1, Manager | getUser(s) ×1, Freshdesk | getTickets ×1, OZmap | login ×1, Totango | getAccountContractValues ×1, Totango | getAccountsTicketDetails ×1, OZmachine v2 | getUser(s) ×1

### Freshdesk Sync  (52 nós)
- **Chama:** (url dinâmica, via msg.url), devoz.freshdesk.com
- **Subflows:** Freshdesk | getAllCompanies ×1, Freshdesk | createCompany ×1, Freshdesk | createContact ×1, OZmachine | getUser(s) ×1, Zoho | getUserInfos ×1

### OZmachine Sync  (108 nós)
- **Subflows:** OZmachine | patchField ×5, OZmachine v2 | getUser(s) ×5, Totango | getClientsByTag ×3, Totango | getAccountsDetailsV3 ×2, Totango | getAccountsDetailsV2 ×1, Totango | getStages ×1

### (bkp)Produção  (194 nós)
- **Chama:** (url dinâmica, via msg.url), devoz.freshdesk.com, discord.com, ozmap.atlassian.net, sitename.atlassian.net
- **Subflows:** Freshdesk | getTicketsByQuery ×8, Totango | getAccountsDetailsV2 ×2, OZmachine v2 | getUser(s) ×1, Totango | getAccountsTicketDetails ×1

### Produção  (286 nós)
- **Expõe:** `GET /api/v1/totango/ozmap/callback`, `GET /api/v1/totango/ozneutral/callback`, `POST /api/v1/totango/ozmap/callback`, `POST /api/v1/totango/ozneutral/callback`
- **Chama:** (url dinâmica, via msg.url), amplitude.com, api-gw-us.totango.com, api.lab.amplitude.com, api2.amplitude.com, app.amplitude.com, devoz.freshdesk.com, nr-csm.ozmap.com.br, ozmap.atlassian.net
- **Subflows:** OZmachine v2 | getUser(s) ×9, OZmachine | getAdditionalService(s) ×2, Totango OZmap | getAuthorization ×1, Totango OZneutral | getAuthorization ×1, Totango | updateAttribute ×1, Freshdesk | getTicketsByQuery ×1

### Endpoints  (62 nós)
- **Expõe:** `GET /api/v1/totango/accounts`, `GET /api/v1/totango/contacts/active_users`, `GET /api/v1/totango/stages`, `GET /api/v1/totango/stages/:stage`, `PATCH /api/v1/totango/account/attribute`, `POST /api/v1/totango/touchpoint`
- **Subflows:** vault | checkAuthorization ×6, validFields ×4, Totango | getStages ×3, Totango | getAccountsDetails ×1, Totango | updateAttribute ×1, Totango | createTouchpoint ×1, Totango | getAccountsActiveUsers ×1

### FreshDesk Automation  (313 nós)
- **Expõe:** `POST /api/v1/freshdesk/webhook/automacao`, `POST /api/v1/freshdesk/webhook/engenharia`, `POST /api/v1/report`, `POST /api/v2/report`, `POST /api/v3/report`, `POST /api/v4/report`
- **Chama:** (url dinâmica, via msg.url), discord.com, ozmap.atlassian.net
- **Subflows:** vault | checkAuthorization ×5, checkAuthorization ×1, OZmachine v2 | getUser(s) ×1

### Integração Métricas  (59 nós)
- **Expõe:** `GET /api/v1/integration/metrics/error`
- **Chama:** (url dinâmica, via msg.url), devoz.freshdesk.com
- **Subflows:** OZmachine v2 | getUser(s) ×3, checkAuthorization ×1

### JetSales  (66 nós)
- **Expõe:** `POST /api/v1/jetsales/ticket/closed`
- **Chama:** chat-33.jetsalesbrasil.com
- **Subflows:** Freshdesk | getContactsByPhone ×1, Freshdesk | searchCompaniesByUserId ×1, Freshdesk | createContactV2 ×1, Freshdesk | createTicket ×1, OZmachine v2 | getUser(s) ×1, Machine DB | getPlansV2 ×1, checkAuthorization ×1

### Relatórios  (35 nós)
- **Chama:** ajuda.ozmap.com.br
- **Subflows:** OZmachine v2 | getUser(s) ×1, Totango | getClientsByTag ×1, Freshdesk | getTicketsByQuery ×1

### Controle de criação de tasks  (30 nós)
- **Expõe:** `GET /api/v1/jirasdkmanagement`, `GET /v1/jirasdkmanagement`, `PATCH /api/v1/jirasdkmanagement`
- **Subflows:** KeycloakAuthorization ×3, validFields ×1

### Totango OZneutral  (46 nós)
- **Chama:** (url dinâmica, via msg.url), api-gw-us.totango.com, authentication.ozneutral.com, int-hub.totango.com, portal.ozneutral.com
- **Subflows:** Totango OZneutral | getAuthorization ×1

### testes Jira  (105 nós)
- **Expõe:** `POST teste-jira-fields`
- **Chama:** (url dinâmica, via msg.url), 5041443d-5f0c-4885-8462-1bdc1303bcc1.hello.atlassian-dev.net, ozmap.atlassian.net
- **Subflows:** OZmachine v1 | get SKUs ×2, OZmachine v2 | getUser(s) ×1, OZmachine | patchField ×1, OZmachine v1 | create SKUs ×1

### Amplitude  (26 nós)
- **Chama:** (url dinâmica, via msg.url), api2.amplitude.com
- **Subflows:** OZmachine | getAdditionalService(s) ×1, OZmachine v2 | getUser(s) ×1

### Report Manager  (148 nós)
- **Expõe:** `POST /api/v5/report/error`, `POST /api/v5/reports/error/resolved`
- **Chama:** (url dinâmica, via msg.url), discord.com, nr-csm.ozmap.com, ozmap.atlassian.net
- **Subflows:** OZmachine v2 | getUser(s) ×1, vault | checkAuthorization ×1
