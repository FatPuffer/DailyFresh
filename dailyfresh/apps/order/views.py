from django.shortcuts import render, redirect
from django.views.generic import View
from django.core.urlresolvers import reverse
from django.db import transaction
from django.conf import settings
from django.http import JsonResponse
from datetime import datetime

from goods.models import GoodsSKU
from order.models import OrderInfo, OrderGoods
from user.models import Address

from django_redis import get_redis_connection
from utils.mixin import LoginRequiredMixin
from alipay import AliPay, ISVAliPay
import os


# /order/palce
class OrderPlaceView(LoginRequiredMixin, View):
    """提价订单显示页面"""
    def post(self, request):
        # 获取当前用户
        user = request.user
        # 获取参数sku_ids
        sku_ids = request.POST.getlist('sku_ids')
        print(sku_ids)
        # 校验参数
        if not sku_ids:
            # 跳转到购物车页面
            return redirect(reverse('cart:show'))

        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        # 保存用户购买商的所有品信息
        skus = []

        # 记录用户购买商品的总件数和总价格
        total_count = 0
        total_price = 0

        # 遍历sku_ids获取用户要购买的商品id信息
        for sku_id in sku_ids:
            # 根据商品的id获取商品对象
            sku = GoodsSKU.objects.get(id=sku_id)
            # 获取用户要购买的商品的数量
            count = conn.hget(cart_key, sku_id)
            # 计算商品小计
            amount = sku.price*int(count)
            # 动态给商品对象添加购买数量和小计属性
            sku.amount = amount
            sku.count = count
            skus.append(sku)
            # 累加计算用户购买商品总件数和总价格
            total_count += int(count)
            total_price += amount

        # 商品运费 实际开发中,运费会新建一个子系统
        transit_price = 10

        # 实付款
        total_pay = total_price + transit_price

        # 获取用户收件地址
        addrs = Address.objects.filter(user=user)

        # 组织上下文
        sku_ids = ','.join(sku_ids)
        context = {
            "skus": skus,
            "total_count": total_count,
            "total_price": total_price,
            "transit_price": transit_price,
            "total_pay": total_pay,
            "addrs": addrs,
            "sku_ids": sku_ids
        }

        # 使用模板
        return render(request, 'place_order.html', context)


# /order/commit
# 前端传递参数：订单地址（addr_id）,支付方式（pay_method）,用户购买商品id字符串
# mysql事物，一组sql操作，要么都成功，要么都失败
# 高并发：秒杀
# 支付宝支付
# 悲观锁处理
class OrderCommitView1(View):
    """订单创建"""
    # mysql事物操作装饰器
    @transaction.atomic
    def post(self, request):
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({"res": 0, "errmsg": "请登录"})

        # 接收参数
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')

        # 校验参数
        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({"res": 1, "errmsg": "参数不完整"})

        # 校验支付方式
        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({"res": 2, "errmsg": "非法的支付方式"})

        # 校验地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            return JsonResponse({"res": 3, "errmsg": "地址不存在"})

        # todo： 创建订单核心业务

        # 组织参数
        # 订单id：20190217203835+用户id
        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)

        # 运费
        transit_price = 10

        # 商品总数目和总价格
        total_count = 0
        total_price = 0

        # 设置事物保存点
        save_id = transaction.savepoint()

        try:
            # todo： 向订单信息表（df_order_info）中添加一条数据
            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_price=total_price,
                                             total_count=total_count,
                                             transit_price=transit_price)

            # todo：用户订单里面有几个商品用户订单里面有几个商品，就需要向订单商品表（df_order_goods）中添加几条数据
            conn = get_redis_connection('default')
            cart_key = "cart_%d" % user.id

            sku_ids = sku_ids.split(',')
            for sku_id in sku_ids:
                # 获取商品信息
                try:
                    # select * from df_goods_sku where id=sku_id for update;
                    sku = GoodsSKU.objects.select_for_update().get(id=sku_id)
                except GoodsSKU.DoesNotExist:
                    # 商品不存在，进行回滚到事物点
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({"res": 4, "errmsg": "商品不存在"})

                # 从redis中获取用户所要购买的商品的数量
                count = conn.hget(cart_key, sku_id)

                # todo: 判断商品库存
                if int(count) > sku.stock:
                    # 商品库存不足，进行回滚到事物点
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({"res": 5, "errmsg": "商品库存不足"})

                # todo: 向订单商品表（order_goods）中添加一条数据
                OrderGoods.objects.create(order=order,
                                          sku=sku,
                                          count=count,
                                          price=sku.price)

                # todo: 更新商品的库存和销量
                sku.stock -= int(count)
                sku.sales += int(count)
                sku.save()

                # todo: 累加计算订单商品的总数目和总价格
                amount = sku.price * int(count)
                total_count += int(count)
                total_price += amount

            # todo: 更新订单信息表中的商品总数量和总价格
            order.total_count = total_count
            order.total_price = total_price
            order.save()

        except Exception as e:
            transaction.savepoint_rollback(save_id)
            return JsonResponse({"res": 6, "errmsg": "下单失败"})

        # 提交事物
        transaction.savepoint_commit(save_id)

        # todo: 清除用户购物车中对应的记录
        conn.hdel(cart_key, *sku_ids)

        # 返回应答
        return JsonResponse({"res": 7, "errmsg": "创建订单成功"})


