from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.views.generic import View
from django.core.paginator import Paginator  # 分页
from django.core.cache import cache  # django自带缓存api接口
from django_redis import get_redis_connection
from order.models import OrderGoods
from goods.models import GoodsType, GoodsSKU, IndexGoodsBanner, IndexPromotionBanner, IndexTypeGoodsBanner


class IndexView(View):
    def get(self, request):
        """首页展示"""
        # 尝试从缓存中获取数据,cache.get获取不到数据返回None
        context = cache.get("index_page_data")
        if context is None:
            """未获取到数据"""

            # 获取商品的种类信息
            types = GoodsType.objects.all()

            # 获取首页轮播商品信息
            goods_banners = IndexGoodsBanner.objects.all().order_by('index')

            # 获取首页促销活动信息
            promotion_banners = IndexPromotionBanner.objects.all().order_by('index')

            # 获取首页分类商品展示信息
            for type in types:
                # 获取type种类首页分类商品的图片展示信息
                image_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=1).order_by('index')
                # 获取type种类首页分类商品的文字展示信息
                title_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=0).order_by('index')

                # 动态给type增加属性，分别保存首页分类商品的图片展示信息和文字展示信息
                type.image_banners = image_banners
                type.title_banners = title_banners

            context = {
                "types": types,
                "goods_banners": goods_banners,
                "promotion_banners": promotion_banners,
            }

            # 设置缓存
            cache.set("index_page_data", context, 3600)

        # 获取用户购物车中商品的数目
        user = request.user
        cart_count = 0
        # 判断用户是否已登录
        if user.is_authenticated():
            # 用户已登录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            # 获取用户购物车内的商品总条目数
            cart_count = conn.hlen(cart_key)

        # 组织模板上下文(更新用户个人购物车信息)
        context.update(cart_count=cart_count)

        return render(request, 'index.html', context)


# /goods/
class DetailView(View):
    """商品详情页"""
    def get(self, request, goods_id):
        try:
            sku = GoodsSKU.objects.get(id=goods_id)
        except GoodsSKU.DoesNotExist:
            # 商品不存在
            return redirect(reverse("goods:index"))

        # 获取商品的分类信息
        types = GoodsType.objects.all()

        # 获取商品的评论信息,过滤掉评论信息为空的数据
        sku_orders = OrderGoods.objects.filter(sku=sku).exclude(comment='').order_by('-create_time')

        # 获取同一个SPU商品的 "其他" 规格商品
        same_spu_skus = GoodsSKU.objects.filter(goods=sku.goods).exclude(id=goods_id)

        # 获取新品信息(推荐新品根据该商品的所属类型进行推荐),根据时间降序排列.
        new_skus = GoodsSKU.objects.filter(type=sku.type).order_by('-create_time')[:5]

        # 获取用户购物车中商品的数目
        user = request.user
        cart_count = 0
        # 判断用户是否已登录
        if user.is_authenticated():
            # 用户已登录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            # 获取用户购物车内的商品总条目数
            cart_count = conn.hlen(cart_key)

            # 添加用户历史浏览记录
            conn = get_redis_connection('default')
            history_key = 'history_%d' % user.id
            # 移除列表中的goods_id
            conn.lrem(history_key, 0, goods_id)
            # 把goods_id插入到列表的左侧
            conn.lpush(history_key, goods_id)
            # 只保存最近浏览的5条信息
            conn.ltrim(history_key, 0, 4)

        # 组织模板上下文
        context = {
            "sku": sku,
            "types": types,
            "sku_orders": sku_orders,
            "new_skus": new_skus,
            "same_spu_skus": same_spu_skus,
            "cart_count": cart_count
        }

        # 使用模板
        return render(request, "detail.html", context)


# /list/种类id/页码/排序方式
# /list?type_id=种类id&page_num=页码&sort=排序方式
# /list/种类id/页码?sort=排序方式（推荐写法）
class ListView(View):
    """列表页"""
    def get(self, request, type_id, page):
        """
        :param
            type_id: 商品种类id
            page: 页码
        :return:
        """
        # 获取种类信息
        try:
            type = GoodsType.objects.get(id=type_id)
        except GoodsType.DoesNotExist:
            # 种类不存在
            return redirect(reverse("goods:index"))

        # 获取商品分类信息
        types = GoodsType.objects.all()

        # 获取排序方式，获取分类商品的信息
        # sort=default  默认排序
        # sort=price  按照价格排序
        # sort=hot  按照商品销量排序
        sort = request.GET.get('sort')

        if sort == "price":
            skus = GoodsSKU.objects.filter(type=type).order_by('price')
        elif sort == "hot":
            skus = GoodsSKU.objects.filter(type=type).order_by('-sales')
        else:
            sort = "default"
            skus = GoodsSKU.objects.filter(type=type).order_by('-id')

        # 对数据进行分页,分页数据列表对象，分页数量
        paginator = Paginator(skus, 1)

        # 获取page页的内容
        try:
            page = int(page)
        except Exception as e:
            page = 1

        # 如果请求页码超出页码总页数，则返回第一页数据
        if page > paginator.num_pages:
            page = 1

        # 获取第page页的实例对象
        skus_page = paginator.page(page)

        # Todo: 进行页码控制，页面上最多显示5个页码
        # 1.总页数小于5页，页面显示所有页码
        # 2.如果当前页是前三页，显示1-5页
        # 3.如果当前页是后三页(总页数的后三页)，显示后5页
        # 4.其他情况，显示当前页的前2页，当前页，后2页
        num_pages = paginator.num_pages
        if num_pages < 5:
            pages = range(1, num_pages+1)
        elif page <= 3:
            pages = range(1, 6)
        elif num_pages - page <= 2:
            pages = range(num_pages-4, num_pages+1)
        else:
            pages = range(page-2, page+3)

        # 获取新品信息(推荐新品根据该商品的所属类型进行推荐),根据时间降序排列.
        new_skus = GoodsSKU.objects.filter(type=type).order_by('-create_time')[:5]

        # 获取用户购物车中商品的数目
        user = request.user
        cart_count = 0
        # 判断用户是否已登录
        if user.is_authenticated():
            # 用户已登录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            # 获取用户购物车内的商品总条目数
            cart_count = conn.hlen(cart_key)

        # 组织模板上下文
        context = {
            "type": type,
            "types": types,
            "skus_page": skus_page,
            "new_skus": new_skus,
            "cart_count": cart_count,
            "sort": sort,
            "pages": pages
        }

        return render(request, 'list.html', context)











