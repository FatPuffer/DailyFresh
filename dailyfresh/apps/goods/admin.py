from django.contrib import admin
from django.core.cache import cache
from goods.models import GoodsType  # 商品类型类
from goods.models import IndexGoodsBanner  # 首页轮播商品展示模型类
from goods.models import IndexPromotionBanner  # 首页促销活动模型类
from goods.models import IndexTypeGoodsBanner  # 首页分类商品展示模型类
from goods.models import GoodsImage  # 商品图片模型类
from goods.models import Goods  # 商品SKU模型类
from goods.models import GoodsSKU  # 商品SKU模型类



class BaseModelAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        """新增或更新表中的数据时调用"""
        super().save_model(request, obj, form, change)

        # celery_task:是我存放celery_task任务文件tasks.py的目录，与项目其他应用评级
        from celery_task.tasks import generate_static_index_html
        
        # 调用celery任务重新生成静态页面
        generate_static_index_html.delay()

        # 清除首页的缓存数据
        cache.delete('index_page_data')

    def delete_model(self, request, obj):
        """删除表中的数据时调用"""
        super().delete_model(request, obj)

        # celery_task:是我存放celery_task任务文件tasks.py的目录，与项目其他应用评级
        from celery_task.tasks import generate_static_index_html

        # 调用celery任务重新生成静态页面
        generate_static_index_html.delay()

        # 清除首页的缓存数据
        cache.delete('index_page_data')


# 由于admin.ModelAdmin中的两个方法相同，所以我们定义一个基类，使以下四个类都继承此类
class GoodsTypeAdmin(BaseModelAdmin):
    pass


class IndexGoodsBannerAdmin(BaseModelAdmin):
    pass


class IndexTypeGoodsBnanerAdmin(BaseModelAdmin):
    pass


class IndexPormotionBannerAdmin(BaseModelAdmin):
    pass


class GoodsSKUAdmin(BaseModelAdmin):
    pass


class GoodsAdmin(BaseModelAdmin):
    pass


class GoodsImageAdmin(BaseModelAdmin):
    pass


# 注册模型类到后台管理
# 管理员修改GoodsType模型类里面的数据，将会调用GoodsTypeAdmin这个类里面的方法
admin.site.register(GoodsType, GoodsTypeAdmin)
admin.site.register(IndexGoodsBanner, IndexGoodsBannerAdmin)
admin.site.register(IndexPromotionBanner, IndexPormotionBannerAdmin)
admin.site.register(IndexTypeGoodsBanner, IndexTypeGoodsBnanerAdmin)
admin.site.register(GoodsSKU, GoodsSKUAdmin)
admin.site.register(Goods, GoodsAdmin)
admin.site.register(GoodsImage, GoodsImageAdmin)