# 乐观锁处理
class OrderCommitView(View):
    """订单创建"""
    # mysql事物操作装饰器
    @transaction.atomic
    def post(self, request):
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({"res": 0, "errmsg": "请登录"})

        # 接收参数
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')

        # 校验参数
        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({"res": 1, "errmsg": "参数不完整"})

        # 校验支付方式
        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({"res": 2, "errmsg": "非法的支付方式"})

        # 校验地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            return JsonResponse({"res": 3, "errmsg": "地址不存在"})

        # todo： 创建订单核心业务

        # 组织参数
        # 订单id：20190217203835+用户id
        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)

        # 运费
        transit_price = 10

        # 商品总数目和总价格
        total_count = 0
        total_price = 0

        # 设置事物保存点
        save_id = transaction.savepoint()

        try:
            # todo： 向订单信息表（df_order_info）中添加一条数据
            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_price=total_price,
                                             total_count=total_count,
                                             transit_price=transit_price)

            # todo：用户订单里面有几个商品用户订单里面有几个商品，就需要向订单商品表（df_order_goods）中添加几条数据
            conn = get_redis_connection('default')
            cart_key = "cart_%d" % user.id

            sku_ids = sku_ids.split(',')
            for sku_id in sku_ids:
                for i in range(3):
                    # 获取商品信息
                    try:
                        sku = GoodsSKU.objects.get(id=sku_id)
                    except GoodsSKU.DoesNotExist:
                        # 商品不存在，进行回滚到事物点
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({"res": 4, "errmsg": "商品不存在"})

                    # 从redis中获取用户所要购买的商品的数量
                    count = conn.hget(cart_key, sku_id)

                    # todo: 判断商品库存
                    if int(count) > sku.stock:
                        # 商品库存不足，进行回滚到事物点
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({"res": 5, "errmsg": "商品库存不足"})

                    # todo: 更新商品的库存和销量
                    orgin_stock = sku.stock
                    new_stock = orgin_stock - int(count)
                    new_sales = sku.sales + int(count)

                    # 更新商品库存
                    # update df_goods_sku set stock=new_stock, sales=new_sales where id=sku_id and stock=orgin_stock
                    # 返回受影响的行数
                    res = GoodsSKU.objects.filter(id=sku_id, stock=orgin_stock).update(stock=new_stock, sales=new_sales)
                    if res == 0:
                        # 尝试的第三次
                        if i == 2:
                            transaction.savepoint_rollback(save_id)
                            return JsonResponse({"res": 8, "errmsg": "下单失败"})
                        continue

                    # todo: 向订单商品表（order_goods）中添加一条数据
                    OrderGoods.objects.create(order=order,
                                              sku=sku,
                                              count=count,
                                              price=sku.price)

                    # todo: 累加计算订单商品的总数目和总价格
                    amount = sku.price * int(count)
                    total_count += int(count)
                    total_price += amount

                    # 跳出循环
                    break

            # todo: 更新订单信息表中的商品总数量和总价格
            order.total_count = total_count
            order.total_price = total_price
            order.save()

        except Exception as e:
            transaction.savepoint_rollback(save_id)
            return JsonResponse({"res": 6, "errmsg": "下单失败1"})

        # 提交事物
        transaction.savepoint_commit(save_id)

        # todo: 清除用户购物车中对应的记录
        conn.hdel(cart_key, *sku_ids)

        # 返回应答
        return JsonResponse({"res": 7, "errmsg": "创建订单成功"})


