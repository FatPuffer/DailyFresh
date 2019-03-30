# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('order', '0004_auto_20190324_1225'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderinfo',
            name='order_status',
            field=models.SmallIntegerField(verbose_name='订单状态', default=1, choices=[(1, '待支付'), (2, '待发货'), (3, '待发货'), (4, '待评价'), (5, '已完成')]),
        ),
    ]
