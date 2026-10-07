import base64
import binascii
import hashlib
import ipaddress
import mimetypes
import logging
from pathlib import Path
from types import SimpleNamespace

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.exceptions import SuspiciousFileOperation
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from django.utils.dateparse import parse_date
from django.utils._os import safe_join
from glpi.client import GlpiClient
from notifications.services import schedule_signature_notification
from accounts.permissions import active_role, get_role_display, get_visible_acta_or_404, visible_actas
from .exporters import render_acta_xlsx, save_final_acta_pdf, upload_final_acta_to_glpi
from .models import Acta, ActaFieldValue, CampaignCatalog, FormFieldDefinition, PortfolioCatalog, Signature, Site
from accounts.models import UserRole, WorkflowConfig


FORM_DEFINITIONS = [
    ("usuario", "Nombre completo", "text", True, []),
    ("usuario", "Cédula", "text", True, []),
    ("sistemas", "Tipo de cuenta", "choice", False, ["Red", "Correo"]),
    ("sistemas", "Usuario de Windows", "text", False, []),
    ("sistemas", "Cuenta de correo", "text", False, []),
    ("sistemas", "Acceso a HelpDesk GLPI", "boolean", False, []),
    ("sistemas", "Novedades AIO", "boolean", False, []),
    ("sistemas", "Impresora", "boolean", False, []),
    ("sistemas", "Control de acceso", "boolean", False, []),
    ("sistemas", "Recurso compartido", "boolean", False, []),
    ("sistemas", "Licencia Office 365", "boolean", False, []),
    ("sistemas", "Extensión", "text", False, []),
    ("sistemas", "Perfil de navegación", "text", False, []),
    ("sistemas", "Power BI", "boolean", False, []),
    ("sistemas", "VPN", "boolean", False, []),
    ("equipo", "Tipo de equipo", "choice", False, ["Desktop", "Portátil"]),
    ("equipo", "Marca", "text", False, []),
    ("equipo", "Modelo", "text", False, []),
    ("equipo", "Serial", "text", False, []),
    ("equipo", "Serial devuelto", "text", False, []),
    ("equipo", "Procesador", "text", False, []),
    ("equipo", "Dirección IP", "text", False, []),
    ("equipo", "Memoria RAM", "text", False, []),
    ("equipo", "Disco duro", "text", False, []),
    ("equipo", "Sistema operativo", "text", False, []),
    ("equipo", "Placa de inventario", "text", False, []),
    ("perifericos", "Diadema", "boolean", False, []),
    ("perifericos", "Teclado", "boolean", False, []),
    ("perifericos", "Mouse", "boolean", False, []),
    ("perifericos", "CPU", "boolean", False, []),
    ("perifericos", "Móvil", "boolean", False, []),
    ("perifericos", "SIM", "boolean", False, []),
    ("perifericos", "Otro", "boolean", False, []),
    ("monitor", "Marca", "text", False, []),
    ("monitor", "Modelo", "text", False, []),
    ("monitor", "Placa de inventario", "text", False, []),
    ("monitor", "Serial", "text", False, []),
    ("observaciones", "Observaciones", "text", False, []),
    ("sistemas", "Acceso a red", "boolean", False, []),
    ("sistemas", "Acceso a correo", "boolean", False, []),
    ("perifericos", "Cual es el otro periferico", "text", False, []),
    ("perifericos", "Marca y modelo", "text", False, []),
    ("perifericos", "Placa de inventario GLPI", "text", False, []),
    ("perifericos", "Serial", "text", False, []),
    ("perifericos", "Serial devuelto", "text", False, []),
]
logger = logging.getLogger(__name__)


