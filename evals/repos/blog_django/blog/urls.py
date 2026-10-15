from django.contrib.auth.decorators import login_required
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api, views

router = DefaultRouter()
router.register(r"posts", api.PostViewSet, basename="post")
router.register(r"tags", api.TagViewSet, basename="tag")

urlpatterns = [
    path("", views.index, name="index"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("posts/<int:post_id>/", views.post_detail, name="post-detail"),
    path("posts/new/", views.CreatePostView.as_view(), name="post-new"),
    path("dashboard/", login_required(views.dashboard), name="dashboard"),
    path("api/health/", api.health),
    path("api/", include(router.urls)),
]
