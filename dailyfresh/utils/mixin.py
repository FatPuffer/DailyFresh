from django.contrib.auth.decorators import login_required


class LoginRequiredMixin(object):
    @classmethod
    def as_view(cls, **initkwards):
        # 调用父类的as_view
        view = super(LoginRequiredMixin, cls).as_view(**initkwards)
        return login_required(view)

