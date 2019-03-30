from django.shortcuts import render
from django.views.generic import View
from django.http import JsonResponse
from goods.models import GoodsSKU
from django_redis import get_redis_connection
from utils.mixin import LoginRequiredMixin


# 添加商品到购物车
# 1.请求方式，采用ajax
# 	如果涉及到数据的修改（增，删，改），采用post
# 	如果只涉及到数据的获取，采用get
# 2.传递参数，商品id(sku_id) 商品数量(count)


class CartAddView(View):
    """添加购物车记录"""
    def post(self, request):
        user = request.user
        if not user.is_authenticated():
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '请先登录'})

        # 1.获取数据
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 2.数据校验
        if not all([sku_id, count]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        # 检验添加的商品数量
        try:
            count = int(count)
        except Exception as e:
            # 数目出错
            return JsonResponse({'res': 2, 'errmsg': '商品数目出错'})

        # 校验商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res': 3, 'errmsg': '商品不存在'})

        # 3.业务处理
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        # 尝试先获取sku_id的值, --> hget cart_key
        # 如果获取不到返回None
        cart_count = conn.hget(cart_key, sku_id)
        if cart_count:
            # 累加购物车商品数目
            count += int(cart_count)

        # 校验商品的库存
        if count > sku.stock:
            return JsonResponse({'res': 4, 'errmsg': '库存不足'})

        # 设置hash中sku_id对应的值, 如果sku_id不存在则添加, 存在则更新
        conn.hset(cart_key, sku_id, count)

        # 统计用户购物车中的商品条目
        total_count = conn.hlen(cart_key)

        # 4.返回响应
        return JsonResponse({'res': 5, 'total_count': total_count, 'errmsg': '添加成功'})


class CartInfoView(LoginRequiredMixin, View):
    """购物车页面显示"""
    def get(self, request):
        """显示"""
        # 获取登录的用户
        user = request.user
        # 获取用户购物车里面的信息
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        # {'商品id': '商品数量'}
        cart_dict = conn.hgetall(cart_key)

        skus = []
        # 保存用户购物车中商品的总件数，总价格
        total_count = 0
        total_price = 0
        # 遍历获取商品信息
        for sku_id, count in cart_dict.items():
            # 根据商品id获取商品数量
            sku = GoodsSKU.objects.get(id=sku_id)
            # 计算商品的小计
            amount = sku.price*int(count)
            # 动态给sku对象增加一个属性amount, 保存商品小计
            sku.amount = amount
            # 动态给sku对象增加一个属性count, 保存商品数量
            sku.count = count
            # 添加商品对象
            skus.append(sku)

            # 累加计算商品总件数和总价格
            total_count += int(count)
            total_price += amount

        # 组织上下文
        context = {
            'total_count': total_count,
            'total_price': total_price,
            'skus': skus
        }

        return render(request, 'cart.html', context)


# 更新购物车
# ajax post
# 前端传递参数：商品id(sku_id),更新数量(count)
class CartUpdateView(View):
    """更新购物车记录"""
    def post(self, request):
        user = request.user
        if not user.is_authenticated():
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '请先登录'})

        # 接收数据
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 2.数据校验
        if not all([sku_id, count]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        # 检验添加的商品数量
        try:
            count = int(count)
        except Exception as e:
            # 数目出错
            return JsonResponse({'res': 2, 'errmsg': '商品数目出错'})

        # 校验商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res': 3, 'errmsg': '商品不存在'})

        # 业务处理：更新购物车记录
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        # 校验商品库存
        if count > sku.stock:
            return JsonResponse({'res': 4, 'errmsg': '商品库存不足'})

        # 更新
        conn.hset(cart_key, sku_id, count)

        # 计算用户购物车种商品总件数
        vals = conn.hvals(cart_key)
        total_count = 0
        for val in vals:
            total_count += int(val)

        # 返回应答
        return JsonResponse({'res': 5, 'total_count': total_count, 'ermsg': '更新成功'})


# 删除购物车记录
# ajax post
# 前端传递参数：商品id(sku_id)
class CartDeleteView(View):
    """购物车删除记录"""
    def post(self, request):
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated():
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '请先登录'})

        # 接收数据
        sku_id = request.POST.get('sku_id')

        # 校验数据
        if not sku_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的商品id'})

        # 校验商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '商品不存在'})

        # 业务处理:删除购物车记录
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        # 删除 hdel
        conn.hdel(cart_key, sku_id)

        # 计算用户购物车种商品总件数
        vals = conn.hvals(cart_key)
        total_count = 0
        for val in vals:
            total_count += int(val)

        # 返回应答
        return JsonResponse({'res': 3, 'total_count': total_count, 'errmsg': '删除成功'})



