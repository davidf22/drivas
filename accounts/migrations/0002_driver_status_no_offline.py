from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        # Change any existing "offline" drivers to "available"
        migrations.RunSQL(
            "UPDATE accounts_driverprofile SET status = 'available' WHERE status = 'offline';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name='driverprofile',
            name='status',
            field=models.CharField(
                choices=[('available', 'Available'), ('busy', 'Busy')],
                default='available',
                max_length=10,
            ),
        ),
    ]
