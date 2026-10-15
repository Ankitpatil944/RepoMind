from django.conf import settings
from django.db import models


class Tag(models.Model):
    name = models.CharField(max_length=40, unique=True)

    def __str__(self) -> str:
        return self.name


class Post(models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tags = models.ManyToManyField(Tag, blank=True)

    def word_count(self) -> int:
        """Number of words in the post body."""
        return len(self.body.split())
