from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('messaging', '0003_chatmessage_drop_whatsappmessage'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatmessage',
            name='job_offer_id',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