# ajax post
# 前端传递的参数：订单id(order_id)
# /order/pay
class OrderPayView(View):
    """订单支付"""
    def post(self, request):
        # 登录验证
        user = request.user

        if not user.is_authenticated():
            return JsonResponse({"res": 0, "errmsg": "用户未登录"})

        # 接收参数
        order_id = request.POST.get('order_id')

        # 校验参数
        if not order_id:
            return JsonResponse({"res": 1, "errmsg": "无效的订单id"})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          order_status=1)
        except OrderInfo.DoesNotExist:
            return JsonResponse({"res": 2, "errmsg": "订单错误"})

        # 业务处理，使用python的 sdk 调用支付宝支付接口
        alipay = AliPay(
            appid="2016092600601590",  # 应用id，由于我们是沙箱环境，所以直接拿沙箱应用下的APPID，实际开发环境根据自己实际应用ID填写
            app_notify_url=None,  # 支付宝默认回调函数，由于我们是本地项目，没有公网ip所以就算填写了，支付宝也访问不过来。
            app_private_key_path=os.path.join(settings.BASE_DIR, 'apps/order/app_private_key.pem'),
            # alipay public key, do not use your own public key!
            alipay_public_key_path=os.path.join(settings.BASE_DIR, 'apps/order/alipay_public_key.pem'),
            sign_type="RSA2",  # RSA or RSA2
            debug=True,  # 沙箱环境,所以需要设置为True
        )

        # 调用电脑支付接口
        # 电脑网站支付，需要跳转到: https://openapi.alipay.com/gateway.do? + order_string
        # 沙箱环境需要跳转地址为： https://openapi.alipaydev.com/gateway.do? + order_string
        total_amount = order.total_price + order.transit_price  # Decimal类型，所以不能被序列化，所以需要转化未str
        order_string = alipay.api_alipay_trade_wap_pay(
            out_trade_no=order_id,  # 订单id
            total_amount=str(total_amount),  # 总结额：加运费
            subject='天天生鲜%s' % order_id,  # 标题
            return_url=None,
            notify_url=None
        )

        # 返回应答
        pay_url = "https://openapi.alipaydev.com/gateway.do?" + order_string
        return JsonResponse({"res": 3, "pay_url": pay_url})


