from django.conf.urls import url
from .views import CartAddView, CartInfoView, CartUpdateView, CartDeleteView

urlpatterns = [
    url(r'^add$', CartAddView.as_view(), name='add'),  # 添加购物车
    url(r'^$', CartInfoView.as_view(), name='show'),  # 购物车页面显示
    url(r'^update$', CartUpdateView.as_view(), name='update'),  # 更新购物车记录
    url(r'^delete$', CartDeleteView.as_view(), name='delete'),  # 删除购物车记录
]
