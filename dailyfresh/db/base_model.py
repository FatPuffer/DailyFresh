from django.db import models


class BaseModel(models.Model):
    """模型抽象基类"""
    # auto_now_add=True 第一次创建的时间，不会随数据更新而变化
    create_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    # auto_now = True 无论是添加还是修改对象，时间随之变化
    update_time = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    is_delete = models.BooleanField(default=False, verbose_name='删除标记')

    class Meta:
        """说明是一个模型抽象类"""
        abstract = True
