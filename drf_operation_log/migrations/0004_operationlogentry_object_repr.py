# Generated by Django 4.1.2 on 2022-10-24 06:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("drf_operation_log", "0003_operationlogentry_extra"),
    ]

    operations = [
        migrations.AddField(
            model_name="operationlogentry",
            name="object_repr",
            field=models.CharField(default="", max_length=128, verbose_name="操作对象"),
            preserve_default=False,
        ),
    ]
