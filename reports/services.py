from collections import defaultdict
from django.utils import timezone

from actas.models import Acta, ActaFieldValue, Signature


def report_data(start_date=None, end_date=None, queryset=None):
    acts = (queryset if queryset is not None else Acta.objects.all()).prefetch_related("signatures__signed_by", "field_values__definition")
    if start_date:
        acts = acts.filter(created_at__date__gte=start_date)
    if end_date:
        acts = acts.filter(created_at__date__lte=end_date)

    signatures = Signature.objects.filter(acta__in=acts).select_related("acta", "signed_by")
    if start_date:
        signatures = signatures.filter(signed_at__date__gte=start_date)
    if end_date:
        signatures = signatures.filter(signed_at__date__lte=end_date)

    signed_by_period = defaultdict(int)
    for sig in signatures.filter(result="APPROVED", signature_type="FINAL_APPROVAL"):
        signed_by_period[sig.signed_at.strftime("%Y-%m")] += 1

    equipment = defaultdict(int)
    # Aggregate marca/modelo per acta, rather than counting the fields independently.
    equipment_fields = defaultdict(dict)
    for row in ActaFieldValue.objects.filter(acta__in=acts.filter(status__in=["COMPLETED", "GLPI_UPLOADED"]), definition__section="equipo").select_related("acta", "definition").distinct():
        label = row.definition.label.casefold()
        if label in {"marca", "modelo"}:
            value = row.value.get("value", "") if isinstance(row.value, dict) else row.value
            equipment_fields[row.acta_id][label] = str(value or "Sin especificar")
    for fields in equipment_fields.values():
        equipment[(fields.get("marca", "Sin especificar"), fields.get("modelo", "Sin especificar"))] += 1

    durations = defaultdict(list)
    by_user = defaultdict(list)
    for acta in acts:
        stage_sigs = {s.signature_type: s for s in acta.signatures.all() if s.result == "APPROVED"}
        stages = [
            ("Recibe", None, "RECEIVE"),
            ("Entrega", "RECEIVE", "DELIVERY"),
            ("Revisó · Supervisor uno", "DELIVERY", "REVIEW"),
            ("Aprobó · Supervisor dos", "REVIEW", "FINAL_APPROVAL"),
        ]
        for stage, before, after in stages:
            if after in stage_sigs and (before is None or before in stage_sigs):
                start = acta.created_at if before is None else stage_sigs[before].signed_at
                seconds = max(0, (stage_sigs[after].signed_at - start).total_seconds())
                durations[stage].append(seconds)
                signer = stage_sigs[after].signed_by
                if signer:
                    by_user[(stage, signer.get_full_name() or signer.username)].append(seconds)

    averages = {stage: round(sum(items) / len(items) / 3600, 1) for stage, items in durations.items()}
    supervisor_averages = [{"stage": stage, "user": user, "hours": round(sum(items) / len(items) / 3600, 1), "count": len(items)} for (stage, user), items in sorted(by_user.items())]

    pending_statuses = {
        "DRAFT": ("T?cnico", "assigned_technician"),
        "PENDING_RECEIVER_SIGNATURE": ("Receptor", "receiver"),
        "PENDING_TECHNICIAN_DELIVERY": ("T?cnico", "assigned_technician"),
        "PENDING_SUPERVISOR_ONE": ("Supervisor uno", "supervisor_one"),
        "PENDING_SUPERVISOR_TWO": ("Supervisor dos", "supervisor_two"),
        "PENDING_RECEIVER_UPLOAD": ("Receptor · legado", "receiver"),
        "GLPI_UPLOAD_PENDING": ("GLPI", "receiver"),
        "GLPI_UPLOAD_FAILED": ("Administrador", "created_by"),
    }
    pending = []
    for acta in acts.filter(status__in=pending_statuses):
        label, owner_field = pending_statuses[acta.status]
        owner = getattr(acta, owner_field)
        elapsed = max(0, (timezone.now() - acta.updated_at).days)
        pending.append({"case": acta.glpi_case_number, "stage": label, "owner": owner.get_full_name() or owner.username if owner else "Sin asignar", "days": elapsed, "status": acta.get_status_display()})

    return {
        "actas_total": acts.count(),
        "actas_firmadas": acts.filter(signatures__signature_type="FINAL_APPROVAL", signatures__result="APPROVED").distinct().count(),
        "signed_by_period": sorted(signed_by_period.items()),
        "equipment": [{"brand": brand, "model": model, "count": count} for (brand, model), count in sorted(equipment.items())],
        "averages": averages,
        "supervisor_averages": supervisor_averages,
        "pending": pending,
    }
