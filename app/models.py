from tortoise import fields
from tortoise.models import Model


class Chat(Model):
    """Chat model for storing chat history."""
    id = fields.BigIntField(pk=True)
    title = fields.CharField(max_length=200, default="")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    session_key = fields.CharField(max_length=40, null=True)

    class Meta:
        table = "app_chat"
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title or f"Chat {self.id}"


class Message(Model):
    """Message model for individual chat messages."""
    id = fields.BigIntField(pk=True)
    chat = fields.ForeignKeyField(
        "models.Chat", related_name="messages", on_delete=fields.CASCADE
    )
    role = fields.CharField(max_length=10)  # 'user' or 'assistant'
    content = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "app_message"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:30]}..."


class Session(Model):
    """Session model for storing session data."""
    session_key = fields.CharField(max_length=40, pk=True)
    data = fields.JSONField()

    class Meta:
        table = "app_session"


class ResponseTask(Model):
    """Model for tracking async response generation tasks.

    Uses FSM architecture where status is stored and status messages are derived dynamically.
    """
    id = fields.UUIDField(pk=True)
    chat = fields.ForeignKeyField("models.Chat", related_name="response_tasks")
    status = fields.CharField(max_length=20, default="pending")  # FSM states: pending, analyzing, tool_calling, synthesizing, completed, error
    partial_content = fields.TextField(null=True)  # Partial content as it's being generated
    result = fields.TextField(null=True)
    error = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "app_response_task"
