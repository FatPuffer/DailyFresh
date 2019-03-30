# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('order', '0005_orderinfo_order_status'),
    ]

    operations = [
        migrations.RenameField(
            model_name='orderinfo',
            old_name='trande_no',
            new_name='trade_no',
        ),
    ]
