from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST
from django.views.generic import CreateView

from .models import Post


def index(request):
    """Public landing page listing the newest posts."""
    return render(request, "index.html", {"posts": Post.objects.order_by("-created")[:10]})


@require_POST
def login_view(request):
    """Check the submitted credentials and start a session."""
    user = authenticate(request, username=request.POST["username"], password=request.POST["password"])
    if user is None:
        return JsonResponse({"error": "invalid credentials"}, status=401)
    login(request, user)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def logout_view(request):
    logout(request)
    return JsonResponse({"ok": True})


def post_detail(request, post_id: int):
    post = get_object_or_404(Post, pk=post_id)
    return render(request, "post.html", {"post": post})


class CreatePostView(LoginRequiredMixin, CreateView):
    """Form to write a new post; only for signed-in users."""

    model = Post
    fields = ["title", "body"]


def dashboard(request):
    return render(request, "dashboard.html", {"mine": Post.objects.filter(author=request.user)})
