from django.db import models
from django.utils import timezone


class HardwareIdentification(models.Model):
    """Model for storing hardware identification records."""

    image = models.ImageField(upload_to="hw")
    result = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Hardware identification at {self.created_at}"

    class Meta:
        ordering = ["-created_at"]


class HardwareChat(models.Model):
    """Model for storing hardware chat sessions."""

    session_id = models.CharField(max_length=100, unique=True)
    history = models.JSONField(default=list)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Chat session {self.session_id}"

    class Meta:
        ordering = ["-updated_at"]


class HardwareQuery(models.Model):
    """Model for storing individual hardware queries within chat sessions."""

    chat = models.ForeignKey(
        HardwareChat, related_name="queries", on_delete=models.CASCADE
    )
    question = models.TextField()
    answer = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Query in session {self.chat.session_id} at {self.created_at}"

    class Meta:
        ordering = ["created_at"]


class ProductSimilaritySearch(models.Model):
    """Model for storing product similarity search records."""

    image = models.ImageField(upload_to="product_similarity_searches")
    identified_component = models.TextField(null=True, blank=True)
    similar_product_ids = models.JSONField(default=list)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Product similarity search at {self.created_at}"

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Product similarity searches"
