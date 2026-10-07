import django.db.models.deletion
from django.db import migrations, models


def match_campaigns_to_portfolios(apps, schema_editor):
    CampaignCatalog = apps.get_model("actas", "CampaignCatalog")
    PortfolioCatalog = apps.get_model("actas", "PortfolioCatalog")
    database = schema_editor.connection.alias

    for campaign in CampaignCatalog.objects.using(database).filter(portfolio__isnull=True):
        matches = PortfolioCatalog.objects.using(database).filter(
            name__iexact=campaign.name
        )[:2]
        matching_portfolios = list(matches)
        if len(matching_portfolios) == 1:
            campaign.portfolio_id = matching_portfolios[0].pk
            campaign.save(update_fields=["portfolio"], using=database)


class Migration(migrations.Migration):

    dependencies = [
        ("actas", "0007_campaigncatalog_acta_campaign"),
    ]

    operations = [
        migrations.AddField(
            model_name="campaigncatalog",
            name="portfolio",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="campaigns",
                to="actas.portfoliocatalog",
            ),
        ),
        migrations.RunPython(
            match_campaigns_to_portfolios,
            migrations.RunPython.noop,
        ),
    ]
