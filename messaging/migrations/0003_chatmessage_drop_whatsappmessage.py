from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('messaging', '0002_rename_twilio_sid_to_external_id'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Widen the session identifier field (was max_length=30)
        migrations.AlterField(
            model_name='conversationhistory',
            name='phone_number',
            field=models.CharField(db_index=True, max_length=100, unique=True),
        ),
        # Replace WhatsAppMessage with ChatMessage
        migrations.DeleteModel(
            name='WhatsAppMessage',
        ),
        migrations.CreateModel(
            name='ChatMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_key', models.CharField(db_index=True, max_length=100)),
                ('role', models.CharField(choices=[('user', 'User'), ('assistant', 'Assistant')], max_length=15)),
                ('body', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='chat_messages',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
    ]
