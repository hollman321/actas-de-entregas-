from rest_framework import serializers
from .models import Acta, ActaFieldValue, CampaignCatalog, FormFieldDefinition, Signature


class FormFieldDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FormFieldDefinition
        fields = "__all__"


class ActaFieldValueSerializer(serializers.ModelSerializer):
    key = serializers.CharField(source="definition.key", read_only=True)

    class Meta:
        model = ActaFieldValue
        fields = ["id", "definition", "key", "value", "source", "updated_at"]
        read_only_fields = ["updated_at"]


class SignatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Signature
        fields = ["signature_type", "signed_by", "signer_name", "signer_role", "signer_document", "signature_image", "signature_hash", "signed_at", "result", "rejection_reason", "ip_address", "method"]
        read_only_fields = ["signed_by", "signer_role", "signed_at", "signature_hash", "result", "rejection_reason", "ip_address"]


class ActaSerializer(serializers.ModelSerializer):
    field_values = ActaFieldValueSerializer(many=True, read_only=True)
    signatures = SignatureSerializer(many=True, read_only=True)
    campaign = serializers.PrimaryKeyRelatedField(
        queryset=CampaignCatalog.objects.filter(active=True),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Acta
        fields = ["public_id", "form_version", "status", "site", "act_type", "act_date", "glpi_case_number", "portfolio", "campaign", "assigned_technician", "supervisor_one", "supervisor_two", "rejection_reason", "legal_custody_accepted", "legal_accuracy_confirmed", "legal_data_processing_accepted", "legal_accepted_at", "legal_acceptance_ip", "field_values", "signatures", "created_at", "updated_at"]
        read_only_fields = ["public_id", "form_version", "status", "rejection_reason", "assigned_technician", "supervisor_one", "supervisor_two", "legal_custody_accepted", "legal_accuracy_confirmed", "legal_data_processing_accepted", "legal_accepted_at", "legal_acceptance_ip", "created_at", "updated_at"]
