from app.ingest.analysis import analyze_source

FASTIFY = b"""
import Fastify from 'fastify';
const app = Fastify();
app.addHook('onRequest', authenticate);
app.get('/a', { preHandler: [verifyJwt] }, listA);
app.post('/b', { onRequest: guard }, async (req) => save(req));
app.route({ method: ['GET', 'HEAD'], url: '/c', preHandler: requireAdmin, handler: showC });
"""

CHAIN = b"""
import express from 'express';
const r = express.Router();
r.route('/items').get(list).post(requireAuth, create);
"""

DJANGO_URLS = b"""
from django.contrib.auth.decorators import login_required
from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter
from . import views, api

router = DefaultRouter()
router.register(r"posts", api.PostViewSet)
urlpatterns = [
    path("", views.index),
    path("me/", login_required(views.me)),
    path("new/", views.CreateView.as_view()),
    re_path(r"^old/(?P<slug>[\w-]+)/$", views.old),
    path("api/", include(router.urls)),
    path("other/", include("other.urls")),
]
"""

DJANGO_VIEWS = b"""
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.http import require_POST
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser

@login_required
@require_POST
def save(request): ...

class Panel(LoginRequiredMixin, View):
    permission_classes = [IsAdminUser, AllowAny]

@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def open_api(request): ...
"""


def _routes(src, lang):
    return {(e.method, e.path): e for e in analyze_source(src, lang).endpoints}


def test_fastify_options_hooks_and_route_object():
    eps = _routes(FASTIFY, "typescript")

    assert set(eps) == {("GET", "/a"), ("POST", "/b"), ("GET", "/c"), ("HEAD", "/c")}
    assert eps[("GET", "/a")].framework == "fastify"
    assert set(eps[("GET", "/a")].signals) == {"authenticate", "verifyJwt"}  # hook + preHandler
    assert "guard" in eps[("POST", "/b")].signals
    assert eps[("POST", "/b")].inline_calls == ("save",)
    assert eps[("GET", "/c")].handler_name == "showC"
    assert "requireAdmin" in eps[("HEAD", "/c")].signals


def test_express_route_chain():
    eps = _routes(CHAIN, "typescript")

    assert set(eps) == {("GET", "/items"), ("POST", "/items")}
    assert eps[("POST", "/items")].signals == ("requireAuth",)
    assert eps[("POST", "/items")].handler_name == "create"
    assert eps[("GET", "/items")].signals == ()


def test_django_url_conf_and_router_prefix():
    eps = _routes(DJANGO_URLS, "python")

    assert ("ANY", "/") in eps and ("ANY", "/new/") in eps
    assert eps[("ANY", "/me/")].signals == ("login_required",)
    assert eps[("ANY", "/me/")].handler_name == "me"
    assert eps[("ANY", "/new/")].handler_name == "CreateView"
    assert ("ANY", "/old/<slug>/") in eps  # regex named groups become <name>
    assert ("GET", "/api/posts") in eps and ("DELETE", "/api/posts/<pk>") in eps
    assert not any(p.startswith("/other") for _, p in eps)  # include("other.urls") is skipped


def test_django_view_guards_become_pseudo_calls():
    calls = {c.callee_full for c in analyze_source(DJANGO_VIEWS, "python").calls}

    assert {"@login_required", "@require_POST", "@LoginRequiredMixin", "@IsAdminUser"} <= calls
    assert "@AllowAny" not in calls  # AllowAny is not a guard
    assert "@api_view:GET,POST" in calls
