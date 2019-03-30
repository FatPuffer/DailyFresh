from django.conf.urls import url
from order.views import OrderPlaceView, OrderCommitView, OrderPayView, OrderCheckPayView, OrderCommentView

urlpatterns = [
    url(r'^place$', OrderPlaceView.as_view(), name='place'),  # 提交订单
    url(r'^commit$', OrderCommitView.as_view(), name='commit'),  # 提交创建
    url(r'^pay$', OrderPayView.as_view(), name='pay'),  # 订单支付
    url(r'^check$', OrderCheckPayView.as_view(), name='check'),  # 支付结果查询
    url(r'^comment/(?P<order_id>.+)$', OrderCommentView.as_view(), name='comment'),  # 订单评论
]
