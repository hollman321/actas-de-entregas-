import os
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")
USERNAME = os.getenv("E2E_USERNAME")
PASSWORD = os.getenv("E2E_PASSWORD")
if not USERNAME or not PASSWORD:
    raise SystemExit("Define E2E_USERNAME y E2E_PASSWORD para ejecutar el smoke visual; no se usan credenciales por defecto.")
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(os.getenv("E2E_OUTPUT_DIR", str(ROOT / "artifacts" / "playwright")))
OUTPUT.mkdir(parents=True, exist_ok=True)

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1000},
    "tablet": {"width": 834, "height": 1112},
    "mobile": {"width": 390, "height": 844},
}


def check_no_horizontal_overflow(page):
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def run():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for name, viewport in VIEWPORTS.items():
            context = browser.new_context(viewport=viewport, device_scale_factor=1)
            page = context.new_page()
            page_errors = []
            failed_requests = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on("requestfailed", lambda request: failed_requests.append(f"{request.method} {request.url}: {request.failure}"))
            page.goto(f"{BASE_URL}/login/", wait_until="networkidle")
            page.screenshot(path=OUTPUT / f"{name}-login.png", full_page=True)
            page.fill("#id_username", USERNAME)
            page.fill("#id_password", PASSWORD)
            page.click("button[type=submit]")
            page.wait_for_url("**/accounts/dashboard/")
            page.screenshot(path=OUTPUT / f"{name}-dashboard.png", full_page=True)

            page.goto(f"{BASE_URL}/actas/", wait_until="networkidle")
            page.screenshot(path=OUTPUT / f"{name}-actas.png", full_page=True)
            assert check_no_horizontal_overflow(page), f"Overflow horizontal en listado {name}"

            page.goto(f"{BASE_URL}/actas/new/", wait_until="networkidle")
            page.screenshot(path=OUTPUT / f"{name}-form.png", full_page=True)
            assert check_no_horizontal_overflow(page), f"Overflow horizontal en formulario {name}"

            mock_case = os.getenv("E2E_GLPI_CASE")
            if mock_case:
                page.locator("[data-case-number]").fill(mock_case)
                page.on("dialog", lambda dialog: dialog.accept())
                with page.expect_response(lambda response: "/actas/glpi/autocomplete/" in response.url):
                    page.click("#glpiButton")
                assert page.locator('[data-autocomplete-field="Nombre completo"]').input_value(), "GLPI no completó el nombre"
                assert page.locator('[data-autocomplete-field="Diadema"]').is_checked(), "GLPI no completó el periférico Diadema"

            sign_acta = os.getenv("E2E_SIGN_ACTA")
            if sign_acta:
                page.goto(f"{BASE_URL}/actas/{sign_acta}/sign/", wait_until="networkidle")
                page.screenshot(path=OUTPUT / f"{name}-sign.png", full_page=True)
                assert page.locator("canvas, #signaturePad").count() == 0, f"La firma no debe dibujarse en {name}"
                assert page.locator("img").count() > 0 or page.locator("a[href*='supervisor-signature']").count() > 0, f"No se muestra firma PNG ni enlace para registrarla en {name}"
                assert check_no_horizontal_overflow(page), f"Overflow horizontal en firma {name}"

            page.goto(f"{BASE_URL}/accounts/notifications/", wait_until="networkidle")
            page.screenshot(path=OUTPUT / f"{name}-notifications.png", full_page=True)
            assert check_no_horizontal_overflow(page), f"Overflow horizontal en notificaciones {name}"
            page.goto(f"{BASE_URL}/accounts/reports/", wait_until="networkidle")
            assert page.locator("h2").filter(has_text="Reportes de actas").count() == 1, "No se mostró la página de reportes"
            assert check_no_horizontal_overflow(page), f"Overflow horizontal en reportes {name}"
            assert not page_errors, f"Errores JavaScript en {name}: {page_errors}"
            assert not failed_requests, f"Solicitudes fallidas en {name}: {failed_requests}"
            context.close()
        browser.close()
    print(f"Screenshots saved in {OUTPUT}")


if __name__ == "__main__":
    run()