def _request_ip(request):
    """Return a validated client IP; only trust forwarded headers when configured."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",", 1)[0].strip()
    candidate = forwarded if settings.USE_X_FORWARDED_HOST and forwarded else request.META.get("REMOTE_ADDR", "")
    try:
        return str(ipaddress.ip_address(candidate)) if candidate else None
    except ValueError:
        return None


LEGAL_CONSENT_FIELDS = (
    "legal_custody_accepted",
    "legal_accuracy_confirmed",
    "legal_data_processing_accepted",
)

ACTA_COMMITMENTS = """Nota: Si es cambio de dispositivo tecnol\u00f3gico, en el campo serial devuelto agregar el serial del activo que entregaron a tecnolog\u00eda; de lo contrario, llenar con NO APLICA (N/A).\nEl usuario se compromete a:\n\u2022 Utilizar el hardware, software y servicios solo para el desempe\u00f1o exclusivo de las funciones definidas para el cargo o actividad encomendada, y en asuntos estrictamente laborales.\n\u2022 No instalar ning\u00fan tipo de software en el equipo entregado, ni crear o utilizar cuentas de correo electr\u00f3nico o mensajer\u00eda instant\u00e1nea personales desde los equipos de propiedad de Synerjoy. No intercambiar partes (monitor, teclado, mouse, CPU y dem\u00e1s) con otros equipos o usuarios.\n\u2022 Manipular la diadema con cuidado, evitando golpes, rayones, presiones, temperaturas excesivas y ambientes contaminados. Mantener l\u00edquidos y sustancias nocivas alejadas de los equipos y evitar subir el volumen al m\u00e1ximo.\n\u2022 El software no permitido o no requerido por el Proceso de Infraestructura Tecnol\u00f3gica y el uso inadecuado del equipo ser\u00e1n responsabilidad del usuario. El trabajador responder\u00e1 ante la empresa por los da\u00f1os ocasionados y autoriza, con su firma, el descuento por n\u00f3mina o liquidaci\u00f3n laboral del valor de los da\u00f1os en caso de siniestro.\nAPLICACI\u00d3N DE CL\u00c1USULA DE CONFIDENCIALIDAD DEL CONTRATO CON SYNERJOY BPO SAS.\n\u2022 En trabajo en casa siguen vigentes las cl\u00e1usulas contractuales, especialmente las obligaciones de reserva y confidencialidad, garantizando el manejo adecuado de los datos conforme a las exigencias de Synerjoy.\n\u2022 El colaborador se obliga a cumplir las pol\u00edticas de seguridad de la informaci\u00f3n."""


def decode_signature_data(signature_data):
    prefix = "data:image/png;base64,"
    if not signature_data.startswith(prefix):
        raise ValueError("La firma debe enviarse como PNG base64.")      
    try:
        payload = base64.b64decode(signature_data[len(prefix):], validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("La imagen de firma no es válida.") from error
    if len(payload) > 2 * 1024 * 1024:
        raise ValueError("La imagen de firma supera el tamaño permitido.")
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("La imagen de firma no es un PNG válido.")
    return payload


def ensure_form_definitions():
    replacement = chr(0xfffd)
    display_labels = {
        ("usuario", f"C{replacement}dula"): "C\u00e9dula",
        ("sistemas", f"Extensi{replacement}n"): "Extensi\u00f3n",
        ("sistemas", f"Perfil de navegaci{replacement}n"): "Perfil de navegaci\u00f3n",
        ("equipo", "Tipo de equipo"): "Tipo de equipo",
        ("equipo", f"Direcci{replacement}n IP"): "Direcci\u00f3n IP",
        ("perifericos", f"M{replacement}vil"): "M\u00f3vil",
        ("perifericos", "Cual es el otro periferico"): "\u00bfCu\u00e1l es el otro perif\u00e9rico?",
    }
    for order, (section, label, field_type, required, options) in enumerate(FORM_DEFINITIONS):
        clean_label = display_labels.get((section, label), label)
        key = f"{section}_{order}_{slugify(clean_label).replace('-', '_')}"
        clean_options = ["Desktop", "Port\u00e1til"] if section == "equipo" and label == "Tipo de equipo" else options
        definition, _ = FormFieldDefinition.objects.get_or_create(
            key=key,
            defaults={"label": clean_label, "section": section, "field_type": field_type,
                     "required": required, "options": clean_options, "sort_order": order},
        )
        changes = {"label": clean_label, "field_type": field_type, "required": required,
                   "options": clean_options, "sort_order": order}
        if any(getattr(definition, name) != value for name, value in changes.items()):
            FormFieldDefinition.objects.filter(pk=definition.pk).update(**changes)
        for legacy in FormFieldDefinition.objects.filter(section=section, label=clean_label, active=True).exclude(pk=definition.pk):
            for old_value in ActaFieldValue.objects.filter(definition=legacy).iterator():
                current, created = ActaFieldValue.objects.get_or_create(
                    acta=old_value.acta, definition=definition,
                    defaults={"value": old_value.value, "source": old_value.source, "updated_by": old_value.updated_by},
                )
                if not created and current.value in (None, "") and old_value.value not in (None, ""):
                    current.value = old_value.value
                    current.save(update_fields=["value", "updated_at"])
                old_value.delete()
            legacy.active = False
            legacy.save(update_fields=["active"])


def form_context(request):
    ensure_form_definitions()
    fields = list(FormFieldDefinition.objects.filter(active=True).order_by("sort_order"))
    field_rows = [{
        "field": field,
        "field_name": f"field_{field.key}",
        "field_value": request.POST.get(f"field_{field.key}", ""),
    } for field in fields if field.label != "Tipo de cuenta"]
    sections = []
    for section in dict.fromkeys(field.section for field in fields):
        rows = [row for row in field_rows if row["field"].section == section]
        if section == "sistemas":
            rows.sort(key=lambda row: (0 if row["field"].label == "Acceso a red" else 1 if row["field"].label == "Acceso a correo" else 2, row["field"].sort_order))
        sections.append({"key": section, "label": section.replace("_", " ").title(), "rows": rows})
    return fields, sections, field_rows


def _acta_document_context(acta, draft_post=None):
    ensure_form_definitions()
    definitions = list(FormFieldDefinition.objects.filter(active=True).order_by("sort_order"))
    saved_values = {
        (row.definition.section, row.definition.label): row.value
        for row in acta.field_values.select_related("definition").all()
    } if getattr(acta, "pk", None) else {}
    grouped = {}
    for definition in definitions:
        if draft_post is not None:
            raw = draft_post.get(f"field_{definition.key}", "")
            value = raw == "on" if definition.field_type == "boolean" else raw.strip()
        else:
            value = saved_values.get((definition.section, definition.label), "")
        if definition.field_type == "boolean":
            false_values = {"false", "0", "off", "no", "n.a", "n.a.", "no aplica", ""}
            enabled_value = value is True or (isinstance(value, str) and value.strip().lower() not in false_values) or str(value).lower() in {"true", "1", "on", "si"}
            display_value = "SI" if enabled_value else "NO APLICA"
        else:
            display_value = value if value not in (None, "") else "N.A."
        grouped.setdefault(definition.section, []).append({
            "key": definition.key, "label": definition.label,
            "value": display_value, "raw_value": value,
            "field_type": definition.field_type,
        })

    titles = {
        "usuario": "Usuario", "sistemas": "Usuarios",
        "equipo": "Desktop o port\u00e1til", "perifericos": "Perif\u00e9ricos adicionales",
        "monitor": "Monitor",
    }
    sections = [{"key": key, "title": titles.get(key, key.replace("_", " ").title()), "fields": fields}
                for key, fields in grouped.items() if key != "observaciones"]
    values = {(section["key"], field["label"]): field for section in sections for field in section["fields"]}
    account = values.get(("sistemas", "Tipo de cuenta"), {}).get("raw_value", "")
    email = values.get(("sistemas", "Cuenta de correo"), {}).get("raw_value", "")
    account_red_value = values.get(("sistemas", "Acceso a red"), {}).get("raw_value", False)
    account_mail_value = values.get(("sistemas", "Acceso a correo"), {}).get("raw_value", False)
    def enabled(raw):
        return raw is True or str(raw).strip().lower() in {"true", "1", "on", "si", "sí"}
    account_red = enabled(account_red_value) or account == "Red"
    account_email = enabled(account_mail_value) or account == "Correo" or str(email).strip().lower() not in {"", "n.a", "n.a."}
    equipment_type = values.get(("equipo", "Tipo de equipo"), {}).get("raw_value", "")
    equipment_model = " ".join(str(values.get(("equipo", label), {}).get("raw_value", "") or "").strip() for label in ("Marca", "Modelo")).strip() or "N.A."
    monitor_model = " ".join(str(values.get(("monitor", label), {}).get("raw_value", "") or "").strip() for label in ("Marca", "Modelo")).strip() or "N.A."
    peripheral_checks = [field for field in grouped.get("perifericos", []) if field["field_type"] == "boolean"]
    peripheral_details = [field for field in grouped.get("perifericos", []) if field["field_type"] != "boolean"]

    signature_by_type = {}
    if getattr(acta, "pk", None):
        signature_by_type = {signature.signature_type: signature for signature in acta.signatures.select_related("signed_by").order_by("signed_at")}

    def related_user(field):
        if hasattr(acta, "_meta"):
            user_id = getattr(acta, f"{field}_id", None)
            return get_user_model().objects.filter(pk=user_id).first() if user_id else None
        return getattr(acta, field, None)

    def signer(slot, assigned_user, assigned_role):
        signature = signature_by_type.get(slot)
        user = signature.signed_by if signature and signature.signed_by else assigned_user
        name = signature.signer_name if signature else (user.get_full_name() or user.username if user else "Pendiente")
        cargo = signature.signer_role if signature and signature.signer_role else assigned_role
        labels = {"DELIVERY": "Entrega", "REVIEW": "Revisó", "FINAL_APPROVAL": "Aprobó", "RECEIVE": "Recibe"}
        signature_data = ""
        if signature and signature.signature_image:
            signature.signature_image.open("rb")
            signature_data = "data:image/png;base64," + base64.b64encode(signature.signature_image.read()).decode("ascii")
            signature.signature_image.close()
        return {"label": labels.get(slot, slot), "name": name, "cargo": cargo or "Pendiente", "signature": signature, "signature_data": signature_data}

    roles = [
        signer("DELIVERY", related_user("assigned_technician") or related_user("created_by"), "Técnico"),
        signer("REVIEW", related_user("supervisor_one"), "Supervisor uno"),
        signer("FINAL_APPROVAL", related_user("supervisor_two"), "Supervisor dos"),
        signer("RECEIVE", related_user("receiver"), "Receptor"),
    ]
    observation = next((field for field in grouped.get("observaciones", []) if field["label"] == "Observaciones"), None)
    obs = observation["value"] if observation else "N.A."
    legal_commitments = [
        {"text": label, "accepted": bool(getattr(acta, key, False))}
        for key, label in (
            ("legal_custody_accepted", "Acepto la custodia, uso responsable y devolución de los activos asignados."),
            ("legal_accuracy_confirmed", "Confirmo que la información registrada es completa y veraz."),
            ("legal_data_processing_accepted", "Acepto el tratamiento de la información para la gestión del acta."),
        )
    ]
    return {
        "document_sections": sections,
        "document_fields": values,
        "observations": obs,
        "commitments_text": ACTA_COMMITMENTS,
        "legal_commitments": legal_commitments,
        "document_signatures": roles,
        "account_type": account,
        "account_red": account_red,
        "account_email": account_email,
        "equipment_type": str(equipment_type).strip().lower(),
        "equipment_model": equipment_model,
        "monitor_model": monitor_model,
        "peripheral_checks": peripheral_checks,
        "peripheral_details": peripheral_details,
    }


def _safe_parse_date(value):
    try:
        return parse_date(value) if value else None
    except (TypeError, ValueError):
        return None


def _mock_field_values(case):
    equipment = case.get("equipment", {})
    peripherals = case.get("peripherals", {})
    values = {
        "Nombre completo": case.get("user_name", ""),
        "C\u00e9dula": case.get("document", ""),
        "Tipo de cuenta": "Red",
        "Usuario de Windows": case.get("windows_user", ""),
        "Cuenta de correo": case.get("email", ""),
        "Acceso a HelpDesk GLPI": case.get("helpdesk_access", False),
        "Acceso a red": case.get("network_access", True),
        "Acceso a correo": bool(case.get("email")),
        "Tipo de equipo": equipment.get("type", ""),
        "Marca": equipment.get("brand", ""),
        "Modelo": equipment.get("model", ""),
        "Serial": equipment.get("serial", ""),
        "Serial devuelto": equipment.get("returned_serial", ""),
        "Procesador": equipment.get("processor", ""),
        "Memoria RAM": equipment.get("ram", ""),
        "Disco duro": equipment.get("disk", ""),
        "Sistema operativo": equipment.get("operating_system", ""),
        "Placa de inventario": equipment.get("inventory_plate", ""),
    }
    peripheral_labels = {"headset": "Diadema", "keyboard": "Teclado", "mouse": "Mouse", "cpu": "CPU", "mobile": "M\u00f3vil", "sim": "SIM", "other": "Otro"}
    for peripheral_name, peripheral in peripherals.items():
        label = peripheral_labels.get(peripheral_name, peripheral_name.replace("_", " ").title())
        values[label] = " / ".join(str(peripheral.get(key, "")) for key in ("brand", "model", "inventory_plate", "serial"))
    return values


@login_required
def glpi_autocomplete(request):
    if active_role(request.user) not in {"ADMIN", "TECHNICIAN"}:
        return JsonResponse({"ok": False, "message": "Tu rol no puede consultar casos GLPI."}, status=403)
    case_number = request.GET.get("case_number", "").strip()
    if not case_number:
        return JsonResponse({"ok": False, "message": "Escribe un número de caso GLPI."}, status=400)

    try:
        case = GlpiClient().get_case(case_number)
    except LookupError as error:
        return JsonResponse({"ok": False, "message": str(error)}, status=404)
    except (requests.RequestException, RuntimeError, ValueError):
        return JsonResponse({"ok": False, "message": "No fue posible consultar GLPI en este momento."}, status=502)

    site_name = case.get("site", "")
    site = None
    if site_name:
        site, _ = Site.objects.get_or_create(code=site_name.upper()[:30], defaults={"name": site_name})

    return JsonResponse({
        "ok": True,
        "simulation": settings.GLPI_SIMULATION_MODE,
        "case": {
            "case_number": case.get("case_number", case_number),
            "user_name": case.get("user_name", ""),
            "document": case.get("document", ""),
            "portfolio": case.get("portfolio", ""),
            "site": site_name,
            "site_id": site.id if site else "",
            "act_type": case.get("act_type", "Entrega"),
        },
        "fields": _mock_field_values(case),
    })


@login_required
def portfolio_autocomplete(request):
    if active_role(request.user) not in {"ADMIN", "TECHNICIAN"}:
        return JsonResponse({"ok": False, "message": "Tu rol no puede consultar portafolios."}, status=403)
    name = (request.GET.get("name") or "").strip()
    if not name:
        return JsonResponse({"ok": False, "message": "Selecciona un portafolio."}, status=400)
    portfolio = PortfolioCatalog.objects.filter(name__iexact=name, active=True).first()
    if portfolio is None:
        return JsonResponse({"ok": False, "message": "No hay valores configurados para este portafolio."}, status=404)
    return JsonResponse({
        "ok": True,
        "portfolio": portfolio.name,
        "fields": _portfolio_field_defaults(portfolio),
    })


def _portfolio_field_defaults(portfolio):
    ensure_form_definitions()
    allowed_labels = set(
        FormFieldDefinition.objects.filter(active=True, section="sistemas").values_list(
            "label", flat=True
        )
    )
    return {
        label: value
        for label, value in portfolio.defaults.items()
        if label in allowed_labels
    }


@login_required
def campaign_autocomplete(request):
    if active_role(request.user) not in {"ADMIN", "TECHNICIAN"}:
        return JsonResponse({"ok": False, "message": "Tu rol no puede consultar campañas."}, status=403)
    campaign_id = (request.GET.get("campaign_id") or "").strip()
    if not campaign_id.isdigit():
        return JsonResponse({"ok": False, "message": "Selecciona una campaña válida."}, status=400)
    campaign = CampaignCatalog.objects.select_related("portfolio").filter(
        pk=campaign_id,
        active=True,
    ).first()
    if campaign is None:
        return JsonResponse({"ok": False, "message": "La campaña seleccionada no existe o está inactiva."}, status=404)
    if campaign.portfolio is None or not campaign.portfolio.active:
        return JsonResponse({
            "ok": False,
            "message": "La campaña no tiene un portafolio activo asociado. Pide al administrador que configure la relación.",
        }, status=409)
    return JsonResponse({
        "ok": True,
        "campaign": campaign.name,
        "portfolio": campaign.portfolio.name,
        "fields": _portfolio_field_defaults(campaign.portfolio),
    })


@login_required
def acta_list(request):
    role = active_role(request.user)
    if not role:
        return HttpResponseForbidden("La cuenta no tiene un rol activo.")
    qs = visible_actas(Acta.objects.select_related("site", "created_by", "assigned_technician"), request.user).order_by("-created_at")
    if role == "SUPERVISOR_ONE":
        qs = qs.filter(status__in=["PENDING_SUPERVISOR_ONE", "DELIVERY_SIGNED", "REJECTED_BY_SUPERVISOR_ONE"])
    elif role == "SUPERVISOR_TWO":
        qs = qs.filter(status__in=["PENDING_SUPERVISOR_TWO", "REJECTED_BY_SUPERVISOR_TWO"])

    query = request.GET.get("q")
    if query:
        qs = qs.filter(Q(glpi_case_number__icontains=query) | Q(portfolio__icontains=query) | Q(act_type__icontains=query))

    status_filter = request.GET.get("status")
    act_type_filter = request.GET.get("act_type")
    site_filter = request.GET.get("site")
    if status_filter:
        qs = qs.filter(status=status_filter)
    if act_type_filter:
        qs = qs.filter(act_type=act_type_filter)
    if site_filter:
        qs = qs.filter(site_id=site_filter)

    return render(request, "actas/list.html", {"actas": qs, "title": "Actas", "role": role, "sites": Site.objects.filter(active=True).order_by("name"), "status_choices": Acta.STATUS})


@login_required
def acta_create(request):
    if active_role(request.user) != "TECHNICIAN":
        return HttpResponseForbidden("Solo los t\u00e9cnicos pueden crear actas.")
    fields, sections, field_rows = form_context(request)
    sites = Site.objects.filter(active=True).order_by("name")
    receiver_profiles = UserRole.objects.filter(role="RECEIVER", active=True, user__is_active=True).select_related("user")
    portfolios = PortfolioCatalog.objects.filter(active=True).order_by("name")
    campaigns = CampaignCatalog.objects.filter(active=True).select_related("portfolio").order_by("name")
    assignment_context = {
        "portfolios": portfolios,
        "campaigns": campaigns,
        "has_campaigns": campaigns.exists(),
    }
    base_context = {
        "fields": fields,
        "sections": sections,
        "field_rows": field_rows,
        "sites": sites,
        **assignment_context,
        "title": "Nueva acta",
    }

    if request.method == "POST":
        glpi_case_number = (request.POST.get("glpi_case_number") or "").strip()
        act_type = (request.POST.get("act_type") or "").strip()
        act_date = request.POST.get("act_date") or None
        portfolio = (request.POST.get("portfolio") or "").strip()
        campaign_id = (request.POST.get("campaign_id") or "").strip()
        campaign = campaigns.filter(pk=campaign_id).first() if campaign_id.isdigit() else None

        if not glpi_case_number:
            return render(request, "actas/form.html", {**base_context, "error": "El número de caso GLPI es obligatorio."})
        if (campaign_id and campaign is None) or (base_context["has_campaigns"] and campaign is None):
            return render(request, "actas/form.html", {**base_context, "error": "Selecciona una campaña activa."}, status=400)
        if campaign:
            if campaign.portfolio_id is None or not campaign.portfolio.active:
                return render(request, "actas/form.html", {
                    **base_context,
                    "error": "La campaña seleccionada no tiene un portafolio activo asociado. Pide al administrador que configure la relación.",
                }, status=400)
            portfolio = campaign.portfolio.name

        site_id = request.POST.get("site_id") or None
        workflow = WorkflowConfig.get_solo()
        if not workflow.supervisor_one_id or not workflow.supervisor_two_id:
            return render(request, "actas/form.html", {**base_context, "error": "El administrador debe configurar los dos supervisores en Administración antes de crear actas."}, status=400)
        if not all(request.POST.get(name) == "on" for name in LEGAL_CONSENT_FIELDS):
            return render(request, "actas/form.html", {**base_context, "error": "Debes aceptar las tres declaraciones para continuar."}, status=400)
        if act_type not in {"Entrega", "Cambio"}:
            return render(request, "actas/form.html", {**base_context, "error": "Selecciona un tipo de acta válido."}, status=400)
        if not _safe_parse_date(act_date):
            return render(request, "actas/form.html", {**base_context, "error": "La fecha indicada no es válida."}, status=400)
        if site_id:
            try:
                site_id = int(site_id)
            except (TypeError, ValueError):
                site_id = -1
            if not sites.filter(pk=site_id).exists():
                return render(request, "actas/form.html", {**base_context, "error": "La sede seleccionada no existe o está inactiva."}, status=400)
        missing = [field.label for field in fields if field.required and not (request.POST.get(f"field_{field.key}") or "").strip()]
        if missing:
            return render(request, "actas/form.html", {**base_context, "error": "Completa los campos obligatorios: " + ", ".join(missing)}, status=400)
        if Acta.objects.filter(glpi_case_number=glpi_case_number).exists():
            return render(request, "actas/form.html", {**base_context, "error": "Ya existe un acta con ese número de caso GLPI."}, status=400)

        try:
            glpi_case = GlpiClient().get_case(glpi_case_number)
        except LookupError:
            return render(request, "actas/form.html", {**base_context, "error": "No se encontró el caso en GLPI para identificar al receptor."}, status=400)
        except (requests.RequestException, RuntimeError, ValueError):
            logger.exception("No se pudo consultar GLPI para identificar al receptor del caso=%s", glpi_case_number)
            return render(request, "actas/form.html", {**base_context, "error": "No se pudo verificar el receptor con GLPI. Intenta nuevamente."}, status=502)

        receiver_email = str(glpi_case.get("email") or "").strip()
        if not receiver_email:
            return render(request, "actas/form.html", {**base_context, "error": "GLPI no proporcionó un correo para identificar al receptor del activo."}, status=400)
        matching_receiver_profiles = list(receiver_profiles.filter(user__email__iexact=receiver_email)[:2])
        if not matching_receiver_profiles:
            return render(request, "actas/form.html", {**base_context, "error": "No hay una cuenta activa con rol Receptor que coincida con el correo de GLPI."}, status=400)
        if len(matching_receiver_profiles) > 1:
            return render(request, "actas/form.html", {**base_context, "error": "Hay varias cuentas Receptor con el correo de GLPI. Pide al administrador corregirlas."}, status=400)
        receiver = matching_receiver_profiles[0].user

        try:
            with transaction.atomic():
                acta = Acta.objects.create(status="PENDING_RECEIVER_SIGNATURE", act_type=act_type, act_date=act_date, portfolio=portfolio, campaign=campaign, glpi_case_number=glpi_case_number, created_by=request.user, assigned_technician=request.user, supervisor_one=workflow.supervisor_one, supervisor_two=workflow.supervisor_two, receiver=receiver, site_id=site_id, legal_custody_accepted=True, legal_accuracy_confirmed=True, legal_data_processing_accepted=True, legal_accepted_at=timezone.now(), legal_acceptance_ip=_request_ip(request))
                from audit.models import ActaEvent
                ActaEvent.objects.create(acta=acta, event_type="LIFECYCLE", action="ACTA_CREATED", actor=request.user, from_status="DRAFT", to_status="PENDING_RECEIVER_SIGNATURE", ip_address=_request_ip(request))
                for field in fields:
                    value = request.POST.get(f"field_{field.key}")
                    if value in (None, ""):
                        continue
                    normalized_value = value
                    if field.field_type == "boolean":
                        normalized_value = value == "on"
                    elif field.field_type == "number":
                        try:
                            normalized_value = int(value)
                        except ValueError:
                            pass
                    ActaFieldValue.objects.create(acta=acta, definition=field, value=normalized_value, source="MANUAL", updated_by=request.user)
        except IntegrityError:
            return render(request, "actas/form.html", {**base_context, "error": "No se pudo guardar el acta. Verifica que el caso GLPI no esté duplicado."}, status=400)

        return redirect("html-acta-detail", public_id=acta.public_id)

    return render(request, "actas/form.html", {"fields": fields, "sections": sections, "field_rows": field_rows, "sites": sites, **assignment_context, "title": "Nueva acta"})


@login_required
def acta_edit(request, public_id):
    acta = get_visible_acta_or_404(public_id, request.user)
    role = active_role(request.user)
    if role not in {"TECHNICIAN", "ADMIN"} or acta.status not in {"REJECTED_BY_SUPERVISOR_ONE", "REJECTED_BY_SUPERVISOR_TWO"}:
        return HttpResponseForbidden("Solo el técnico asignado puede corregir un acta rechazada.")
    if role == "TECHNICIAN" and acta.assigned_technician_id != request.user.pk:
        return HttpResponseForbidden("El acta no está asignada a tu usuario.")

    fields, sections, field_rows = form_context(request)
    sites = Site.objects.filter(active=True).order_by("name")
    portfolios = PortfolioCatalog.objects.filter(active=True).order_by("name")
    campaigns = CampaignCatalog.objects.filter(active=True).select_related("portfolio").order_by("name")
    existing_values = {row.definition_id: row.value for row in acta.field_values.all()}
    for row in field_rows:
        row["field_value"] = existing_values.get(row["field"].pk, "")

    if request.method == "POST":
        act_type = (request.POST.get("act_type") or "").strip()
        act_date = request.POST.get("act_date") or ""
        glpi_case_number = (request.POST.get("glpi_case_number") or "").strip()
        site_id = request.POST.get("site_id") or None
        base_context = {"acta": acta, "fields": fields, "sections": sections, "field_rows": field_rows, "sites": sites, "portfolios": portfolios, "campaigns": campaigns, "has_campaigns": campaigns.exists(), "title": "Corregir acta"}
        campaign_id = (request.POST.get("campaign_id") or "").strip()
        campaign = campaigns.filter(pk=campaign_id).first() if campaign_id.isdigit() else None
        if (campaign_id and campaign is None) or (base_context["has_campaigns"] and campaign is None):
            return render(request, "actas/form.html", {**base_context, "error": "Selecciona una campaña activa."}, status=400)
        if campaign:
            if campaign.portfolio_id is None or not campaign.portfolio.active:
                return render(request, "actas/form.html", {
                    **base_context,
                    "error": "La campaña seleccionada no tiene un portafolio activo asociado. Pide al administrador que configure la relación.",
                }, status=400)
        if not all(request.POST.get(name) == "on" for name in LEGAL_CONSENT_FIELDS):
            return render(request, "actas/form.html", {**base_context, "error": "Debes aceptar las tres declaraciones para continuar."}, status=400)
        if not glpi_case_number or Acta.objects.filter(glpi_case_number=glpi_case_number).exclude(pk=acta.pk).exists():
            return render(request, "actas/form.html", {**base_context, "error": "El número de caso es obligatorio y no puede estar duplicado."}, status=400)
        if act_type not in {"Entrega", "Cambio"} or not _safe_parse_date(act_date):
            return render(request, "actas/form.html", {**base_context, "error": "Verifica el tipo de acta y la fecha."}, status=400)
        if site_id:
            try:
                site_id = int(site_id)
            except (TypeError, ValueError):
                site_id = -1
            if not sites.filter(pk=site_id).exists():
                return render(request, "actas/form.html", {**base_context, "error": "La sede seleccionada no existe o está inactiva."}, status=400)
        missing = [field.label for field in fields if field.required and not (request.POST.get(f"field_{field.key}") or "").strip()]
        if missing:
            return render(request, "actas/form.html", {**base_context, "error": "Completa los campos obligatorios: " + ", ".join(missing)}, status=400)
        previous_status = acta.status
        next_status = "PENDING_RECEIVER_SIGNATURE"
        with transaction.atomic():
            acta.signatures.filter(result="APPROVED").update(result="SUPERSEDED")
            acta.act_type = act_type
            acta.act_date = act_date
            acta.glpi_case_number = glpi_case_number
            acta.portfolio = campaign.portfolio.name if campaign else (request.POST.get("portfolio") or "").strip()
            acta.campaign = campaign
            acta.site_id = site_id
            acta.status = next_status
            acta.rejection_reason = ""
            acta.rejection_step = ""
            acta.legal_custody_accepted = True
            acta.legal_accuracy_confirmed = True
            acta.legal_data_processing_accepted = True
            acta.legal_accepted_at = timezone.now()
            acta.legal_acceptance_ip = _request_ip(request)
            acta.save(update_fields=["act_type", "act_date", "glpi_case_number", "portfolio", "campaign", "site", "status", "rejection_reason", "rejection_step", "legal_custody_accepted", "legal_accuracy_confirmed", "legal_data_processing_accepted", "legal_accepted_at", "legal_acceptance_ip", "updated_at"])
            from audit.models import ActaEvent
            ActaEvent.objects.create(acta=acta, event_type="CORRECTION", action="ACTA_CORRECTED", actor=request.user, from_status=previous_status, to_status=next_status, ip_address=_request_ip(request))
            for field in fields:
                raw_value = request.POST.get(f"field_{field.key}", "")
                value = (field.field_type == "boolean" and raw_value == "on") if field.field_type == "boolean" else raw_value.strip()
                ActaFieldValue.objects.update_or_create(acta=acta, definition=field, defaults={"value": value, "source": "MANUAL", "updated_by": request.user})
        messages.success(request, "Correcciones guardadas y acta reenviada a revisión.")
        return redirect("html-acta-detail", public_id=acta.public_id)

    return render(request, "actas/form.html", {"acta": acta, "fields": fields, "sections": sections, "field_rows": field_rows, "sites": sites, "portfolios": portfolios, "campaigns": campaigns, "has_campaigns": campaigns.exists(), "title": "Corregir acta"})


def receiver_public_sign(request, token):
    acta = get_object_or_404(Acta, receiver_signature_token=token)
    approved_types = set(acta.signatures.filter(result="APPROVED").values_list("signature_type", flat=True))
    if "RECEIVE" in approved_types or acta.status != "PENDING_RECEIVER_SIGNATURE":
        return render(request, "actas/receiver_sign_done.html", {"acta": acta}, status=200)

    identity = {
        (row.definition.section, row.definition.label): row.value
        for row in acta.field_values.select_related("definition").filter(definition__section="usuario")
    }
    receiver_name = str(identity.get(("usuario", "Nombre completo")) or acta.receiver.get_full_name() or acta.receiver.username)
    receiver_document = str(identity.get(("usuario", "C\u00e9dula")) or "")
    context = {
        "acta": acta,
        "receiver_name": receiver_name,
        "receiver_document": receiver_document,
        **_acta_document_context(acta),
    }
    if request.method == "POST":
        try:
            signature_bytes = decode_signature_data(request.POST.get("signature_data", ""))
        except ValueError as error:
            return render(request, "actas/receiver_sign.html", {**context, "error": str(error)}, status=400)

        with transaction.atomic():
            locked_acta = Acta.objects.select_for_update().get(pk=acta.pk)
            if locked_acta.status != "PENDING_RECEIVER_SIGNATURE" or locked_acta.signatures.filter(signature_type="RECEIVE", result="APPROVED").exists():
                return render(request, "actas/receiver_sign_done.html", {"acta": locked_acta}, status=200)
            signature = Signature.objects.create(
                acta=locked_acta,
                signature_type="RECEIVE",
                signed_by=locked_acta.receiver,
                signer_name=receiver_name,
                signer_role="Receptor del activo",
                signer_document=receiver_document,
                signature_hash=hashlib.sha256(signature_bytes).hexdigest(),
                method="DRAWN_PNG",
                result="APPROVED",
                ip_address=_request_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
            signature.signature_image.save(f"signature-{signature.pk}.png", ContentFile(signature_bytes), save=True)
            previous_status = locked_acta.status
            locked_acta.status = "PENDING_TECHNICIAN_DELIVERY"
            locked_acta.save(update_fields=["status", "updated_at"])
            from audit.models import ActaEvent
            ActaEvent.objects.create(
                acta=locked_acta,
                event_type="SIGNATURE",
                action="RECEIVE_APPROVED",
                actor=locked_acta.receiver,
                from_status=previous_status,
                to_status=locked_acta.status,
                ip_address=_request_ip(request),
            )
            schedule_signature_notification(locked_acta, signature, actor=locked_acta.receiver)
        response = render(request, "actas/receiver_sign_done.html", {"acta": locked_acta})
        response["Cache-Control"] = "no-store"
        return response

    if request.method != "GET":
        return HttpResponse(status=405)
    response = render(request, "actas/receiver_sign.html", context)
    response["Cache-Control"] = "no-store"
    return response


@login_required
def acta_detail(request, public_id):
    acta = get_visible_acta_or_404(public_id, request.user)
    if request.method == "POST":
        return HttpResponseForbidden("Las aprobaciones y rechazos deben registrarse desde la bandeja de revisión y la pantalla de firma.")
    field_values = {item.definition.key: item.value for item in acta.field_values.select_related("definition").all()}
    signatures = acta.signatures.select_related("signed_by").order_by("signed_at")
    signature_types = dict(Signature.TYPES)
    signatures_by_type = {signature.signature_type: signature for signature in signatures}
    signature_rows = [{"label": label, "signature": signatures_by_type.get(key)} for key, label in Signature.TYPES]
    timeline = [
        {"title": "Acta creada", "time": acta.created_at.strftime("%d/%m/%Y %H:%M"), "description": "Se registró el documento inicial."},
        *[{"title": signature_types.get(signature.signature_type, signature.signature_type), "time": signature.signed_at.strftime("%d/%m/%Y %H:%M"), "description": f"Firma registrada por {signature.signer_name}."} for signature in signatures],
        {"title": acta.get_status_display(), "time": acta.updated_at.strftime("%d/%m/%Y %H:%M"), "description": acta.rejection_reason or "Sin observaciones."},
    ]
    signature_progress = min(100, round(len([item for item in signatures if item.result == "APPROVED"]) / 4 * 100))
    role = active_role(request.user)
    can_review = (role == "SUPERVISOR_ONE" and acta.supervisor_one_id == request.user.pk and acta.status == "PENDING_SUPERVISOR_ONE") or (role == "SUPERVISOR_TWO" and acta.supervisor_two_id == request.user.pk and acta.status == "PENDING_SUPERVISOR_TWO")
    receiver_sign_url = ""
    if role == "TECHNICIAN" and acta.assigned_technician_id == request.user.pk and acta.status == "PENDING_RECEIVER_SIGNATURE":
        receiver_sign_url = request.build_absolute_uri(reverse("html-receiver-public-sign", kwargs={"token": acta.receiver_signature_token}))
    document_context = _acta_document_context(acta)
    return render(request, "actas/detail.html", {"acta": acta, "timeline": timeline, "field_values": field_values, "signatures": signatures, "signature_rows": signature_rows, "signature_progress": signature_progress, "can_review": can_review, "role": role, "receiver_sign_url": receiver_sign_url, "title": "Detalle de acta", **document_context})


@login_required
def acta_export_xlsx(request, public_id):
    acta = get_visible_acta_or_404(public_id, request.user)
    workbook = render_acta_xlsx(acta)
    response = HttpResponse(workbook.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="acta-{acta.glpi_case_number}.xlsx"'
    return response


@login_required
def acta_receiver_upload(request, public_id):
    acta = get_visible_acta_or_404(public_id, request.user)
    if active_role(request.user) != "RECEIVER" or acta.receiver_id != request.user.pk:
        return HttpResponseForbidden("Solo el receptor asignado puede cargar el escaneo firmado.")
    if acta.status != "PENDING_RECEIVER_UPLOAD":
        return HttpResponseForbidden("El escaneo solo se puede cargar después de la aprobación de los supervisores.")
    approvals = set(acta.signatures.filter(result="APPROVED").values_list("signature_type", flat=True))
    if not {"DELIVERY", "REVIEW", "FINAL_APPROVAL"}.issubset(approvals):
        return HttpResponseForbidden("El escaneo requiere la firma de Entrega y las dos aprobaciones.")
    if request.method != "POST":
        return HttpResponseForbidden("Método no permitido.")
    upload = request.FILES.get("signed_scan")
    if not upload or upload.size > 15 * 1024 * 1024 or upload.content_type != "application/pdf":
        messages.error(request, "Adjunta el escaneo firmado en PDF (máximo 15 MB).")
        return redirect("html-acta-detail", public_id=acta.public_id)
    if not upload.name.lower().endswith(".pdf") or not upload.read(5).startswith(b"%PDF-"):
        messages.error(request, "El archivo adjunto no es un PDF válido.")
        return redirect("html-acta-detail", public_id=acta.public_id)
    upload.seek(0)
    document_hash = hashlib.sha256(upload.read()).hexdigest()
    upload.seek(0)
    previous_status = acta.status
    with transaction.atomic():
        acta.pdf_file = upload
        acta.status = "GLPI_UPLOAD_PENDING" if settings.GLPI_UPLOAD_ENABLED else "COMPLETED"
        acta.glpi_upload_status = "PENDING" if settings.GLPI_UPLOAD_ENABLED else "DISABLED"
        if not settings.GLPI_UPLOAD_ENABLED:
            acta.completed_at = timezone.now()
        acta.save(update_fields=["pdf_file", "status", "glpi_upload_status", "completed_at", "updated_at"])
        receive_signature = Signature.objects.create(acta=acta, signature_type="RECEIVE", signed_by=request.user, signer_name=request.user.get_full_name() or request.user.username, signer_role="Receptor del activo", signature_hash=document_hash, method="SCANNED_PDF", result="APPROVED", ip_address=_request_ip(request), user_agent=request.META.get("HTTP_USER_AGENT", ""))
        schedule_signature_notification(acta, receive_signature, actor=request.user)
    if settings.GLPI_UPLOAD_ENABLED:
        try:
            with acta.pdf_file.open("rb") as signed_pdf:
                GlpiClient().upload_document(acta.glpi_case_number, acta.pdf_file.name.rsplit("/", 1)[-1], signed_pdf)
            acta.status = "GLPI_UPLOADED"
            acta.glpi_upload_status = "UPLOADED"
            acta.glpi_uploaded_at = timezone.now()
            acta.completed_at = acta.glpi_uploaded_at
            acta.save(update_fields=["status", "glpi_upload_status", "glpi_uploaded_at", "completed_at", "updated_at"])
        except (requests.RequestException, RuntimeError, ValueError, OSError):
            logger.exception("No se pudo asociar en GLPI el escaneo del acta=%s", acta.public_id)
            acta.status = "GLPI_UPLOAD_FAILED"
            acta.glpi_upload_status = "FAILED"
            acta.save(update_fields=["status", "glpi_upload_status", "updated_at"])
    from audit.models import ActaEvent
    ActaEvent.objects.create(acta=acta, event_type="DOCUMENT", action="SIGNED_SCAN_UPLOADED", actor=request.user, from_status=previous_status, to_status=acta.status, metadata={"filename": upload.name, "size": upload.size}, ip_address=_request_ip(request))
    if acta.status == "COMPLETED":
        messages.success(request, "Escaneo firmado cargado; el acta quedó completada.")
    elif acta.status == "GLPI_UPLOADED":
        messages.success(request, "Escaneo firmado cargado y asociado correctamente al caso GLPI.")
    else:
        messages.error(request, "El escaneo quedó guardado, pero no se pudo cargar a GLPI. Contacta al administrador para reintentar.")
    return redirect("html-acta-detail", public_id=acta.public_id)


@login_required
def acta_glpi_retry(request, public_id):
    if request.method != "POST" or active_role(request.user) != "ADMIN":
        return HttpResponseForbidden("Solo un administrador puede reintentar una carga a GLPI.")
    acta = get_object_or_404(Acta, public_id=public_id)
    if acta.status != "GLPI_UPLOAD_FAILED" or not acta.pdf_file:
        return HttpResponseForbidden("El acta no tiene una carga a GLPI fallida para reintentar.")
    previous_status = acta.status
    try:
        with acta.pdf_file.open("rb") as signed_pdf:
            GlpiClient().upload_document(acta.glpi_case_number, acta.pdf_file.name.rsplit("/", 1)[-1], signed_pdf)
        acta.status = "GLPI_UPLOADED"
        acta.glpi_upload_status = "UPLOADED"
        acta.glpi_uploaded_at = timezone.now()
        acta.completed_at = acta.glpi_uploaded_at
        acta.save(update_fields=["status", "glpi_upload_status", "glpi_uploaded_at", "completed_at", "updated_at"])
        from audit.models import ActaEvent
        ActaEvent.objects.create(acta=acta, event_type="GLPI", action="DOCUMENT_UPLOAD_RETRIED", actor=request.user, from_status=previous_status, to_status=acta.status, ip_address=_request_ip(request))
        messages.success(request, "El escaneo se asoció correctamente al caso GLPI.")
    except (requests.RequestException, RuntimeError, ValueError, OSError):
        logger.exception("Falló el reintento de carga GLPI acta=%s", acta.public_id)
        messages.error(request, "GLPI no está disponible o rechazó la carga. El archivo local se conserva.")
    return redirect("html-acta-detail", public_id=acta.public_id)


@login_required
def private_media(request, media_path):
    signature = Signature.objects.filter(signature_image=media_path).select_related("acta").first()
    acta = signature.acta if signature else Acta.objects.filter(pdf_file=media_path).first()
    if acta:
        if not visible_actas(Acta.objects.filter(pk=acta.pk), request.user).exists():
            raise Http404
    else:
        profile = UserRole.objects.filter(digital_signature=media_path, user=request.user, active=True).first()
        if not profile and active_role(request.user) != "ADMIN":
            raise Http404
        if not profile and not UserRole.objects.filter(digital_signature=media_path).exists():
            raise Http404
    try:
        file_path = safe_join(str(settings.MEDIA_ROOT), media_path)
    except SuspiciousFileOperation as error:
        raise Http404 from error
    if not Path(file_path).is_file():
        raise Http404
    content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    response = FileResponse(open(file_path, "rb"), content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
def acta_preview(request, public_id):
    acta = get_visible_acta_or_404(public_id, request.user)
    document_context = _acta_document_context(acta)
    return render(request, "actas/preview.html", {
        "acta": acta,
        **document_context,
        "title": "Vista previa del acta",
    })


@login_required
def acta_preview_draft(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    if active_role(request.user) != "TECHNICIAN":
        return HttpResponseForbidden("Solo los t\u00e9cnicos pueden crear actas.")
    try:
        site_id = int(request.POST.get("site_id", ""))
        site = Site.objects.filter(pk=site_id, active=True).first()
    except (TypeError, ValueError):
        site = None
    receiver_id = request.POST.get("receiver_id", "")
    receiver = get_user_model().objects.filter(pk=receiver_id).first() if receiver_id.isdigit() else None
    workflow = WorkflowConfig.get_solo()
    campaign_id = (request.POST.get("campaign_id") or "").strip()
    campaign = (
        CampaignCatalog.objects.filter(pk=campaign_id, active=True).first()
        if campaign_id.isdigit()
        else None
    )
    acta = SimpleNamespace(
        act_date=_safe_parse_date(request.POST.get("act_date", "")),
        site=site,
        act_type=request.POST.get("act_type", "").strip() or "N.A.",
        glpi_case_number=request.POST.get("glpi_case_number", "").strip() or "N.A.",
        portfolio=request.POST.get("portfolio", "").strip() or "N.A.",
        campaign=campaign,
        assigned_technician=request.user,
        created_by=request.user,
        supervisor_one=workflow.supervisor_one,
        supervisor_two=workflow.supervisor_two,
        receiver=receiver,
    )
    return render(request, "actas/preview_draft.html", {
        "acta": acta,
        **_acta_document_context(acta, draft_post=request.POST),
        "legal_commitments": [],
    })

@login_required
def acta_sign(request, public_id):
    acta = get_visible_acta_or_404(public_id, request.user)
    role = active_role(request.user)
    if request.method == "POST":
        signature_type = request.POST.get("signature_type", "")
        existing_types = set(acta.signatures.filter(result="APPROVED").values_list("signature_type", flat=True))
        allowed_roles = {"DELIVERY": {"TECHNICIAN"}, "REVIEW": {"SUPERVISOR_ONE"}, "FINAL_APPROVAL": {"SUPERVISOR_TWO"}}
        expected_users = {
            "DELIVERY": acta.assigned_technician,
            "REVIEW": acta.supervisor_one,
            "FINAL_APPROVAL": acta.supervisor_two,
        }
        transitions = {
            "DELIVERY": ("PENDING_SUPERVISOR_ONE", "PENDING_TECHNICIAN_DELIVERY"),
            "REVIEW": ("PENDING_SUPERVISOR_TWO", "PENDING_SUPERVISOR_ONE"),
            "FINAL_APPROVAL": ("COMPLETED", "PENDING_SUPERVISOR_TWO"),
        }
        next_status, required_status = transitions.get(signature_type, (None, None))
        required_signatures = {
            "DELIVERY": {"RECEIVE"},
            "REVIEW": {"RECEIVE", "DELIVERY"},
            "FINAL_APPROVAL": {"RECEIVE", "DELIVERY", "REVIEW"},
        }
        if signature_type in required_signatures and not required_signatures[signature_type].issubset(existing_types):
            messages.error(request, "No puedes firmar esta etapa porque faltan firmas anteriores.")
            return redirect("html-acta-sign", public_id=acta.public_id)
        if signature_type in existing_types:
            messages.error(request, "Esta firma ya fue registrada para el acta.")
            return redirect("html-acta-sign", public_id=acta.public_id)
        if role not in allowed_roles.get(signature_type, set()):
            messages.error(request, "Tu rol no tiene permiso para registrar este tipo de firma.")
            return redirect("html-acta-sign", public_id=acta.public_id)
        expected_user = expected_users.get(signature_type)
        if expected_user is None or expected_user.pk != request.user.pk:
            messages.error(request, "Permiso denegado: tu sesión no corresponde al usuario asignado para esta firma.")
            return redirect("html-acta-sign", public_id=acta.public_id)
        if not next_status or acta.status != required_status:
            messages.error(request, "Esta firma no corresponde al estado actual del acta.")
            return redirect("html-acta-sign", public_id=acta.public_id)
        profile = getattr(request.user, "role_profile", None)
        if not profile or not profile.digital_signature:
            messages.error(request, "Registra tu firma PNG fija antes de firmar.")
            return redirect("accounts:supervisor-signature")
        profile.digital_signature.open("rb")
        signature_bytes = profile.digital_signature.read()
        profile.digital_signature.close()
        if not signature_bytes.startswith(b"\x89PNG\r\n\x1a\n") or len(signature_bytes) > 1024 * 1024:
            messages.error(request, "La firma digital registrada no es un PNG válido o supera 1 MB.")
            return redirect("accounts:supervisor-signature")
        signer_name = request.user.get_full_name() or request.user.username
        with transaction.atomic():
            locked_acta = Acta.objects.select_for_update().get(pk=acta.pk)
            if locked_acta.status != required_status or locked_acta.signatures.filter(signature_type=signature_type, result="APPROVED").exists():
                messages.error(request, "La etapa ya cambió o la firma fue registrada por otra sesión.")
                return redirect("html-acta-detail", public_id=acta.public_id)
            signature = Signature.objects.create(
                acta=locked_acta,
                signature_type=signature_type,
                signed_by=request.user,
                signer_name=signer_name,
                signer_role=get_role_display(request.user),
                signer_document=request.POST.get("signer_document", ""),
                signature_hash=hashlib.sha256(signature_bytes).hexdigest(),
                method="DIGITAL_PNG",
                result="APPROVED",
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
            signature.signature_image.save(f"signature-{signature.pk}.png", ContentFile(signature_bytes), save=True)
            previous_status = locked_acta.status
            locked_acta.status = next_status
            update_fields = ["status", "updated_at"]
            if signature_type == "FINAL_APPROVAL":
                locked_acta.completed_at = timezone.now()
                save_final_acta_pdf(locked_acta)
                locked_acta.status = "GLPI_UPLOAD_PENDING" if settings.GLPI_UPLOAD_ENABLED else "COMPLETED"
                locked_acta.glpi_upload_status = "PENDING" if settings.GLPI_UPLOAD_ENABLED else "DISABLED"
                update_fields.extend(["pdf_file", "completed_at", "glpi_upload_status"])
            from audit.models import ActaEvent
            ActaEvent.objects.create(acta=locked_acta, event_type="SIGNATURE", action=f"{signature_type}_APPROVED", actor=request.user, from_status=previous_status, to_status=next_status, ip_address=_request_ip(request))
            locked_acta.save(update_fields=update_fields)
            schedule_signature_notification(locked_acta, signature, actor=request.user)
        if signature_type == "FINAL_APPROVAL" and settings.GLPI_UPLOAD_ENABLED:
            if not upload_final_acta_to_glpi(locked_acta, actor=request.user):
                messages.error(request, "El PDF final se generó, pero no se pudo asociar en GLPI. El administrador puede reintentar la carga.")
            else:
                messages.success(request, "El PDF final se generó y se asoció al caso GLPI.")
        else:
            messages.success(request, f"Firma guardada correctamente: {signer_name}, {signature.signed_at.strftime('%d/%m/%Y %H:%M')}.")
        return redirect("html-acta-detail", public_id=acta.public_id)

    existing_types = set(acta.signatures.filter(result="APPROVED").values_list("signature_type", flat=True))
    signature_options = []
    profile = getattr(request.user, "role_profile", None)
    technician_waiting = role == "TECHNICIAN" and acta.status == "PENDING_TECHNICIAN_DELIVERY" and acta.assigned_technician_id == request.user.pk
    supervisor_waiting = (role == "SUPERVISOR_ONE" and acta.status == "PENDING_SUPERVISOR_ONE" and acta.supervisor_one_id == request.user.pk) or (role == "SUPERVISOR_TWO" and acta.status == "PENDING_SUPERVISOR_TWO" and acta.supervisor_two_id == request.user.pk)
    if (technician_waiting or supervisor_waiting) and (not profile or not profile.digital_signature):
        messages.error(request, "No tienes una firma digital registrada.")
        return redirect("accounts:supervisor-signature")
    if technician_waiting and "RECEIVE" in existing_types and "DELIVERY" not in existing_types:
        signature_options.append(("DELIVERY", "Entrega / Técnico"))
    if acta.status == "PENDING_SUPERVISOR_ONE" and "REVIEW" not in existing_types and acta.supervisor_one_id == request.user.pk and getattr(getattr(request.user, "role_profile", None), "digital_signature", None):
        signature_options.append(("REVIEW", "Revisó / Supervisor uno"))
    if acta.status == "PENDING_SUPERVISOR_TWO" and "REVIEW" in existing_types and "FINAL_APPROVAL" not in existing_types and acta.supervisor_two_id == request.user.pk and getattr(getattr(request.user, "role_profile", None), "digital_signature", None):
        signature_options.append(("FINAL_APPROVAL", "Aprobó / Supervisor dos"))
    existing_signatures = acta.signatures.order_by("signed_at")
    document_context = _acta_document_context(acta)
    return render(request, "actas/sign.html", {"acta": acta, "signature_options": signature_options, "existing_signatures": existing_signatures, "is_supervisor_signing": role in {"SUPERVISOR_ONE", "SUPERVISOR_TWO"}, "title": "Firmar acta", **document_context})


@login_required
def acta_review(request):
    if request.method == "POST":
        action = request.POST.get("action")
        acta_id = request.POST.get("acta_id")
        acta = get_object_or_404(Acta, pk=acta_id)
        role = active_role(request.user)
        expected_user = acta.supervisor_one if acta.status == "PENDING_SUPERVISOR_ONE" else acta.supervisor_two
        if role not in {"SUPERVISOR_ONE", "SUPERVISOR_TWO"} or expected_user is None or expected_user.pk != request.user.pk:
            messages.error(request, "Permiso denegado: esta acta no está asignada a tu sesión de supervisor.")
            return redirect("html-acta-review")
        if action == "approve":
            messages.info(request, "Contin\u00faa en la pantalla de revisi\u00f3n para aprobar con tu firma PNG registrada.")
            return redirect("html-acta-sign", public_id=acta.public_id)
        elif action == "reject":
            approved_types = set(acta.signatures.filter(result="APPROVED").values_list("signature_type", flat=True))
            required_types = {"RECEIVE", "DELIVERY"}
            if role == "SUPERVISOR_TWO":
                required_types.add("REVIEW")
            if not required_types.issubset(approved_types):
                messages.error(request, "No puedes rechazar en esta etapa porque faltan firmas anteriores.")
                return redirect("html-acta-review")
            reason = (request.POST.get("reason") or "Sin motivo indicado").strip()
            role = active_role(request.user)
            if not reason:
                messages.error(request, "El motivo de rechazo es obligatorio.")
                return redirect("html-acta-review")
            if role == "SUPERVISOR_TWO" and acta.status == "PENDING_SUPERVISOR_TWO":
                signature_type, next_status, rejection_step = "FINAL_APPROVAL", "REJECTED_BY_SUPERVISOR_TWO", "SUPERVISOR_TWO"
            elif role == "SUPERVISOR_ONE" and acta.status == "PENDING_SUPERVISOR_ONE":
                signature_type, next_status, rejection_step = "REVIEW", "REJECTED_BY_SUPERVISOR_ONE", "SUPERVISOR_ONE"
            else:
                messages.error(request, "Tu rol no puede rechazar esta acta en su estado actual.")
                return redirect("html-acta-review")
            profile = getattr(request.user, "role_profile", None)
            if not profile or not profile.digital_signature:
                messages.error(request, "Registra tu firma PNG fija antes de rechazar actas.")
                return redirect("accounts:supervisor-signature")
            profile.digital_signature.open("rb")
            rejection_png = profile.digital_signature.read()
            profile.digital_signature.close()
            if not rejection_png.startswith(b"\x89PNG\r\n\x1a\n") or len(rejection_png) > 1024 * 1024:
                messages.error(request, "La firma PNG registrada no es v\u00e1lida o supera 1 MB.")
                return redirect("accounts:supervisor-signature")
            with transaction.atomic():
                signature = Signature.objects.create(acta=acta, signature_type=signature_type, signed_by=request.user, signer_name=request.user.get_full_name() or request.user.username, signer_role=get_role_display(request.user), signature_hash=hashlib.sha256(rejection_png).hexdigest(), result="REJECTED", rejection_reason=reason, method="DIGITAL_PNG", ip_address=request.META.get("REMOTE_ADDR"), user_agent=request.META.get("HTTP_USER_AGENT", ""))
                signature.signature_image.save(f"signature-rejected-{signature.pk}.png", ContentFile(rejection_png), save=True)
                acta.status = next_status
                acta.rejection_reason = reason
                acta.rejection_step = rejection_step
                acta.save(update_fields=["status", "rejection_reason", "rejection_step", "updated_at"])
                from audit.models import ActaEvent
                ActaEvent.objects.create(acta=acta, event_type="REJECTION", action=f"{signature_type}_REJECTED", actor=request.user, from_status="PENDING_SUPERVISOR_TWO" if signature_type == "FINAL_APPROVAL" else "PENDING_SUPERVISOR_ONE", to_status=next_status, reason=reason, ip_address=_request_ip(request))
                schedule_signature_notification(acta, signature, actor=request.user)
            messages.warning(request, "Rechazo guardado correctamente y notificado al responsable.")
        return redirect("html-acta-review")

    role = active_role(request.user)
    if role == "SUPERVISOR_ONE":
        qs = Acta.objects.filter(supervisor_one=request.user, status="PENDING_SUPERVISOR_ONE")
    elif role == "SUPERVISOR_TWO":
        qs = Acta.objects.filter(supervisor_two=request.user, status="PENDING_SUPERVISOR_TWO")
    else:
        qs = Acta.objects.none()
    qs = qs.prefetch_related("signatures").order_by("-created_at")
    review_rows = [{"acta": acta, "signatures": acta.signatures.order_by("signed_at")} for acta in qs]
    return render(request, "actas/review.html", {"actas": qs, "review_rows": review_rows, "title": "Revisión"})
