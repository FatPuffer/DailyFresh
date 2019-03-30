# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('order', '0002_auto_20190210_1850'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ordergoods',
            name='comment',
            field=models.CharField(verbose_name='评论', max_length=256, default=''),
        ),
    ]