# ajax post
# 前端传递的参数：订单id(order_id)
# /order/check
class OrderCheckPayView(View):
    """支付结果查询"""
    def post(self, request):
        """查询支付结果"""
        # 登录验证
        user = request.user

        if not user.is_authenticated():
            return JsonResponse({"res": 0, "errmsg": "用户未登录"})

        # 接收参数
        order_id = request.POST.get('order_id')

        # 校验参数
        if not order_id:
            return JsonResponse({"res": 1, "errmsg": "无效的订单id"})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          order_status=1)
        except OrderInfo.DoesNotExist:
            return JsonResponse({"res": 2, "errmsg": "订单错误"})

        # 业务处理，使用python的 sdk 调用支付宝支付接口
        alipay = AliPay(
            appid="2016092600601590",  # 应用id，由于我们是沙箱环境，所以直接拿沙箱应用下的APPID，实际开发环境根据自己实际应用ID填写
            app_notify_url=None,  # 支付宝默认回调函数，由于我们是本地项目，没有公网ip所以就算填写了，支付宝也访问不过来。
            app_private_key_path=os.path.join(settings.BASE_DIR, 'apps/order/app_private_key.pem'),
            # alipay public key, do not use your own public key!
            alipay_public_key_path=os.path.join(settings.BASE_DIR, 'apps/order/alipay_public_key.pem'),
            sign_type="RSA2",  # RSA or RSA2
            debug=True,  # 沙箱环境,所以需要设置为True
        )

        while True:
            # 调用支付宝查询接口
            # 订单支付查询接口                 商户订单号           支付宝交易号
            # 参数必传其一，由于是测试环境，我们就使用订单编号进行查询
            # api_alipay_trade_query(self, out_trade_no=None, trade_no=None)
            response = alipay.api_alipay_trade_query(out_trade_no=order.order_id)

            """
                # 自行查看支付宝开发文档/公共文档/公共错误码
                response = {
                     "alipay_trade_query_response": {
                     "trade_no": "2017032121001004070200176844",  # 支付宝交易号
                     "code": "10000",  # 接口调用是否成功
                     "invoice_amount": "20.00",
                     "open_id": "20880072506750308812798160715407",
                     "fund_bill_list": [
                         {
                            "amount": "20.00",
                            "fund_channel": "ALIPAYACCOUNT"
                         }
                     ],
                     "buyer_logon_id": "csq***@sandbox.com",
                     "send_pay_date": "2017-03-21 13:29:17",
                     "receipt_amount": "20.00",
                     "out_trade_no": "out_trade_no15",
                     "buyer_pay_amount": "20.00",
                     "buyer_user_id": "2088102169481075",
                     "msg": "Success",
                     "point_amount": "0.00",
                     "trade_status": "TRADE_SUCCESS",  # 支付结果
                     "total_amount": "20.00"
                }
            """

            code = response.get('code')

            if code == '10000' and response.get('trade_status') == "TRADE_SUCCESS":
                # 支付成功
                # 获取支付宝交易号
                trade_no = response.get('trade_no')
                # 更新订单状态
                order.trade_no = trade_no
                order.order_status = 4  # 待评价
                order.save()
                # 返回应答
                return JsonResponse({"res": 3, "errmsg": "支付成功"})

            elif code == '40004' or (code == '10000' and response.get('trade_status') == "WAIT_BUYER_PAY"):
                # 等待用户付款
                # 业务暂时处理失败，可能一会就会成功
                import time
                time.sleep(5)
                continue

            else:
                return JsonResponse({"res": 4, "errmsg": "支付失败"})


class OrderCommentView(LoginRequiredMixin, View):
    """订单评论"""
    def get(self, request, order_id):
        """提供评论页面"""
        user = request.user

        # 校验数据
        if not order_id:
            return redirect(reverse("user:order"))

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            return redirect(reverse("user:order"))

        # 根据订单的状态获取订单状态标题
        order.status_name = OrderInfo.ORDER_STATUS[order.order_status]

        # 获取订单商品信息
        order_skus = OrderGoods.objects.filter(order_id=order_id)

        for order_sku in order_skus:
            # 计算商品小计
            amount = order_sku.price*order_sku.count
            # 动态给order_sku增加属性amount,保存商品小计
            order_sku.amount = amount

        # 动态给order增加属性，order_skus,保存订单商品信息
        order.order_skus = order_skus

        # 使用模板
        return render(request, 'order_comment.html', {'order': order})

    def post(self, request, order_id):
        """评论内容处理"""
        user = request.user

        # 校验数据
        if not order_id:
            return redirect(reverse("user:order"))
        
        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            return redirect(reverse("user:order"))

        print("订单id:", order_id)
        # 根据订单商品个数获取评论条数
        total_count = request.POST.get('total_count')
        total_count = int(total_count)

        for i in range(1, total_count+1):
            # 获取评论商品的id
            sku_id = request.POST.get('sku_%d' % i)  # sku_1  sku_2
            # 获取评论内容
            content = request.POST.get('content_%d' % i, '')  # content_1  content_2
            try:
                order_goods = OrderGoods.objects.get(order=order, sku_id=sku_id)
            except OrderGoods.DoesNotExist:
                continue

            order_goods.comment = content
            order_goods.save()

        order.order_status = 5  # 修改订单状态为已完成
        order.save()

        return redirect(reverse("user:order", kwargs={'page': 1}))











































