#!/usr/bin/env python3
"""Publica o onde_estamos.html no Google Drive (sobrescreve SEMPRE o mesmo arquivo).

Por quê: o Google Sites não tem API de conteúdo. Em vez de colar o HTML no bloco
"Incorporar > Código", o Sites embute POR URL um Web App do Apps Script
(scripts/onde_estamos_webapp.gs) que serve o conteúdo deste arquivo do Drive.
Logo, atualizar o mapa == sobrescrever este arquivo. Nada de redeploy, nada de
editar o Sites.

Autenticação: service account (JSON) com o arquivo do Drive compartilhado com
ela como Editor. O arquivo continua sendo do Rodrigo — a SA só escreve nele.

Env:
    GDRIVE_SA_JSON   conteúdo do JSON da service account (secret no Actions)
                     ou caminho para o arquivo .json (uso local)
    DRIVE_FILE_ID    ID do arquivo onde_estamos.html no Drive

Uso:
    python3 scripts/drive_publish.py [caminho/do/onde_estamos.html]
    # sem argumento: usa ./onde_estamos.html
"""
import json
import os
import sys

SCOPES = ["https://www.googleapis.com/auth/drive"]


def _credentials():
    raw = os.environ.get("GDRIVE_SA_JSON", "").strip()
    if not raw:
        raise SystemExit("Defina GDRIVE_SA_JSON (conteúdo do JSON da service account, ou caminho).")
    from google.oauth2 import service_account
    if raw.startswith("{"):
        info = json.loads(raw)
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return service_account.Credentials.from_service_account_file(raw, scopes=SCOPES)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "onde_estamos.html"
    file_id = os.environ.get("DRIVE_FILE_ID", "").strip()
    if not file_id:
        raise SystemExit("Defina DRIVE_FILE_ID (ID do arquivo no Drive).")
    if not os.path.exists(path):
        raise SystemExit(f"Arquivo não encontrado: {path} — rode antes o mapa_interativo.py")
    size = os.path.getsize(path)
    if size < 5_000:  # o HTML real tem >10 KB; algo bem menor = geração falhou
        raise SystemExit(f"{path} tem só {size} bytes — parece quebrado; abortando publicação.")

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    svc = build("drive", "v3", credentials=_credentials(), cache_discovery=False)
    media = MediaFileUpload(path, mimetype="text/html", resumable=False)
    meta = svc.files().update(
        fileId=file_id, media_body=media, supportsAllDrives=True,
        fields="id,name,modifiedTime").execute()
    print(f"OK: publicado no Drive — {meta['name']} ({meta['id']}) @ {meta['modifiedTime']}")


if __name__ == "__main__":
    main()
