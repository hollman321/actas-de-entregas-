import json

import requests
from django.conf import settings

from .mock_data import available_mock_cases, get_mock_case


class GlpiClient:
    """Small client for GLPI's legacy REST API (apirest.php)."""

    timeout = (5, 20)

    def __init__(self):
        self.base_url = settings.GLPI_BASE_URL.rstrip("/")
        self.app_token = settings.GLPI_APP_TOKEN
        self.user_token = settings.GLPI_USER_TOKEN

    def _session(self):
        if not self.base_url or not self.user_token:
            raise RuntimeError("La conexión con GLPI no está configurada.")
        session = requests.Session()
        headers = {"Authorization": f"user_token {self.user_token}", "Content-Type": "application/json"}
        if self.app_token:
            headers["App-Token"] = self.app_token
        response = session.get(f"{self.base_url}/initSession", headers=headers, timeout=self.timeout)
        response.raise_for_status()
        session_token = response.json().get("session_token")
        if not session_token:
            raise RuntimeError("GLPI no devolvió un token de sesión.")
        session.headers.update({"Session-Token": session_token, "Content-Type": "application/json"})
        if self.app_token:
            session.headers["App-Token"] = self.app_token
        return session

    def _close(self, session):
        try:
            session.get(f"{self.base_url}/killSession", timeout=self.timeout)
        except requests.RequestException:
            pass
        finally:
            session.close()

    def get_case(self, case_number):
        if settings.GLPI_SIMULATION_MODE:
            case = get_mock_case(case_number)
            if case is None:
                available = ", ".join(available_mock_cases())
                raise LookupError(f"Caso no encontrado en simulación. Casos disponibles: {available}")
            return case

        session = self._session()
        try:
            response = session.get(f"{self.base_url}/Ticket/{case_number}", timeout=self.timeout)
            if response.status_code == 404:
                raise LookupError("Caso GLPI no encontrado.")
            response.raise_for_status()
            ticket = response.json()
            # GLPI's standard Ticket endpoint exposes IDs and ticket metadata. User,
            # asset and site fields vary by installation and must be mapped there.
            return {
                "case_number": str(ticket.get("id", case_number)),
                "user_name": "",
                "document": "",
                "portfolio": "",
                "site": "",
                "act_type": "Entrega",
                "title": ticket.get("name", ""),
                "description": ticket.get("content", ""),
                "equipment": {},
                "peripherals": {},
            }
        finally:
            self._close(session)

    def upload_document(self, case_id, filename, content):
        if settings.IS_TEST_ENVIRONMENT:
            raise RuntimeError("La carga a GLPI está deshabilitada en el ambiente de pruebas.")
        session = self._session()
        try:
            session.headers.pop("Content-Type", None)
            manifest = {"input": {"name": filename, "_filename": [filename]}}
            response = session.post(
                f"{self.base_url}/Document/",
                data={"uploadManifest": json.dumps(manifest)},
                files={"filename[0]": (filename, content, "application/pdf")},
                timeout=self.timeout,
            )
            response.raise_for_status()
            document = response.json()
            document_id = document.get("id")
            if not document_id:
                raise RuntimeError("GLPI no confirmó la creación del documento.")

            session.headers["Content-Type"] = "application/json"
            link_response = session.post(
                f"{self.base_url}/Document_Item/",
                json={"input": {"documents_id": document_id, "itemtype": "Ticket", "items_id": int(case_id)}},
                timeout=self.timeout,
            )
            link_response.raise_for_status()
            return {"document": document, "association": link_response.json()}
        finally:
            self._close(session)
