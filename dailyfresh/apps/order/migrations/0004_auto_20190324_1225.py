# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('order', '0003_auto_20190315_2213'),
    ]

    operations = [
        migrations.AlterField(
            model_name='orderinfo',
            name='trande_no',
            field=models.CharField(verbose_name='支付编码', max_length=128, default=''),
        ),
    ]
