from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from utils.mixin import LoginRequiredMixin  # 自定义登录验证模块
from django.views.generic import View  # 基于类的视图继承类
# from django.core.mail import send_mail
from django.http import HttpResponse
from django.core.paginator import Paginator
from django.conf import settings
from user.models import User, Address
from order.models import OrderInfo, OrderGoods
from goods.models import GoodsSKU
from django.contrib.auth import authenticate, login, logout  # django自带登录认证, 记录登录状态

from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from celery_task.tasks import send_register_active_email
from itsdangerous import SignatureExpired
from django_redis import get_redis_connection
import re


# /user/register
class RegisterView(View):
    """注册"""
    def get(self, request):
        """显示注册页面"""
        return render(request, 'register.html')

    def post(self, request):
        """进行注册处理"""
        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')

        # 数据完整性校验
        if not all([username, password, email]):
            print("数据不完整")
            return render(request, 'register.html', {'errmsg': '数据不完整'})

        # 校验邮箱
        if not re.match(r'^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            print("邮箱验证失败")
            return render(request, 'register.html', {'errmsg': '数据不完整'})

        # 协议校验
        if allow != 'on':
            print("未同意协议")
            return render(request, 'register.html', {'errmsg': '请同意协议'})

        # 校验用户名是否已注册
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            # 用户名不存在
            user = None

        if user:
            # 用户名已存在
            print("用户名已存在")
            return render(request, 'register.html', {'errmsg': '用户名已存在'})
        
        # 进行数据保存
        user = User.objects.create_user(username, email, password)
        user.is_active = 0
        user.save()
        # 发送激活邮件，包含激活链接:http://127.0.0.1:8000/user/active/id
        # 激活链接中需要包含用户身份信息，并且要将身份信息加密(itsdangerous模块)，防止有人恶意操作

        # 加密用户身份信息，生成激活token
        serializer = Serializer(settings.SECRET_KEY, 7200)
        # 加密对象
        info = {'confirm': user.id}
        # 进行加密
        token = serializer.dumps(info)  # 返回的是bytes类型数据
        token = token.decode()  # 将数据转为utf8

        # 发送邮件
        # subject = '天天生鲜欢迎信息'
        # message = ''
        # sender = settings.EMAIL_FROM
        # receiver = [email]
        # html_message = '<h1>%s, 欢迎您成为天天生鲜注册会员</h1>请点击下面链接激活您的账户<br/><a href="http://127.0.0.1:8000/user/active/%s">http://127.0.0.1:8000/user/active/%s</a>'%(username, token, token)

        # # message:发送不带html标签的文本信息
        # # html_message:该参数发送带html标签的文本信息
        # send_mail(subject, message, sender, receiver, html_message=html_message)

        # 使用celery发送邮件
        send_register_active_email.delay(email, username, token)

        # 返回应答，跳转到首页
        return redirect(reverse('goods:index'))


# /user/active
class ActiveView(View):
    """用户激活"""
    def get(self, request, token):
        # 进行解密，获取要激活的用户信息
        serializer = Serializer(settings.SECRET_KEY, 7200)
        try:
            info = serializer.loads(token)
            # 获取待激活用户id
            user_id = info['confirm']

            # 根据id获取用户信息
            user = User.objects.get(id=user_id)
            user.is_active = 1
            user.save()

            # 跳转到登录页面
            return redirect(reverse('user:login'))
        except SignatureExpired as e:
            # 激活链接已过期
            return HttpResponse('激活链接已过期')


# /user/login
class LoginView(View):
    """登录"""
    def get(self, request):
        """显示登录页面"""
        # 判断是否记住了用户名,如果记住用户名,则将用户名保存进cookies
        if 'username' in request.COOKIES:
            username = request.COOKIES.get('username')
            checked = 'checked'
        else:
            username = ''
            checked = ''

        return render(request, 'login.html', {'username': username, 'checked': checked})

    def post(self, request):
        """登录校验"""
        # 接收数据
        username = request.POST.get('username')
        pwd = request.POST.get('pwd')

        # 校验数据
        if not all([username, pwd]):
            return render(request, 'login.html', {'errmsg': '数据不完整'})

        # 业务处理:登录校验
        user = authenticate(username=username, password=pwd)
        if user is not None:
            if user.is_active:
                # 记录用户登录状态(login: django自带,内部运用session保存信息,默认存储于数据库,由于经常用到session信息,所以会加重数据库压力,需要在settings中配置缓存信息)
                login(request, user)

                # 获取登录后所要跳转到的地址
                # 跳转首页
                next_url = request.GET.get('next', reverse('goods:index'))

                # 跳转到next_url
                response = redirect(next_url)

                # 判断是否需要记住用户名
                remember = request.POST.get('remeber')
                if remember == "on":
                    # 记住用户名
                    response.set_cookie("username", username, max_age=7*24*3600)
                else:
                    response.delete_cookie('username')

                # 返回response
                return response
            else:
                return render(request, 'login.html', {'errmsg': '账户未激活'})
        else:
            return render(request, 'login.html', {'errmsg': '用户名或密码错误'})


# /user/logout
class LogoutView(View):
    """退出登录"""
    def get(self, request):
        # 清除用户的session信息
        logout(request)

        # 跳转到首页
        return redirect(reverse('goods:index'))


# /user
class UserInfoView(LoginRequiredMixin, View):
    """用户中心-信息页"""
    def get(self, request):
        """显示"""
        # page = "user" :传给前端,让前端判断目前处于哪个标签,从而激活该标签
        # request.user
        # 如果用户未登录->AnonymousUser类的一个实例,此时request.user.is_authenticated()  返回false
        # 如果用户登录  ->User类的一个实例,此时request.user.is_authenticated()  返回true
        # request.user.is_authenticated()
        # 除了你给模板文件传递的模板变量之外,django框架会把request.user也传递给模板

        # 获取用户的个人信息
        user = request.user
        address = Address.objects.get_default_address(user=user)

        # 获取用户历史浏览记录（与python交互固定写法）
        # from redis import StrictRedis
        # str = StrictRedis(host='127.0.0.1', port='6379', db=9)

        # default：redis在settings.py文件中的配置
        # django_redis提供的获取链接的方法
        con = get_redis_connection('default')
        history_key = 'history_%d' % user.id

        # 获取用户最新浏览的5个商品的id  lrange(键,起始下标,终止下标)
        # 返回列表
        sku_ids = con.lrange(history_key, 0, 4)

        # 从数据库中查询用户浏览的商品的具体信息
        goods_li = []
        for id in sku_ids:
            goods = GoodsSKU.objects.get(id=id)
            goods_li.append(goods)

        # 组织上下文
        context = {
            'page': 'user',
            'address': address,
            'context': goods_li
        }

        return render(request, 'user_center_info.html', context)


# /user/order
class UserOrderView(LoginRequiredMixin, View):
    """用户中心-订单页"""
    def get(self, request, page):
        """显示"""
        # page = "order" :传给前端,让前端判断目前处于哪个标签,从而激活该标签

        # 获取用户订单信息
        user = request.user
        orders = OrderInfo.objects.filter(user=user).order_by("-create_time")

        # 遍历获取订单商品信息
        for order in orders:
            # 查询订单商品对象
            order_skus = order.ordergoods_set.all()
            # 遍历order_skus计算商品的小计
            for order_sku in order_skus:
                # 计算小计
                amount = order_sku.count*order_sku.price
                # 动态给order_sku增加属性amount,保存订单的小计
                order_sku.amount = amount

            # 获取订单状态num获取对应属性名，动态给order增加属性，保存订单状态标题
            order.status_name = OrderInfo.ORDER_STATUS[order.order_status]
            # 动态给order增加属性，保存订单商品信息
            order.order_skus = order_skus

        # 分页
        paginator = Paginator(orders, 1)

        # 获取page页的内容
        try:
            page = int(page)
        except Exception as e:
            page = 1

        # 如果请求页码超出页码总页数，则返回第一页数据
        if page > paginator.num_pages:
            page = 1

        # 获取第page页的实例对象
        order_page = paginator.page(page)

        # Todo: 进行页码控制，页面上最多显示5个页码
        # 1.总页数小于5页，页面显示所有页码
        # 2.如果当前页是前三页，显示1-5页
        # 3.如果当前页是后三页(总页数的后三页)，显示后5页
        # 4.其他情况，显示当前页的前2页，当前页，后2页
        num_pages = paginator.num_pages
        if num_pages < 5:
            pages = range(1, num_pages + 1)
        elif page <= 3:
            pages = range(1, 6)
        elif num_pages - page <= 2:
            pages = range(num_pages - 4, num_pages + 1)
        else:
            pages = range(page - 2, page + 3)

        # 组织上下文
        context = {
            "order_page": order_page,
            "pages": pages,
            "page": "order",
        }
        return render(request, 'user_center_order.html', context)


# /user/address
class AddressView(LoginRequiredMixin, View):
    """用户中心-地址页"""
    def get(self, request):
        """显示"""
        # page = "address" :传给前端,让前端判断目前处于哪个标签,从而激活该标签

        # 获取用户默认收获地址
        user = request.user  # 获取登录用户对应的User

        # try:
        #     address = Address.objects.get(user=user, is_default=True)
        # except Address.DoesNotExist:
        #     address = None

        address = Address.objects.get_default_address(user=user)

        return render(request, 'user_center_site.html', {'page': 'address', 'address': address})

    def post(self, request):
        """地址的增加"""
        # 接收数据
        receiver = request.POST.get('receiver')
        addr = request.POST.get('addr')
        zip_code = request.POST.get('zip_code')
        phone = request.POST.get('phone')

        # 校验数据
        if not all([receiver, addr, phone]):
            return render(request, 'user_center_site.html', {'errmsg': '数据不完整'})

        # 校验手机
        if not re.match(r'^1[3|4|5|7|8][0-9]{9}$', phone):
            return render(request, 'user_center_site.html', {'errmsg': '手机格式不正确'})

        # 业务处理:地址添加
        # 如果用户已存在默认收货地址,添加的地址不作为默认收货地址,否则将作为默认收货地址
        user = request.user  # 获取登录用户对应的User

        # try:
        #     address = Address.objects.get(user=user, is_default=True)
        # except Address.DoesNotExist:
        #     address = None

        # 使用自定义模型管理器处理数据
        address = Address.objects.get_default_address(user=user)

        if address:
            is_default = False
        else:
            is_default = True

        Address.objects.create(user=user,
                               receiver=receiver,
                               addr=addr,
                               zip_code=zip_code,
                               phone=phone,
                               is_default=is_default)

        # 返回应答,刷新地址页面
        return redirect(reverse('user:address'))  # get请求返回方式





